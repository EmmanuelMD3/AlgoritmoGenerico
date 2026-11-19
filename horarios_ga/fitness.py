"""Evaluación lexicográfica de restricciones duras y calidad académica."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .modelo import Cromosoma, Problema


VALOR_BASE = 1000

# Las violaciones duras se muestran en el fitness para que la cifra sea legible,
# pero la comparación genética usa primero el total de violaciones, sin depender
# de estos pesos.
PESOS_DUROS = {
    "docente": 100,
    "salon": 100,
    "grupo": 100,
    "disponibilidad_docente": 100,
    "disponibilidad_grupo": 100,
    "franja_no_lectiva": 100,
    "periodo_academico": 100,
    "consecutivas_grupo": 100,
    "consecutivas_docente": 100,
}

PESOS_BLANDOS = {
    "huecos": 20,
    "jornada_extensa": 8,
    "sesion_aislada_final": 12,
    "desequilibrio_carga": 6,
    "cambios_salon": 10,
    "fuera_preferencia_docente": 4,
}

# Alias compatible con código académico anterior que importara PESOS.
PESOS = {
    "docente": PESOS_DUROS["docente"],
    "salon": PESOS_DUROS["salon"],
    "grupo": PESOS_DUROS["grupo"],
    "disponibilidad": PESOS_DUROS["disponibilidad_docente"],
    "huecos": PESOS_BLANDOS["huecos"],
}


@dataclass(frozen=True)
class Evaluacion:
    # Campos originales conservados para compatibilidad.
    fitness: int
    conflicto_docente: int
    conflicto_salon: int
    conflicto_grupo: int
    fuera_disponibilidad: int
    huecos: int

    # Restricciones duras de Fase 2.
    grupo_no_disponible: int = 0
    franja_no_lectiva: int = 0
    fuera_periodo: int = 0
    exceso_consecutivo_grupo: int = 0
    exceso_consecutivo_docente: int = 0

    # Penalizaciones blandas de Fase 2.
    jornada_extensa: int = 0
    sesiones_aisladas_final: int = 0
    desequilibrio_carga: int = 0
    cambios_salon: int = 0
    fuera_preferencia_docente: int = 0
    penalizacion_blanda: int = 0
    penalizacion_dura: int = 0

    @property
    def duras(self) -> int:
        return (
            self.conflicto_docente + self.conflicto_salon
            + self.conflicto_grupo + self.fuera_disponibilidad
            + self.grupo_no_disponible + self.franja_no_lectiva
            + self.fuera_periodo + self.exceso_consecutivo_grupo
            + self.exceso_consecutivo_docente
        )

    @property
    def blandas(self) -> int:
        """Penalización blanda ponderada; cero es la mejor calidad modelada."""
        return self.penalizacion_blanda

    @property
    def factible(self) -> bool:
        return self.duras == 0

    def prioridad(self) -> tuple[int, int, int]:
        """Minimiza primero duras y después la penalización académica blanda."""
        return (-self.duras, -self.penalizacion_blanda, self.fitness)

    def desglose_duro(self) -> dict[str, int]:
        return {
            "Colisiones de docente": self.conflicto_docente,
            "Colisiones de salón": self.conflicto_salon,
            "Colisiones de grupo": self.conflicto_grupo,
            "Indisponibilidad docente": self.fuera_disponibilidad,
            "Indisponibilidad de grupo": self.grupo_no_disponible,
            "Franjas no lectivas": self.franja_no_lectiva,
            "Fuera de periodo permitido": self.fuera_periodo,
            "Exceso consecutivo de grupo": self.exceso_consecutivo_grupo,
            "Exceso consecutivo de docente": self.exceso_consecutivo_docente,
        }

    def desglose_blando(self) -> dict[str, int]:
        return {
            "Huecos entre clases": self.huecos,
            "Extensión de jornada": self.jornada_extensa,
            "Sesiones aisladas al final": self.sesiones_aisladas_final,
            "Desequilibrio semanal": self.desequilibrio_carga,
            "Cambios innecesarios de salón": self.cambios_salon,
            "Fuera de preferencia docente": self.fuera_preferencia_docente,
        }

    def razones_no_factible(self) -> tuple[str, ...]:
        return tuple(
            f"{nombre}: {cantidad}"
            for nombre, cantidad in self.desglose_duro().items()
            if cantidad
        )


def _exceso_consecutivo(bloques: set[int], limite: int | None) -> tuple[int, set[int]]:
    if limite is None or not bloques:
        return 0, set()
    total = 0
    infractores: set[int] = set()
    corrida: list[int] = []
    for bloque in sorted(bloques):
        if corrida and bloque != corrida[-1] + 1:
            if len(corrida) > limite:
                total += len(corrida) - limite
                infractores.update(corrida[limite:])
            corrida = []
        corrida.append(bloque)
    if len(corrida) > limite:
        total += len(corrida) - limite
        infractores.update(corrida[limite:])
    return total, infractores


def evaluar_detallado(
    problema: Problema, cromosoma: Cromosoma,
) -> tuple[Evaluacion, frozenset[int]]:
    """Evalúa y devuelve además los índices de sesiones con violaciones duras."""
    problema.validar_cromosoma(cromosoma)

    ocupacion_docente: Counter[tuple[str, int, int]] = Counter()
    ocupacion_salon: Counter[tuple[int, int, int]] = Counter()
    ocupacion_grupo: Counter[tuple[str, int, int]] = Counter()
    indices_docente: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    indices_salon: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    indices_grupo: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    horas_por_grupo: dict[tuple[str, int], set[int]] = defaultdict(set)
    horas_por_docente: dict[tuple[str, int], set[int]] = defaultdict(set)
    salones_por_clase: dict[str, set[int]] = defaultdict(set)
    conflictivos: set[int] = set()

    fuera_disponibilidad = 0
    grupo_no_disponible = 0
    franja_no_lectiva = 0
    fuera_periodo = 0
    fuera_preferencia_docente = 0

    for idx, (sesion, (dia, inicio, salon)) in enumerate(zip(problema.sesiones, cromosoma)):
        salones_por_clase[sesion.clase_id or sesion.id].add(salon)
        docente = problema.docentes[sesion.docente]
        grupo = problema.grupos[sesion.grupo]
        for bloque in range(inicio, inicio + sesion.duracion):
            clave_docente = (sesion.docente, dia, bloque)
            clave_salon = (salon, dia, bloque)
            clave_grupo = (sesion.grupo, dia, bloque)
            ocupacion_docente[clave_docente] += 1
            ocupacion_salon[clave_salon] += 1
            ocupacion_grupo[clave_grupo] += 1
            indices_docente[clave_docente].append(idx)
            indices_salon[clave_salon].append(idx)
            indices_grupo[clave_grupo].append(idx)
            horas_por_grupo[(sesion.grupo, dia)].add(bloque)
            horas_por_docente[(sesion.docente, dia)].add(bloque)

            posicion = (dia, bloque)
            if posicion in docente.no_disponible:
                fuera_disponibilidad += 1
                conflictivos.add(idx)
            if posicion in grupo.no_disponible:
                grupo_no_disponible += 1
                conflictivos.add(idx)
            if posicion in problema.franjas_no_lectivas:
                franja_no_lectiva += 1
                conflictivos.add(idx)
            if sesion.periodos_permitidos is not None and posicion not in sesion.periodos_permitidos:
                fuera_periodo += 1
                conflictivos.add(idx)
            if docente.preferidos and posicion not in docente.preferidos:
                fuera_preferencia_docente += 1

    pares = lambda n: n * (n - 1) // 2
    conflicto_docente = sum(pares(n) for n in ocupacion_docente.values())
    conflicto_salon = sum(pares(n) for n in ocupacion_salon.values())
    conflicto_grupo = sum(pares(n) for n in ocupacion_grupo.values())
    for contador, indices in (
        (ocupacion_docente, indices_docente),
        (ocupacion_salon, indices_salon),
        (ocupacion_grupo, indices_grupo),
    ):
        for clave, cantidad in contador.items():
            if cantidad > 1:
                conflictivos.update(indices[clave])

    exceso_grupo = 0
    for (grupo_id, dia), bloques in horas_por_grupo.items():
        grupo = problema.grupos[grupo_id]
        limite = grupo.max_horas_consecutivas or problema.max_horas_consecutivas_grupo
        exceso, infractores = _exceso_consecutivo(bloques, limite)
        exceso_grupo += exceso
        for bloque in infractores:
            conflictivos.update(indices_grupo[(grupo_id, dia, bloque)])

    exceso_docente = 0
    for (docente_id, dia), bloques in horas_por_docente.items():
        docente = problema.docentes[docente_id]
        limite = docente.max_horas_consecutivas or problema.max_horas_consecutivas_docente
        exceso, infractores = _exceso_consecutivo(bloques, limite)
        exceso_docente += exceso
        for bloque in infractores:
            conflictivos.update(indices_docente[(docente_id, dia, bloque)])

    huecos = sum(
        max(bloques) - min(bloques) + 1 - len(bloques)
        for bloques in horas_por_grupo.values() if bloques
    )
    jornada_extensa = sum(
        max(0, max(bloques) - min(bloques) + 1 - problema.umbral_jornada_larga)
        for bloques in horas_por_grupo.values() if bloques
    )
    sesiones_aisladas_final = sum(
        1
        for bloques in horas_por_grupo.values()
        if bloques
        and max(bloques) == len(problema.horas) - 1
        and (max(bloques) - 1) not in bloques
    )

    desequilibrio_carga = 0
    for grupo_id in problema.grupos:
        cargas = [len(horas_por_grupo.get((grupo_id, dia), set())) for dia in range(len(problema.dias))]
        if cargas:
            desequilibrio_carga += max(cargas) - min(cargas)
    cambios_salon = sum(max(0, len(salones) - 1) for salones in salones_por_clase.values())

    valores_duros = {
        "docente": conflicto_docente,
        "salon": conflicto_salon,
        "grupo": conflicto_grupo,
        "disponibilidad_docente": fuera_disponibilidad,
        "disponibilidad_grupo": grupo_no_disponible,
        "franja_no_lectiva": franja_no_lectiva,
        "periodo_academico": fuera_periodo,
        "consecutivas_grupo": exceso_grupo,
        "consecutivas_docente": exceso_docente,
    }
    valores_blandos = {
        "huecos": huecos,
        "jornada_extensa": jornada_extensa,
        "sesion_aislada_final": sesiones_aisladas_final,
        "desequilibrio_carga": desequilibrio_carga,
        "cambios_salon": cambios_salon,
        "fuera_preferencia_docente": fuera_preferencia_docente,
    }
    penalizacion_dura = sum(PESOS_DUROS[k] * v for k, v in valores_duros.items())
    penalizacion_blanda = sum(PESOS_BLANDOS[k] * v for k, v in valores_blandos.items())
    fitness = VALOR_BASE - penalizacion_dura - penalizacion_blanda

    evaluacion = Evaluacion(
        fitness=fitness,
        conflicto_docente=conflicto_docente,
        conflicto_salon=conflicto_salon,
        conflicto_grupo=conflicto_grupo,
        fuera_disponibilidad=fuera_disponibilidad,
        huecos=huecos,
        grupo_no_disponible=grupo_no_disponible,
        franja_no_lectiva=franja_no_lectiva,
        fuera_periodo=fuera_periodo,
        exceso_consecutivo_grupo=exceso_grupo,
        exceso_consecutivo_docente=exceso_docente,
        jornada_extensa=jornada_extensa,
        sesiones_aisladas_final=sesiones_aisladas_final,
        desequilibrio_carga=desequilibrio_carga,
        cambios_salon=cambios_salon,
        fuera_preferencia_docente=fuera_preferencia_docente,
        penalizacion_blanda=penalizacion_blanda,
        penalizacion_dura=penalizacion_dura,
    )
    return evaluacion, frozenset(conflictivos)


def evaluar(problema: Problema, cromosoma: Cromosoma) -> Evaluacion:
    return evaluar_detallado(problema, cromosoma)[0]


def indices_conflictivos(problema: Problema, cromosoma: Cromosoma) -> frozenset[int]:
    """Sesiones involucradas en al menos una violación dura."""
    return evaluar_detallado(problema, cromosoma)[1]
