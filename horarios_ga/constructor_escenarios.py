"""Construcción, validación y persistencia de escenarios académicos configurables.

El módulo produce exactamente el esquema consumido por :mod:`horarios_ga.datos`.
Las asignaciones testigo se usan sólo durante la generación con factibilidad
conocida y nunca se incluyen en el JSON devuelto.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .datos import cargar_datos, guardar_datos, problema_desde_datos
from .escenarios import huella_escenario
from .fitness import evaluar


DIAS_BASE = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
PERFILES = {
    "facil": {"disponibilidad": .92, "laboratorios": .25, "no_lectivos": .02, "coincidencia": .20},
    "moderado": {"disponibilidad": .80, "laboratorios": .30, "no_lectivos": .05, "coincidencia": .45},
    "dificil": {"disponibilidad": .66, "laboratorios": .22, "no_lectivos": .08, "coincidencia": .70},
}


@dataclass(frozen=True)
class ConfiguracionEscenario:
    nombre: str = "Escenario configurable"
    descripcion: str = ""
    modo: str = "semiautomatico"
    perfil: str = "moderado"
    docentes: int = 8
    grupos: int = 4
    materias: int = 8
    salones: int = 5
    sesiones_por_asignacion: int = 2
    duracion_sesion: int = 1
    estudiantes_por_grupo: int = 30
    dias_lectivos: int = 5
    hora_inicio: str = "07:00"
    hora_fin: str = "17:00"
    duracion_bloque_minutos: int = 60
    semilla: int = 42
    porcentaje_disponible: float | None = None
    proporcion_laboratorios: float | None = None
    coincidencia_disponibilidades: float | None = None
    cantidad_restricciones: int = 2
    factibilidad_conocida: bool = True
    estres: bool = False

    def validar(self) -> None:
        if not self.nombre.strip():
            raise ValueError("El escenario requiere un nombre")
        if self.modo not in {"manual", "semiautomatico", "automatico"}:
            raise ValueError("Modo de creación desconocido")
        if self.perfil not in {*PERFILES, "personalizado"}:
            raise ValueError("Perfil de dificultad desconocido")
        for nombre, valor, minimo, maximo in (
            ("docentes", self.docentes, 1, 500), ("grupos", self.grupos, 1, 300),
            ("materias", self.materias, 1, 1000), ("salones", self.salones, 1, 300),
            ("sesiones", self.sesiones_por_asignacion, 1, 20),
            ("duración", self.duracion_sesion, 1, 20),
            ("estudiantes", self.estudiantes_por_grupo, 1, 1000),
            ("días", self.dias_lectivos, 1, 7),
        ):
            if not minimo <= valor <= maximo:
                raise ValueError(f"{nombre.capitalize()} debe estar entre {minimo} y {maximo}")
        if self.duracion_bloque_minutos not in {15, 30, 45, 60, 90, 120}:
            raise ValueError("La duración del bloque debe ser 15, 30, 45, 60, 90 o 120 minutos")
        bloques = generar_horas(self.hora_inicio, self.hora_fin, self.duracion_bloque_minutos)
        if self.duracion_sesion > len(bloques):
            raise ValueError("La duración de sesión supera los bloques del día")
        for nombre, valor in (
            ("porcentaje disponible", self.porcentaje_disponible),
            ("proporción de laboratorios", self.proporcion_laboratorios),
            ("coincidencia de disponibilidades", self.coincidencia_disponibilidades),
        ):
            if valor is not None and not 0 <= valor <= 1:
                raise ValueError(f"{nombre.capitalize()} debe estar entre 0 y 1")
        if self.cantidad_restricciones < 0:
            raise ValueError("La cantidad de restricciones no puede ser negativa")

    @property
    def asignaciones_estimadas(self) -> int:
        return max(self.materias, self.grupos)

    @property
    def sesiones_estimadas(self) -> int:
        return self.asignaciones_estimadas * self.sesiones_por_asignacion


@dataclass(frozen=True)
class IncidenciaValidacion:
    nivel: str
    codigo: str
    mensaje: str


@dataclass(frozen=True)
class ResultadoValidacionEscenario:
    incidencias: tuple[IncidenciaValidacion, ...]
    resumen: dict[str, Any]

    @property
    def errores(self) -> tuple[IncidenciaValidacion, ...]:
        return tuple(i for i in self.incidencias if i.nivel == "error")

    @property
    def advertencias(self) -> tuple[IncidenciaValidacion, ...]:
        return tuple(i for i in self.incidencias if i.nivel == "advertencia")

    @property
    def correcto(self) -> bool:
        return not self.errores


@dataclass(frozen=True)
class RegistroEscenarioGenerado:
    identificador: str
    semilla: int
    ruta: Path
    huella: str
    resumen: dict[str, Any]
    valido: bool


def generar_horas(inicio: str, fin: str, duracion_minutos: int) -> list[str]:
    try:
        actual = datetime.strptime(inicio, "%H:%M")
        limite = datetime.strptime(fin, "%H:%M")
    except ValueError as exc:
        raise ValueError("Las horas deben usar formato HH:MM") from exc
    if limite <= actual:
        raise ValueError("La hora final debe ser posterior a la inicial")
    paso = timedelta(minutes=duracion_minutos)
    horas: list[str] = []
    while actual < limite:
        if actual + paso > limite:
            raise ValueError("El intervalo diario debe ser divisible entre la duración del bloque")
        horas.append(actual.strftime("%H:%M"))
        actual += paso
    return horas


def _mapa(bloques: set[tuple[int, int]], dias: list[str], horas: list[str]) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for dia, bloque in sorted(bloques):
        resultado.setdefault(dias[dia], []).append(horas[bloque])
    return resultado


def crear_escenario_manual(nombre: str = "Nuevo escenario manual") -> dict[str, Any]:
    """Crea una base mínima válida que puede ampliarse con el editor académico."""
    datos = {
        "descripcion": "Escenario manual editable",
        "dias": ["Lunes"],
        "horas": ["08:00", "09:00"],
        "salones": [{"id": "A01", "nombre": "Aula 01", "capacidad": 30, "tipo": "aula"}],
        "grupos": [{"id": "G01", "nombre": "Grupo 01", "alumnos": 25}],
        "docentes": [{"id": "D01", "nombre": "Docente 01", "no_disponible": {}, "preferidos": {}}],
        "clases": [{
            "id": "C001", "materia": "Materia 01", "grupo": "G01", "docente": "D01",
            "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula",
        }],
        "restricciones": {"franjas_no_lectivas": {}, "umbral_jornada_larga": 2},
        "metadatos": {
            "nombre": nombre, "tipo": "manual", "semilla": None,
            "duracion_bloque_minutos": 60, "generador": "HorariosGeneticos-Fase7",
            "factibilidad_testigo_validada": False,
        },
    }
    problema_desde_datos(deepcopy(datos))
    return datos


def _max_consecutivos(bloques: set[tuple[int, int]]) -> int:
    por_dia: dict[int, list[int]] = defaultdict(list)
    for dia, bloque in bloques:
        por_dia[dia].append(bloque)
    maximo = 1
    for lista in por_dia.values():
        corrida = 0
        anterior = None
        for bloque in sorted(lista):
            corrida = corrida + 1 if anterior is not None and bloque == anterior + 1 else 1
            maximo = max(maximo, corrida)
            anterior = bloque
    return maximo


def generar_escenario_configurable(config: ConfiguracionEscenario) -> dict[str, Any]:
    """Genera un escenario estructuralmente válido y reproducible."""
    config.validar()
    rng = random.Random(config.semilla)
    perfil = PERFILES.get(config.perfil, PERFILES["moderado"])
    disponible = config.porcentaje_disponible if config.porcentaje_disponible is not None else perfil["disponibilidad"]
    proporcion_lab = config.proporcion_laboratorios if config.proporcion_laboratorios is not None else perfil["laboratorios"]
    coincidencia = config.coincidencia_disponibilidades if config.coincidencia_disponibilidades is not None else perfil["coincidencia"]
    dias = list(DIAS_BASE[:config.dias_lectivos])
    horas = generar_horas(config.hora_inicio, config.hora_fin, config.duracion_bloque_minutos)
    if config.sesiones_estimadas * config.duracion_sesion > config.grupos * len(dias) * len(horas):
        raise ValueError("La demanda por grupo excede la capacidad temporal total configurada")

    grupos = [{
        "id": f"G{i + 1:03d}", "nombre": f"Grupo {i + 1:03d}",
        "alumnos": max(1, config.estudiantes_por_grupo + rng.randint(-4, 4)),
    } for i in range(config.grupos)]
    docentes = [{
        "id": f"D{i + 1:03d}", "nombre": f"Docente {i + 1:03d}",
        "no_disponible": {}, "preferidos": {},
    } for i in range(config.docentes)]
    cantidad_labs = min(config.salones, max(1 if proporcion_lab > 0 else 0, round(config.salones * proporcion_lab)))
    salones = []
    capacidad_maxima = max(g["alumnos"] for g in grupos) + 10
    for i in range(config.salones):
        tipo = "laboratorio" if i < cantidad_labs else "aula"
        salones.append({
            "id": f"{'LAB' if tipo == 'laboratorio' else 'A'}{i + 1:03d}",
            "nombre": f"{'Laboratorio' if tipo == 'laboratorio' else 'Aula'} {i + 1:03d}",
            "capacidad": capacidad_maxima + (i % 3) * 5, "tipo": tipo,
        })
    if cantidad_labs == config.salones:
        # Un único vocabulario de tipos sigue siendo válido; las clases se adaptan.
        tipo_normal = "laboratorio"
    else:
        tipo_normal = "aula"

    universo = {(d, h) for d in range(len(dias)) for h in range(len(horas))}
    cantidad_no_lectivos = min(
        max(0, len(universo) - config.duracion_sesion),
        round(len(universo) * perfil["no_lectivos"] * min(3, config.cantidad_restricciones)),
    )
    candidatos_no_lectivos = sorted(universo)
    rng.shuffle(candidatos_no_lectivos)
    no_lectivos = set(candidatos_no_lectivos[:cantidad_no_lectivos])

    ocupacion_grupo: set[tuple[str, int, int]] = set()
    ocupacion_docente: set[tuple[str, int, int]] = set()
    ocupacion_salon: set[tuple[str, int, int]] = set()
    ocupados_grupo: dict[str, set[tuple[int, int]]] = defaultdict(set)
    ocupados_docente: dict[str, set[tuple[int, int]]] = defaultdict(set)
    testigo: list[tuple[int, int, int]] = []
    testigo_por_clase: dict[str, set[tuple[int, int]]] = defaultdict(set)
    clases: list[dict[str, Any]] = []
    asignaciones = config.asignaciones_estimadas

    for i in range(asignaciones):
        grupo = grupos[i % len(grupos)]
        docente = docentes[i % len(docentes)]
        materia_numero = i % config.materias
        clase_id = f"C{i + 1:04d}"
        usar_lab = cantidad_labs > 0 and materia_numero % max(2, round(1 / max(.01, proporcion_lab))) == 0
        tipo = "laboratorio" if usar_lab else tipo_normal
        compatibles = [(indice, salon) for indice, salon in enumerate(salones) if salon["tipo"] == tipo]
        if not compatibles:
            tipo = tipo_normal
            compatibles = [(indice, salon) for indice, salon in enumerate(salones) if salon["tipo"] == tipo]
        for _repeticion in range(config.sesiones_por_asignacion):
            candidatos = [
                (dia, inicio, indice_salon, salon)
                for dia in range(len(dias))
                for inicio in range(len(horas) - config.duracion_sesion + 1)
                for indice_salon, salon in compatibles
            ]
            rng.shuffle(candidatos)
            elegido = None
            for dia, inicio, indice_salon, salon in candidatos:
                bloques = range(inicio, inicio + config.duracion_sesion)
                if any((dia, b) in no_lectivos for b in bloques):
                    continue
                if any((grupo["id"], dia, b) in ocupacion_grupo for b in bloques):
                    continue
                if any((docente["id"], dia, b) in ocupacion_docente for b in bloques):
                    continue
                if any((salon["id"], dia, b) in ocupacion_salon for b in bloques):
                    continue
                elegido = (dia, inicio, indice_salon, salon)
                break
            if elegido is None:
                raise ValueError(
                    "No fue posible construir una asignación testigo con las cantidades configuradas; "
                    "aumenta días, bloques, docentes o salones"
                )
            dia, inicio, indice_salon, salon = elegido
            for bloque in range(inicio, inicio + config.duracion_sesion):
                ocupacion_grupo.add((grupo["id"], dia, bloque))
                ocupacion_docente.add((docente["id"], dia, bloque))
                ocupacion_salon.add((salon["id"], dia, bloque))
                ocupados_grupo[grupo["id"]].add((dia, bloque))
                ocupados_docente[docente["id"]].add((dia, bloque))
                testigo_por_clase[clase_id].add((dia, bloque))
            testigo.append((dia, inicio, indice_salon))
        clase: dict[str, Any] = {
            "id": clase_id, "materia_id": f"M{materia_numero + 1:04d}",
            "materia": f"Materia {materia_numero + 1:04d}",
            "grupo": grupo["id"], "docente": docente["id"],
            "sesiones_semana": config.sesiones_por_asignacion,
            "duracion_bloques": config.duracion_sesion, "tipo_salon": tipo,
        }
        clases.append(clase)

    compartidos = set(rng.sample(sorted(universo), k=min(len(universo), round((1 - disponible) * len(universo) * coincidencia))))
    for grupo in grupos:
        libres = list(universo - ocupados_grupo[grupo["id"]] - no_lectivos)
        rng.shuffle(libres)
        objetivo = round((1 - disponible) * len(universo))
        no_disponibles = (compartidos | set(libres)) - ocupados_grupo[grupo["id"]]
        grupo["no_disponible"] = _mapa(set(sorted(no_disponibles)[:objetivo]), dias, horas)
        if config.cantidad_restricciones >= 2:
            grupo["max_horas_consecutivas"] = max(2, _max_consecutivos(ocupados_grupo[grupo["id"]]))
    for docente in docentes:
        ocupados = ocupados_docente[docente["id"]]
        libres = list(universo - ocupados - no_lectivos)
        rng.shuffle(libres)
        objetivo = round((1 - disponible) * len(universo))
        no_disponibles = (compartidos | set(libres)) - ocupados
        if config.estres and ocupados:
            no_disponibles.add(sorted(ocupados)[0])
        docente["no_disponible"] = _mapa(set(sorted(no_disponibles)[:objetivo]), dias, horas)
        docente["preferidos"] = _mapa(ocupados, dias, horas)
        if config.cantidad_restricciones >= 2 and ocupados:
            docente["max_horas_consecutivas"] = max(2, _max_consecutivos(ocupados))
    if config.cantidad_restricciones >= 1:
        for i, clase in enumerate(clases):
            if i % 3 == 0:
                permitidos = set(universo - no_lectivos)
                # Retira algunos bloques sin tocar la asignación testigo.
                retirables = list(permitidos - testigo_por_clase[clase["id"]])
                rng.shuffle(retirables)
                permitidos -= set(retirables[:max(0, len(retirables) // 8)])
                clase["periodos_permitidos"] = _mapa(permitidos, dias, horas)

    datos: dict[str, Any] = {
        "descripcion": config.descripcion or f"Escenario {config.modo} generado con perfil {config.perfil}",
        "dias": dias, "horas": horas, "salones": salones, "grupos": grupos,
        "docentes": docentes, "clases": clases,
        "restricciones": {
            "franjas_no_lectivas": _mapa(no_lectivos, dias, horas),
            "umbral_jornada_larga": max(2, round(len(horas) * .7)),
        },
        "metadatos": {
            "nombre": config.nombre, "tipo": f"{config.modo}_{'estres' if config.estres else config.perfil}",
            "semilla": config.semilla, "generador": "HorariosGeneticos-Fase7",
            "duracion_bloque_minutos": config.duracion_bloque_minutos,
            "factibilidad_testigo_validada": bool(config.factibilidad_conocida and not config.estres),
            "parametros_generacion": asdict(config),
        },
    }
    problema = problema_desde_datos(deepcopy(datos))
    if config.factibilidad_conocida and not config.estres:
        evaluacion = evaluar(problema, tuple(testigo))
        if not evaluacion.factible:
            raise AssertionError("El testigo interno no cumple: " + "; ".join(evaluacion.razones_no_factible()))
    return datos


def resumen_escenario(datos: dict[str, Any]) -> dict[str, Any]:
    problema = problema_desde_datos(deepcopy(datos))
    materias = {str(c.get("materia_id", c.get("materia", ""))) for c in datos["clases"]}
    demanda = sum(s.duracion for s in problema.sesiones)
    no_lectivos = len(problema.franjas_no_lectivas)
    capacidad_temporal = len(problema.dias) * len(problema.horas) * len(problema.salones)
    return {
        "nombre": str(datos.get("metadatos", {}).get("nombre", datos.get("descripcion", "Sin nombre"))),
        "docentes": len(problema.docentes), "grupos": len(problema.grupos),
        "materias": len(materias), "asignaciones": len(datos["clases"]),
        "sesiones": len(problema.sesiones), "salones": len(problema.salones),
        "dias": len(problema.dias), "bloques_por_dia": len(problema.horas),
        "bloques_disponibles_institucionales": len(problema.dias) * len(problema.horas) - no_lectivos,
        "demanda_bloques": demanda, "capacidad_temporal_aproximada": capacidad_temporal,
        "franjas_no_lectivas": no_lectivos,
        "huella": huella_escenario(datos),
    }


def validar_escenario_detallado(datos: dict[str, Any]) -> ResultadoValidacionEscenario:
    incidencias: list[IncidenciaValidacion] = []

    def agregar(nivel: str, codigo: str, mensaje: str) -> None:
        incidencias.append(IncidenciaValidacion(nivel, codigo, mensaje))

    requeridas = ("dias", "horas", "salones", "grupos", "docentes", "clases")
    for clave in requeridas:
        if clave not in datos:
            agregar("error", "seccion_faltante", f"Falta la sección obligatoria: {clave}")
        elif not isinstance(datos[clave], list):
            agregar("error", "tipo_invalido", f"La sección {clave} debe ser una lista")
    if any(i.nivel == "error" for i in incidencias):
        return ResultadoValidacionEscenario(tuple(incidencias), {})

    ids: dict[str, set[str]] = {}
    for seccion in ("salones", "grupos", "docentes", "clases"):
        vistos: set[str] = set()
        for registro in datos[seccion]:
            identificador = str(registro.get("id", "")).strip() if isinstance(registro, dict) else ""
            if not identificador:
                agregar("error", "id_vacio", f"Hay un registro sin identificador en {seccion}")
            elif identificador in vistos:
                agregar("error", "id_duplicado", f"Identificador duplicado en {seccion}: {identificador}")
            vistos.add(identificador)
        ids[seccion] = vistos
    for clase in datos["clases"]:
        if not isinstance(clase, dict):
            agregar("error", "clase_invalida", "Cada clase debe ser un objeto")
            continue
        cid = str(clase.get("id", "?"))
        if str(clase.get("docente", "")) not in ids["docentes"]:
            agregar("error", "docente_inexistente", f"La clase {cid} referencia un docente inexistente")
        if str(clase.get("grupo", "")) not in ids["grupos"]:
            agregar("error", "grupo_inexistente", f"La clase {cid} referencia un grupo inexistente")
        try:
            duracion = int(clase.get("duracion_bloques", 1))
            sesiones = int(clase.get("sesiones_semana", 1))
            if duracion < 1 or sesiones < 1 or duracion > len(datos["horas"]):
                agregar("error", "sesion_invalida", f"Duración/sesiones inválidas en {cid}")
        except (TypeError, ValueError):
            agregar("error", "sesion_invalida", f"Duración/sesiones no numéricas en {cid}")
    if incidencias and any(i.nivel == "error" for i in incidencias):
        return ResultadoValidacionEscenario(tuple(incidencias), {})
    try:
        problema = problema_desde_datos(deepcopy(datos))
    except (ValueError, KeyError, TypeError) as exc:
        agregar("error", "modelo_invalido", str(exc))
        return ResultadoValidacionEscenario(tuple(incidencias), {})

    universo = {(d, h) for d in range(len(problema.dias)) for h in range(len(problema.horas))}
    for docente in problema.docentes.values():
        if docente.no_disponible >= universo:
            agregar("advertencia", "disponibilidad_vacia", f"El docente {docente.id} no tiene bloques disponibles")
    for grupo in problema.grupos.values():
        if grupo.no_disponible >= universo:
            agregar("advertencia", "disponibilidad_vacia", f"El grupo {grupo.id} no tiene bloques disponibles")
    for indice, sesion in enumerate(problema.sesiones):
        docente = problema.docentes[sesion.docente]
        grupo = problema.grupos[sesion.grupo]
        posibles = 0
        for dia in range(len(problema.dias)):
            for inicio in range(len(problema.horas) - sesion.duracion + 1):
                bloques = {(dia, h) for h in range(inicio, inicio + sesion.duracion)}
                if bloques & docente.no_disponible or bloques & grupo.no_disponible or bloques & problema.franjas_no_lectivas:
                    continue
                if sesion.periodos_permitidos is not None and not bloques <= sesion.periodos_permitidos:
                    continue
                posibles += len(problema.salones_validos[indice])
        if posibles == 0:
            agregar("advertencia", "sin_ubicacion", f"La sesión {sesion.id} no tiene ubicación estática posible")
    demanda_grupo = Counter()
    demanda_docente = Counter()
    for sesion in problema.sesiones:
        demanda_grupo[sesion.grupo] += sesion.duracion
        demanda_docente[sesion.docente] += sesion.duracion
    capacidad = len(problema.dias) * len(problema.horas) - len(problema.franjas_no_lectivas)
    for grupo, demanda in demanda_grupo.items():
        disponibles = capacidad - len(problema.grupos[grupo].no_disponible)
        if demanda > disponibles:
            agregar("advertencia", "demanda_excesiva", f"El grupo {grupo} demanda {demanda} bloques y dispone aproximadamente de {max(0, disponibles)}")
    for docente, demanda in demanda_docente.items():
        disponibles = capacidad - len(problema.docentes[docente].no_disponible)
        if demanda > disponibles:
            agregar("advertencia", "demanda_excesiva", f"El docente {docente} demanda {demanda} bloques y dispone aproximadamente de {max(0, disponibles)}")
    if not incidencias:
        agregar("correcto", "estructura_valida", "El escenario supera las validaciones estructurales implementadas")
    elif not any(i.nivel == "error" for i in incidencias):
        agregar("correcto", "estructura_valida", "El escenario es interpretable; revisa las advertencias")
    return ResultadoValidacionEscenario(tuple(incidencias), resumen_escenario(datos))


def nombre_archivo_seguro(nombre: str) -> str:
    limpio = re.sub(r"[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ_-]+", "_", nombre.strip()).strip("_.")
    if not limpio:
        raise ValueError("El nombre no produce un archivo válido")
    return limpio[:100] + ".json"


class GestorEscenarios:
    def __init__(self, directorio: str | Path):
        self.directorio = Path(directorio).resolve()
        self.directorio.mkdir(parents=True, exist_ok=True)

    def listar(self) -> tuple[Path, ...]:
        return tuple(sorted((p for p in self.directorio.glob("*.json") if p.is_file()), key=lambda p: p.name.lower()))

    def _destino(self, nombre: str) -> Path:
        destino = (self.directorio / nombre_archivo_seguro(nombre)).resolve()
        if destino.parent != self.directorio:
            raise ValueError("La ruta debe permanecer dentro del directorio de escenarios")
        return destino

    def guardar(self, nombre: str, datos: dict[str, Any], *, sobrescribir: bool = False) -> Path:
        destino = self._destino(nombre)
        if destino.exists() and not sobrescribir:
            raise FileExistsError(f"Ya existe el escenario {destino.name}")
        return guardar_datos(datos, destino)

    def duplicar(self, origen: str | Path, nombre_nuevo: str) -> Path:
        datos = cargar_datos(origen)
        datos.setdefault("metadatos", {})["nombre"] = nombre_nuevo
        return self.guardar(nombre_nuevo, datos)

    def renombrar(self, origen: str | Path, nombre_nuevo: str) -> Path:
        origen = Path(origen).resolve()
        if origen.parent != self.directorio:
            raise ValueError("Sólo se pueden renombrar escenarios administrados")
        datos = cargar_datos(origen)
        datos.setdefault("metadatos", {})["nombre"] = nombre_nuevo
        destino = self.guardar(nombre_nuevo, datos)
        origen.unlink()
        return destino

    def eliminar(self, ruta: str | Path) -> None:
        objetivo = Path(ruta).resolve()
        if objetivo.parent != self.directorio or objetivo.suffix.lower() != ".json":
            raise ValueError("Sólo se pueden eliminar JSON administrados")
        objetivo.unlink()


def generar_lote(
    config: ConfiguracionEscenario,
    cantidad: int,
    directorio: str | Path,
    *,
    semilla_inicial: int | None = None,
    variacion: float = 0.0,
    debe_cancelar: Callable[[], bool] | None = None,
    al_generar: Callable[[RegistroEscenarioGenerado], None] | None = None,
) -> tuple[RegistroEscenarioGenerado, ...]:
    if not 1 <= cantidad <= 200:
        raise ValueError("La cantidad del lote debe estar entre 1 y 200")
    if not 0 <= variacion <= .5:
        raise ValueError("La variación debe estar entre 0 y 0.5")
    gestor = GestorEscenarios(directorio)
    semilla_base = config.semilla if semilla_inicial is None else semilla_inicial
    rng_variacion = random.Random(semilla_base ^ 0xF7)
    registros: list[RegistroEscenarioGenerado] = []
    for indice in range(cantidad):
        if debe_cancelar is not None and debe_cancelar():
            break
        factor = 1 + rng_variacion.uniform(-variacion, variacion)
        cfg = replace(
            config,
            nombre=f"{config.nombre} {indice + 1:03d}",
            semilla=semilla_base + indice,
            grupos=max(1, round(config.grupos * factor)),
            docentes=max(1, round(config.docentes * factor)),
        )
        datos = generar_escenario_configurable(cfg)
        validacion = validar_escenario_detallado(datos)
        ruta = gestor.guardar(cfg.nombre, datos)
        registro = RegistroEscenarioGenerado(
            f"ESC-{indice + 1:04d}", cfg.semilla, ruta,
            huella_escenario(datos), validacion.resumen, validacion.correcto,
        )
        registros.append(registro)
        if al_generar is not None:
            al_generar(registro)
    manifiesto = {
        "generador": "HorariosGeneticos-Fase7", "cantidad_solicitada": cantidad,
        "cantidad_generada": len(registros), "cancelado": len(registros) < cantidad,
        "configuracion_base": asdict(config),
        "escenarios": [{**asdict(r), "ruta": str(r.ruta)} for r in registros],
    }
    (gestor.directorio / "manifiesto_lote.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8",
    )
    return tuple(registros)
