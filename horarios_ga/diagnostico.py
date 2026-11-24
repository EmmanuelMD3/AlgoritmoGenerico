"""Diagnóstico explicable de factibilidad y conflictos de un horario."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import combinations

from .fitness import Evaluacion, evaluar
from .modelo import Cromosoma, Gen, Problema


class EstadoFactibilidad(str, Enum):
    SOLUCION_FACTIBLE = "solucion_factible_encontrada"
    NO_ENCONTRADA = "no_se_encontro_solucion_en_el_presupuesto"
    IMPOSIBILIDAD_DEMOSTRADA = "imposibilidad_demostrada"
    INCONCLUSA = "verificacion_inconclusa"


@dataclass(frozen=True)
class CotaNecesaria:
    recurso: str
    demanda_bloques: int
    capacidad_superior: int
    detalle: str

    @property
    def contradiccion(self) -> bool:
        return self.demanda_bloques > self.capacidad_superior


@dataclass(frozen=True)
class AlternativaAsignacion:
    dia: str
    hora: str
    salon: str
    duras_resultantes: int
    penalizacion_blanda: int
    mejora_duras: int


@dataclass(frozen=True)
class AsignacionConflictiva:
    indice: int
    sesion_id: str
    clase_id: str
    materia: str
    grupo: str
    docente: str
    dia: str
    hora: str
    salon: str
    razones: tuple[str, ...]
    alternativas: tuple[AlternativaAsignacion, ...]


@dataclass(frozen=True)
class DiagnosticoHorario:
    estado: EstadoFactibilidad
    evaluacion: Evaluacion
    asignaciones_conflictivas: tuple[AsignacionConflictiva, ...]
    cotas: tuple[CotaNecesaria, ...]
    sesiones_sin_posicion_estatica: tuple[str, ...]

    @property
    def contradicciones_demostrables(self) -> tuple[CotaNecesaria, ...]:
        return tuple(cota for cota in self.cotas if cota.contradiccion)


def _posicion_estaticamente_valida(problema: Problema, indice: int, gen: Gen) -> bool:
    sesion = problema.sesiones[indice]
    docente = problema.docentes[sesion.docente]
    grupo = problema.grupos[sesion.grupo]
    dia, inicio, _salon = gen
    for bloque in range(inicio, inicio + sesion.duracion):
        posicion = (dia, bloque)
        if (
            posicion in docente.no_disponible
            or posicion in grupo.no_disponible
            or posicion in problema.franjas_no_lectivas
            or (
                sesion.periodos_permitidos is not None
                and posicion not in sesion.periodos_permitidos
            )
        ):
            return False
    return True


def candidatos_estaticos(problema: Problema, indice: int) -> tuple[Gen, ...]:
    """Dominio compatible con todas las restricciones duras de una sola sesión."""
    sesion = problema.sesiones[indice]
    return tuple(
        gen
        for dia in range(len(problema.dias))
        for inicio in range(len(problema.horas) - sesion.duracion + 1)
        for salon in problema.salones_validos[indice]
        if _posicion_estaticamente_valida(problema, indice, gen := (dia, inicio, salon))
    )


def _maximo_bloques_consecutivos(
    problema: Problema, no_disponible: frozenset[tuple[int, int]], limite: int | None,
) -> int:
    total = 0
    for dia in range(len(problema.dias)):
        corrida = 0
        for bloque in range(len(problema.horas) + 1):
            disponible = (
                bloque < len(problema.horas)
                and (dia, bloque) not in no_disponible
                and (dia, bloque) not in problema.franjas_no_lectivas
            )
            if disponible:
                corrida += 1
                continue
            if corrida:
                total += corrida if limite is None else corrida - corrida // (limite + 1)
            corrida = 0
    return total


def analizar_cotas_necesarias(problema: Problema) -> tuple[CotaNecesaria, ...]:
    """Calcula sólo cotas necesarias; no confunde holgura con factibilidad."""
    demanda_grupo: dict[str, int] = defaultdict(int)
    demanda_docente: dict[str, int] = defaultdict(int)
    for sesion in problema.sesiones:
        demanda_grupo[sesion.grupo] += sesion.duracion
        demanda_docente[sesion.docente] += sesion.duracion

    cotas: list[CotaNecesaria] = []
    for grupo_id, grupo in problema.grupos.items():
        limite = grupo.max_horas_consecutivas or problema.max_horas_consecutivas_grupo
        capacidad = _maximo_bloques_consecutivos(problema, grupo.no_disponible, limite)
        cotas.append(CotaNecesaria(
            f"Grupo {grupo_id}", demanda_grupo.get(grupo_id, 0), capacidad,
            "Disponibilidad y máximo consecutivo; ignora docentes y salones.",
        ))
    for docente_id, docente in problema.docentes.items():
        limite = docente.max_horas_consecutivas or problema.max_horas_consecutivas_docente
        capacidad = _maximo_bloques_consecutivos(problema, docente.no_disponible, limite)
        cotas.append(CotaNecesaria(
            f"Docente {docente_id}", demanda_docente.get(docente_id, 0), capacidad,
            "Disponibilidad y máximo consecutivo; ignora grupos y salones.",
        ))

    bloques_institucionales = (
        len(problema.dias) * len(problema.horas) - len(problema.franjas_no_lectivas)
    )
    conjuntos = sorted(
        {frozenset(validos) for validos in problema.salones_validos},
        key=lambda conjunto: (len(conjunto), tuple(conjunto)),
    )
    # También revisa uniones de dominios de salones; con cinco salones el número
    # de subconjuntos sigue siendo pequeño y la desigualdad es una cota de Hall.
    uniones = set(conjuntos)
    for cantidad in range(2, min(4, len(conjuntos)) + 1):
        for seleccion in combinations(conjuntos, cantidad):
            uniones.add(frozenset().union(*seleccion))
    for conjunto in sorted(uniones, key=lambda c: (len(c), tuple(c))):
        demanda = sum(
            sesion.duracion
            for sesion, validos in zip(problema.sesiones, problema.salones_validos)
            if frozenset(validos) <= conjunto
        )
        nombres = ", ".join(problema.salones[i].id for i in sorted(conjunto))
        cotas.append(CotaNecesaria(
            f"Salones {{{nombres}}}", demanda, bloques_institucionales * len(conjunto),
            "Cota agregada por compatibilidad de tipo/capacidad y franjas institucionales.",
        ))
    return tuple(cotas)


def _razones_por_sesion(problema: Problema, cromosoma: Cromosoma) -> dict[int, set[str]]:
    razones: dict[int, set[str]] = defaultdict(set)
    ocupacion_docente: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    ocupacion_grupo: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    ocupacion_salon: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    bloques_grupo: dict[tuple[str, int], set[int]] = defaultdict(set)
    bloques_docente: dict[tuple[str, int], set[int]] = defaultdict(set)

    for indice, (sesion, (dia, inicio, salon)) in enumerate(zip(problema.sesiones, cromosoma)):
        docente = problema.docentes[sesion.docente]
        grupo = problema.grupos[sesion.grupo]
        for bloque in range(inicio, inicio + sesion.duracion):
            posicion = (dia, bloque)
            hora = problema.horas[bloque]
            if posicion in docente.no_disponible:
                razones[indice].add(f"Docente no disponible en {problema.dias[dia]} {hora}")
            if posicion in grupo.no_disponible:
                razones[indice].add(f"Grupo no disponible en {problema.dias[dia]} {hora}")
            if posicion in problema.franjas_no_lectivas:
                razones[indice].add(f"Franja institucional no lectiva en {problema.dias[dia]} {hora}")
            if sesion.periodos_permitidos is not None and posicion not in sesion.periodos_permitidos:
                razones[indice].add(f"Fuera del periodo permitido en {problema.dias[dia]} {hora}")
            ocupacion_docente[(sesion.docente, dia, bloque)].append(indice)
            ocupacion_grupo[(sesion.grupo, dia, bloque)].append(indice)
            ocupacion_salon[(salon, dia, bloque)].append(indice)
            bloques_grupo[(sesion.grupo, dia)].add(bloque)
            bloques_docente[(sesion.docente, dia)].add(bloque)

    for etiqueta, ocupacion in (
        ("docente", ocupacion_docente), ("grupo", ocupacion_grupo),
        ("salón", ocupacion_salon),
    ):
        for clave, indices in ocupacion.items():
            if len(indices) < 2:
                continue
            _recurso, dia, bloque = clave
            ids = ", ".join(problema.sesiones[i].id for i in indices)
            mensaje = (
                f"Colisión de {etiqueta} en {problema.dias[dia]} "
                f"{problema.horas[bloque]} con {ids}"
            )
            for indice in indices:
                razones[indice].add(mensaje)

    def marcar_consecutivas(
        bloques_por_recurso: dict[tuple[str, int], set[int]],
        ocupacion: dict[tuple[str, int, int], list[int]], tipo: str,
    ) -> None:
        for (recurso, dia), bloques in bloques_por_recurso.items():
            entidad = problema.grupos[recurso] if tipo == "grupo" else problema.docentes[recurso]
            global_ = (
                problema.max_horas_consecutivas_grupo
                if tipo == "grupo" else problema.max_horas_consecutivas_docente
            )
            limite = entidad.max_horas_consecutivas or global_
            if limite is None:
                continue
            corrida: list[int] = []
            for bloque in sorted(bloques):
                if corrida and bloque != corrida[-1] + 1:
                    corrida = []
                corrida.append(bloque)
                if len(corrida) <= limite:
                    continue
                for indice in ocupacion[(recurso, dia, bloque)]:
                    razones[indice].add(
                        f"Máximo consecutivo de {tipo} excedido en {problema.dias[dia]}"
                    )

    marcar_consecutivas(bloques_grupo, ocupacion_grupo, "grupo")
    marcar_consecutivas(bloques_docente, ocupacion_docente, "docente")
    return razones


def diagnosticar_horario(
    problema: Problema, cromosoma: Cromosoma, *, max_alternativas: int = 3,
) -> DiagnosticoHorario:
    """Explica cada asignación dura y prueba reubicaciones individuales reales."""
    evaluacion = evaluar(problema, cromosoma)
    cotas = analizar_cotas_necesarias(problema)
    dominios = tuple(candidatos_estaticos(problema, i) for i in range(len(problema.sesiones)))
    sin_posicion = tuple(
        problema.sesiones[i].id for i, dominio in enumerate(dominios) if not dominio
    )
    if evaluacion.factible:
        estado = EstadoFactibilidad.SOLUCION_FACTIBLE
    elif sin_posicion or any(cota.contradiccion for cota in cotas):
        estado = EstadoFactibilidad.IMPOSIBILIDAD_DEMOSTRADA
    else:
        estado = EstadoFactibilidad.NO_ENCONTRADA

    razones = _razones_por_sesion(problema, cromosoma)
    conflictivas: list[AsignacionConflictiva] = []
    for indice in sorted(razones):
        sesion = problema.sesiones[indice]
        dia, inicio, salon = cromosoma[indice]
        alternativas: list[AlternativaAsignacion] = []
        for gen in dominios[indice]:
            if gen == cromosoma[indice]:
                continue
            genes = list(cromosoma)
            genes[indice] = gen
            candidata = evaluar(problema, tuple(genes))
            if candidata.duras >= evaluacion.duras:
                continue
            alt_dia, alt_hora, alt_salon = gen
            alternativas.append(AlternativaAsignacion(
                problema.dias[alt_dia], problema.horas[alt_hora],
                problema.salones[alt_salon].id, candidata.duras,
                candidata.penalizacion_blanda, evaluacion.duras - candidata.duras,
            ))
        alternativas.sort(key=lambda a: (
            a.duras_resultantes, a.penalizacion_blanda, a.dia, a.hora, a.salon,
        ))
        conflictivas.append(AsignacionConflictiva(
            indice, sesion.id, sesion.clase_id, sesion.materia,
            sesion.grupo, sesion.docente, problema.dias[dia],
            problema.horas[inicio], problema.salones[salon].id,
            tuple(sorted(razones[indice])), tuple(alternativas[:max_alternativas]),
        ))
    return DiagnosticoHorario(
        estado, evaluacion, tuple(conflictivas), cotas, sin_posicion,
    )


def formatear_diagnostico(diagnostico: DiagnosticoHorario) -> str:
    lineas = [
        f"Estado: {diagnostico.estado.value}",
        f"Violaciones duras: {diagnostico.evaluacion.duras}; "
        f"penalización blanda: {diagnostico.evaluacion.penalizacion_blanda}.",
    ]
    contradicciones = diagnostico.contradicciones_demostrables
    if diagnostico.sesiones_sin_posicion_estatica:
        lineas.append(
            "Sesiones sin ninguna posición estática válida: "
            + ", ".join(diagnostico.sesiones_sin_posicion_estatica)
        )
    if contradicciones:
        lineas.append("Contradicciones necesarias demostradas:")
        for cota in contradicciones:
            lineas.append(
                f"  - {cota.recurso}: demanda {cota.demanda_bloques} > "
                f"capacidad superior {cota.capacidad_superior}."
            )
    elif not diagnostico.evaluacion.factible:
        lineas.append(
            "Las cotas necesarias revisadas no demuestran imposibilidad; "
            "el resultado sólo acredita que la búsqueda no encontró solución."
        )
    for conflicto in diagnostico.asignaciones_conflictivas:
        lineas.append(
            f"\n{conflicto.sesion_id} · {conflicto.materia} · grupo {conflicto.grupo} · "
            f"docente {conflicto.docente} · {conflicto.dia} {conflicto.hora} · {conflicto.salon}"
        )
        lineas.extend(f"  - {razon}" for razon in conflicto.razones)
        if conflicto.alternativas:
            lineas.append("  Alternativas individuales que reducen violaciones:")
            for alternativa in conflicto.alternativas:
                lineas.append(
                    f"    · {alternativa.dia} {alternativa.hora} · {alternativa.salon}: "
                    f"duras {alternativa.duras_resultantes}, blanda "
                    f"{alternativa.penalizacion_blanda}."
                )
        else:
            lineas.append(
                "  Sin mejora mediante una sola reubicación; requiere un movimiento coordinado."
            )
    return "\n".join(lineas)
