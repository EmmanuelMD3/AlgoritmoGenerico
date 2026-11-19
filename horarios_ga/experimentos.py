"""Ejecución reproducible, registro y exportación de experimentos."""
from __future__ import annotations

import csv
import html
import json
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable

from .baselines import ejecutar_busqueda_aleatoria, ejecutar_heuristica_constructiva
from .datos import problema_desde_datos
from .evolucion import RegistroEvolucion, VERSION_EVOLUCION
from .estadisticas import conclusiones_descriptivas, exportar_graficas, resumir_ejecuciones
from .escenarios import huella_escenario
from .fitness import Evaluacion
from .genetico import Configuracion, EjecucionCancelada, Resultado, ejecutar


METODOS = {
    "genetico": "Algoritmo genético",
    "hibrido": "Algoritmo genético híbrido",
    "aleatorio": "Búsqueda aleatoria",
    "constructivo": "Heurística constructiva",
}


@dataclass(frozen=True)
class ConfiguracionExperimento:
    nombre: str = "Comparación de métodos"
    descripcion: str = ""
    escenario: str = "pequeno"
    repeticiones: int = 5
    metodos: tuple[str, ...] = ("genetico", "aleatorio", "constructivo")
    genetico: Configuracion = field(default_factory=lambda: Configuracion(poblacion=40, generaciones=40))
    hibrido: Configuracion = field(default_factory=lambda: Configuracion(
        poblacion=40, generaciones=40, variante="hibrido",
        inicializacion_heuristica=True, busqueda_local=True, mutacion_adaptativa=True,
    ))
    semilla_inicial: int = 42
    modo: str = "comparacion"
    variantes: tuple[tuple[str, Configuracion], ...] = ()
    repeticion_evolucion: int = 1

    def validar(self) -> None:
        if not self.nombre.strip():
            raise ValueError("El experimento requiere un nombre")
        if not 1 <= self.repeticiones <= 100:
            raise ValueError("Las repeticiones deben estar entre 1 y 100")
        if not 0 <= self.repeticion_evolucion <= self.repeticiones:
            raise ValueError("La repetición evolutiva debe ser 0 o estar dentro del experimento")
        if self.modo not in {"comparacion", "parametros", "ablacion"}:
            raise ValueError("Modo experimental desconocido")
        if self.modo == "comparacion":
            if not self.metodos or any(m not in METODOS for m in self.metodos):
                raise ValueError("Selecciona al menos un método válido")
        elif not self.variantes:
            raise ValueError("El análisis de parámetros requiere configuraciones")
        self.genetico.validar()
        self.hibrido.validar()
        for _, variante in self.variantes:
            variante.validar()


@dataclass(frozen=True)
class ProgresoExperimento:
    estado: str
    experimento: str
    metodo: str
    repeticion: int
    repeticiones: int
    completadas: int
    total: int
    ultimo_resultado: str = ""


@dataclass(frozen=True)
class RegistroEjecucion:
    id: str
    fecha: str
    metodo: str
    etiqueta_metodo: str
    escenario: str
    repeticion: int
    semilla: int
    configuracion: dict[str, Any]
    presupuesto_objetivo: int
    evaluaciones: int
    duracion: float
    motivo_parada: str
    factible: bool
    duras: int
    penalizacion_blanda: int
    fitness: int
    evaluaciones_hasta_factible: int | None
    generacion_primera_factible: int | None
    generaciones_ejecutadas: int | None
    desglose_duro: dict[str, int]
    desglose_blando: dict[str, int]
    historial: tuple[dict[str, Any], ...] = ()
    cromosoma: tuple[tuple[int, int, int], ...] = ()
    evolucion: RegistroEvolucion | None = None
    error: str | None = None
    evaluaciones_inicializacion: int = 0
    evaluaciones_evolucion: int = 0
    evaluaciones_busqueda_local: int = 0
    tiempo_inicializacion: float = 0.0
    tiempo_evolucion: float = 0.0
    tiempo_busqueda_local: float = 0.0


@dataclass(frozen=True)
class ResultadoExperimento:
    id: str
    inicio: str
    fin: str
    estado: str
    configuracion: ConfiguracionExperimento
    escenario_datos: dict[str, Any]
    huella_escenario: str
    ejecuciones: tuple[RegistroEjecucion, ...]
    duracion: float


@dataclass(frozen=True)
class ProgresoLoteEscenarios:
    """Progreso de un experimento repetido sobre escenarios independientes."""

    escenario: str
    indice_escenario: int
    total_escenarios: int
    progreso: ProgresoExperimento


@dataclass(frozen=True)
class ResultadoLoteEscenarios:
    """Resultados separados; deliberadamente no contiene estadísticas mezcladas."""

    nombres: tuple[str, ...]
    resultados: tuple[ResultadoExperimento, ...]
    cancelado: bool


def generar_variantes_un_parametro(
    base: Configuracion,
    *,
    poblaciones: Iterable[int] = (),
    mutaciones: Iterable[float] = (),
    cruzas: Iterable[float] = (),
    generaciones: Iterable[int] = (),
) -> tuple[tuple[str, Configuracion], ...]:
    """Cambia un parámetro a la vez y conserva una única configuración base."""
    variantes: list[tuple[str, Configuracion]] = [("Base", base)]
    vistos = {base}
    for campo, valores in (
        ("poblacion", poblaciones),
        ("prob_mutacion", mutaciones),
        ("prob_cruza", cruzas),
        ("generaciones", generaciones),
    ):
        for valor in valores:
            candidata = replace(base, **{campo: valor})
            if candidata in vistos:
                continue
            candidata.validar()
            vistos.add(candidata)
            variantes.append((f"{campo}={valor}", candidata))
    return tuple(variantes)


def generar_ablaciones(base: Configuracion) -> tuple[tuple[str, Configuracion], ...]:
    """Configuraciones A–E para atribuir el efecto de cada componente híbrido."""
    comun = replace(base, variante="hibrido")
    return (
        ("A · clásico", replace(base, variante="clasico")),
        ("B · + inicialización", replace(
            comun, inicializacion_heuristica=True,
            busqueda_local=False, mutacion_adaptativa=False,
        )),
        ("C · + búsqueda local", replace(
            comun, inicializacion_heuristica=False,
            busqueda_local=True, mutacion_adaptativa=False,
        )),
        ("D · + mutación adaptativa", replace(
            comun, inicializacion_heuristica=False,
            busqueda_local=False, mutacion_adaptativa=True,
        )),
        ("E · híbrido completo", replace(
            comun, inicializacion_heuristica=True,
            busqueda_local=True, mutacion_adaptativa=True,
        )),
    )


def presupuesto_nominal(configuracion: Configuracion) -> int:
    """Referencia previa a la corrida: población por generaciones observadas."""
    return configuracion.poblacion * (configuracion.generaciones + 1)


def estimar_experimento(configuracion: ConfiguracionExperimento) -> dict[str, int]:
    configuracion.validar()
    if configuracion.modo in {"parametros", "ablacion"}:
        ejecuciones = len(configuracion.variantes) * configuracion.repeticiones
        evaluaciones = sum(
            presupuesto_nominal(variante) * configuracion.repeticiones
            for _, variante in configuracion.variantes
        )
    else:
        ejecuciones = len(configuracion.metodos) * configuracion.repeticiones
        evaluaciones = presupuesto_nominal(configuracion.genetico) * ejecuciones
    return {"configuraciones": len(configuracion.variantes) if configuracion.modo == "parametros" else 1,
            "ejecuciones": ejecuciones, "evaluaciones_nominales": evaluaciones}


def _registro_desde_ga(
    resultado: Resultado,
    *,
    contador: int,
    primera_factible: int | None,
    duracion: float,
    escenario: str,
    repeticion: int,
    semilla: int,
    etiqueta: str,
    presupuesto: int,
    evolucion: RegistroEvolucion | None = None,
) -> RegistroEjecucion:
    evaluacion = resultado.evaluacion
    estadisticas = resultado.estadisticas
    primera_generacion = next((r.generacion for r in resultado.historial if r.factible), None)
    return RegistroEjecucion(
        id=str(uuid.uuid4()), fecha=datetime.now().astimezone().isoformat(timespec="seconds"),
        metodo="hibrido" if resultado.configuracion.variante == "hibrido" else "genetico",
        etiqueta_metodo=etiqueta, escenario=escenario,
        repeticion=repeticion, semilla=semilla, configuracion=asdict(resultado.configuracion),
        presupuesto_objetivo=presupuesto, evaluaciones=contador, duracion=duracion,
        motivo_parada=resultado.motivo_parada, factible=evaluacion.factible,
        duras=evaluacion.duras, penalizacion_blanda=evaluacion.penalizacion_blanda,
        fitness=evaluacion.fitness, evaluaciones_hasta_factible=primera_factible,
        generacion_primera_factible=primera_generacion,
        generaciones_ejecutadas=resultado.historial[-1].generacion if resultado.historial else 0,
        desglose_duro=evaluacion.desglose_duro(), desglose_blando=evaluacion.desglose_blando(),
        historial=tuple(asdict(r) for r in resultado.historial), cromosoma=resultado.cromosoma,
        evolucion=evolucion,
        evaluaciones_inicializacion=estadisticas.evaluaciones_inicializacion,
        evaluaciones_evolucion=max(
            0, estadisticas.evaluaciones_totales
            - estadisticas.evaluaciones_inicializacion
            - estadisticas.evaluaciones_busqueda_local,
        ),
        evaluaciones_busqueda_local=estadisticas.evaluaciones_busqueda_local,
        tiempo_inicializacion=estadisticas.tiempo_inicializacion,
        tiempo_evolucion=estadisticas.tiempo_evolucion,
        tiempo_busqueda_local=estadisticas.tiempo_busqueda_local,
    )


def _ejecutar_ga(
    problema: Any,
    configuracion: Configuracion,
    escenario: str,
    repeticion: int,
    etiqueta: str,
    cancelar: Callable[[], bool] | None,
    escenario_datos: dict[str, Any],
    capturar_evolucion: bool = False,
) -> RegistroEjecucion:
    contador = 0
    primera_factible: int | None = None
    instantaneas = []

    def contar(evaluacion: Evaluacion) -> None:
        nonlocal contador, primera_factible
        contador += 1
        if primera_factible is None and evaluacion.factible:
            primera_factible = contador

    inicio = perf_counter()
    try:
        resultado = ejecutar(
            problema, configuracion, debe_cancelar=cancelar, al_evaluar=contar,
            callback_instantanea=instantaneas.append if capturar_evolucion else None,
        )
    except EjecucionCancelada as exc:
        resultado = exc.resultado
    duracion = perf_counter() - inicio
    evolucion = RegistroEvolucion(
        VERSION_EVOLUCION, configuracion, escenario_datos,
        tuple(s.id for s in problema.sesiones), tuple(instantaneas),
        resultado.motivo_parada, resultado.motivo_parada == "cancelada",
    ) if capturar_evolucion else None
    return _registro_desde_ga(
        resultado, contador=contador, primera_factible=primera_factible,
        duracion=duracion, escenario=escenario, repeticion=repeticion,
        semilla=configuracion.semilla, etiqueta=etiqueta,
        presupuesto=presupuesto_nominal(configuracion),
        evolucion=evolucion,
    )


def _registro_desde_baseline(
    resultado: Any,
    *,
    escenario: str,
    repeticion: int,
    semilla: int,
    etiqueta: str,
    presupuesto: int,
) -> RegistroEjecucion:
    evaluacion = resultado.evaluacion
    return RegistroEjecucion(
        id=str(uuid.uuid4()), fecha=datetime.now().astimezone().isoformat(timespec="seconds"),
        metodo=resultado.metodo, etiqueta_metodo=etiqueta, escenario=escenario,
        repeticion=repeticion, semilla=semilla,
        configuracion={"presupuesto_evaluaciones": presupuesto},
        presupuesto_objetivo=presupuesto, evaluaciones=resultado.evaluaciones,
        duracion=resultado.duracion, motivo_parada=resultado.motivo_parada,
        factible=evaluacion.factible, duras=evaluacion.duras,
        penalizacion_blanda=evaluacion.penalizacion_blanda, fitness=evaluacion.fitness,
        evaluaciones_hasta_factible=resultado.evaluacion_primera_factible,
        generacion_primera_factible=None, generaciones_ejecutadas=None,
        desglose_duro=evaluacion.desglose_duro(), desglose_blando=evaluacion.desglose_blando(),
        cromosoma=resultado.cromosoma,
    )


def _registro_error(
    metodo: str, etiqueta: str, escenario: str, repeticion: int, semilla: int,
    configuracion: dict[str, Any], presupuesto: int, error: Exception,
) -> RegistroEjecucion:
    return RegistroEjecucion(
        id=str(uuid.uuid4()), fecha=datetime.now().astimezone().isoformat(timespec="seconds"),
        metodo=metodo, etiqueta_metodo=etiqueta, escenario=escenario,
        repeticion=repeticion, semilla=semilla, configuracion=configuracion,
        presupuesto_objetivo=presupuesto, evaluaciones=0, duracion=0.0,
        motivo_parada="error", factible=False, duras=0, penalizacion_blanda=0,
        fitness=0, evaluaciones_hasta_factible=None, generacion_primera_factible=None,
        generaciones_ejecutadas=None, desglose_duro={}, desglose_blando={}, error=str(error),
    )


def ejecutar_experimento(
    configuracion: ConfiguracionExperimento,
    escenario_datos: dict[str, Any],
    *,
    al_progresar: Callable[[ProgresoExperimento], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
) -> ResultadoExperimento:
    """Ejecuta comparaciones sin depender de Tkinter y conserva errores parciales."""
    configuracion.validar()
    problema = problema_desde_datos(escenario_datos)
    huella = huella_escenario(escenario_datos)
    inicio_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    inicio = perf_counter()
    ejecuciones: list[RegistroEjecucion] = []
    estimacion = estimar_experimento(configuracion)
    total = estimacion["ejecuciones"]
    cancelado = False

    def notificar(estado: str, metodo: str, repeticion: int, ultimo: str = "") -> None:
        if al_progresar is not None:
            al_progresar(ProgresoExperimento(
                estado, configuracion.nombre, metodo, repeticion,
                configuracion.repeticiones, len(ejecuciones), total, ultimo,
            ))

    def ejecutar_uno(
        metodo: str, etiqueta: str, cfg: Configuracion, repeticion: int,
        presupuesto: int, capturar_evolucion: bool = False,
    ) -> RegistroEjecucion:
        semilla = configuracion.semilla_inicial + repeticion - 1
        cfg_semilla = replace(cfg, semilla=semilla)
        notificar("ejecutando", etiqueta, repeticion)
        try:
            if metodo in {"genetico", "hibrido"}:
                return _ejecutar_ga(
                    problema, cfg_semilla, configuracion.escenario, repeticion, etiqueta,
                    debe_cancelar, escenario_datos, capturar_evolucion,
                )
            if metodo == "aleatorio":
                resultado = ejecutar_busqueda_aleatoria(problema, presupuesto, semilla, debe_cancelar=debe_cancelar)
            else:
                resultado = ejecutar_heuristica_constructiva(problema, presupuesto, semilla, debe_cancelar=debe_cancelar)
            return _registro_desde_baseline(
                resultado, escenario=configuracion.escenario, repeticion=repeticion,
                semilla=semilla, etiqueta=etiqueta, presupuesto=presupuesto,
            )
        except Exception as exc:
            return _registro_error(
                metodo, etiqueta, configuracion.escenario, repeticion, semilla,
                asdict(cfg_semilla) if metodo in {"genetico", "hibrido"} else {"presupuesto_evaluaciones": presupuesto},
                presupuesto, exc,
            )

    if configuracion.modo in {"parametros", "ablacion"}:
        primera_etiqueta = configuracion.variantes[0][0] if configuracion.variantes else ""
        for etiqueta, cfg in configuracion.variantes:
            for repeticion in range(1, configuracion.repeticiones + 1):
                if debe_cancelar is not None and debe_cancelar():
                    cancelado = True
                    break
                registro = ejecutar_uno(
                    "genetico", etiqueta, cfg, repeticion, presupuesto_nominal(cfg),
                    capturar_evolucion=(
                        configuracion.repeticion_evolucion == repeticion
                        and etiqueta == primera_etiqueta
                    ),
                )
                ejecuciones.append(registro)
                notificar("ejecutando", etiqueta, repeticion, _texto_resultado(registro))
                if registro.motivo_parada == "cancelada":
                    cancelado = True
                    break
            if cancelado:
                break
    else:
        metodos = tuple(dict.fromkeys(configuracion.metodos))
        for repeticion in range(1, configuracion.repeticiones + 1):
            if debe_cancelar is not None and debe_cancelar():
                cancelado = True
                break
            presupuesto_referencia = max(
                presupuesto_nominal(configuracion.genetico),
                presupuesto_nominal(configuracion.hibrido) if "hibrido" in metodos else 0,
            )
            # El AG se ejecuta primero para asignar a las referencias su costo real,
            # incluyendo evaluaciones de reparación y mutación dirigida.
            if "genetico" in metodos:
                cfg_clasico = configuracion.genetico
                if "hibrido" in metodos and cfg_clasico.presupuesto_evaluaciones == 0:
                    cfg_clasico = replace(cfg_clasico, presupuesto_evaluaciones=presupuesto_referencia)
                registro = ejecutar_uno(
                    "genetico", METODOS["genetico"], cfg_clasico,
                    repeticion, presupuesto_referencia,
                    capturar_evolucion=configuracion.repeticion_evolucion == repeticion,
                )
                ejecuciones.append(registro)
                presupuesto_referencia = registro.evaluaciones or presupuesto_referencia
                notificar("ejecutando", METODOS["genetico"], repeticion, _texto_resultado(registro))
                if registro.motivo_parada == "cancelada":
                    cancelado = True
                    break
            if "hibrido" in metodos and not cancelado:
                cfg_hibrido = configuracion.hibrido
                if cfg_hibrido.presupuesto_evaluaciones == 0:
                    cfg_hibrido = replace(cfg_hibrido, presupuesto_evaluaciones=presupuesto_referencia)
                registro = ejecutar_uno(
                    "hibrido", METODOS["hibrido"], cfg_hibrido,
                    repeticion, presupuesto_referencia,
                    capturar_evolucion=(
                        "genetico" not in metodos
                        and configuracion.repeticion_evolucion == repeticion
                    ),
                )
                ejecuciones.append(registro)
                notificar("ejecutando", METODOS["hibrido"], repeticion, _texto_resultado(registro))
                if registro.motivo_parada == "cancelada":
                    cancelado = True
                    break
            for metodo in ("aleatorio", "constructivo"):
                if metodo not in metodos:
                    continue
                if debe_cancelar is not None and debe_cancelar():
                    cancelado = True
                    break
                registro = ejecutar_uno(
                    metodo, METODOS[metodo], configuracion.genetico,
                    repeticion, presupuesto_referencia,
                )
                ejecuciones.append(registro)
                notificar("ejecutando", METODOS[metodo], repeticion, _texto_resultado(registro))
                if registro.motivo_parada == "cancelada":
                    cancelado = True
                    break
            if cancelado:
                break

    errores = any(e.error for e in ejecuciones)
    estado = "cancelado" if cancelado else ("completado_con_errores" if errores else "completado")
    fin_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    resultado = ResultadoExperimento(
        id=f"exp-{uuid.uuid4().hex[:12]}", inicio=inicio_iso, fin=fin_iso,
        estado=estado, configuracion=configuracion, escenario_datos=escenario_datos,
        huella_escenario=huella, ejecuciones=tuple(ejecuciones), duracion=perf_counter() - inicio,
    )
    notificar(estado, "—", 0, conclusiones_descriptivas(ejecuciones).splitlines()[0])
    return resultado


def ejecutar_lote_escenarios(
    configuracion: ConfiguracionExperimento,
    escenarios: Iterable[tuple[str, dict[str, Any]]],
    *,
    al_progresar: Callable[[ProgresoLoteEscenarios], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
) -> ResultadoLoteEscenarios:
    """Aplica el mismo diseño a varios escenarios sin combinar sus muestras.

    Cada resultado conserva su propia huella, ejecuciones y resumen estadístico.
    La semilla inicial y los parámetros no cambian entre escenarios, de modo que
    una comparación por lotes sigue siendo reproducible.
    """
    configuracion.validar()
    entradas = tuple((str(nombre).strip(), deepcopy(datos)) for nombre, datos in escenarios)
    if not entradas:
        raise ValueError("Selecciona al menos un escenario para el lote experimental")
    if any(not nombre for nombre, _datos in entradas):
        raise ValueError("Todos los escenarios del lote requieren un nombre")
    nombres: list[str] = []
    resultados: list[ResultadoExperimento] = []
    total = len(entradas)
    cancelado = False
    for indice, (nombre, datos) in enumerate(entradas, start=1):
        if debe_cancelar is not None and debe_cancelar():
            cancelado = True
            break
        problema_desde_datos(deepcopy(datos))
        config_escenario = replace(
            configuracion,
            nombre=f"{configuracion.nombre} · {nombre}",
            escenario=nombre,
        )

        def notificar(progreso: ProgresoExperimento) -> None:
            if al_progresar is not None:
                al_progresar(ProgresoLoteEscenarios(nombre, indice, total, progreso))

        resultado = ejecutar_experimento(
            config_escenario,
            datos,
            al_progresar=notificar,
            debe_cancelar=debe_cancelar,
        )
        nombres.append(nombre)
        resultados.append(resultado)
        if resultado.estado == "cancelado":
            cancelado = True
            break
    return ResultadoLoteEscenarios(tuple(nombres), tuple(resultados), cancelado)


def _texto_resultado(registro: RegistroEjecucion) -> str:
    if registro.error:
        return f"Error: {registro.error}"
    return (
        f"{'Factible' if registro.factible else 'No factible'} · duras {registro.duras} · "
        f"blanda {registro.penalizacion_blanda} · {registro.evaluaciones} evaluaciones"
    )


def _crear_carpeta_unica(raiz: Path) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    existentes = {p.name for p in raiz.iterdir() if p.is_dir()}
    numero = 1
    while f"experimento_{numero:03d}" in existentes:
        numero += 1
    carpeta = raiz / f"experimento_{numero:03d}"
    carpeta.mkdir()
    return carpeta


def _registro_dict(registro: RegistroEjecucion) -> dict[str, Any]:
    return asdict(registro)


def exportar_experimento(resultado: ResultadoExperimento, raiz: str | Path) -> Path:
    """Genera un paquete autocontenido sin sobrescribir experimentos anteriores."""
    carpeta = _crear_carpeta_unica(Path(raiz))
    configuracion = asdict(resultado.configuracion)
    configuracion["id_experimento"] = resultado.id
    configuracion["estado"] = resultado.estado
    configuracion["huella_escenario_sha256"] = resultado.huella_escenario
    (carpeta / "configuracion.json").write_text(
        json.dumps(configuracion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (carpeta / "escenario.json").write_text(
        json.dumps(resultado.escenario_datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    columnas = (
        "id", "fecha", "metodo", "etiqueta_metodo", "escenario", "repeticion", "semilla",
        "presupuesto_objetivo", "evaluaciones", "duracion", "motivo_parada", "factible",
        "duras", "penalizacion_blanda", "fitness", "evaluaciones_hasta_factible",
        "generacion_primera_factible", "generaciones_ejecutadas", "error",
        "evaluaciones_inicializacion", "evaluaciones_evolucion",
        "evaluaciones_busqueda_local", "tiempo_inicializacion",
        "tiempo_evolucion", "tiempo_busqueda_local",
    )
    with (carpeta / "ejecuciones.csv").open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        for registro in resultado.ejecuciones:
            datos = _registro_dict(registro)
            escritor.writerow({clave: datos.get(clave) for clave in columnas})

    resumen = resumir_ejecuciones(resultado.ejecuciones)
    with (carpeta / "resumen_estadistico.csv").open("w", newline="", encoding="utf-8-sig") as archivo:
        campos = ("metodo", "metrica", "n", "media", "mediana", "desviacion", "minimo", "maximo", "p25", "p75")
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        for metodo in resumen:
            for metrica in ("violaciones_duras", "penalizacion_blanda_factible", "fitness_factible", "tiempo", "evaluaciones", "evaluaciones_factibilidad", "generaciones"):
                escritor.writerow({"metodo": metodo["metodo"], "metrica": metrica, **metodo[metrica]})

    resumen_json = {
        "id": resultado.id, "inicio": resultado.inicio, "fin": resultado.fin,
        "estado": resultado.estado, "duracion": resultado.duracion,
        "huella_escenario_sha256": resultado.huella_escenario,
        "estadisticas": resumen,
        "conclusiones": conclusiones_descriptivas(resultado.ejecuciones),
        "ejecuciones": [_registro_dict(e) for e in resultado.ejecuciones],
    }
    (carpeta / "resumen.json").write_text(
        json.dumps(resumen_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    graficas = exportar_graficas(
        resultado.ejecuciones, carpeta,
        incluir_parametros=resultado.configuracion.modo in {"parametros", "ablacion"},
    )
    _exportar_html(resultado, resumen, graficas, carpeta / "reporte.html")
    return carpeta


def _exportar_html(
    resultado: ResultadoExperimento, resumen: list[dict[str, Any]],
    graficas: tuple[Path, ...], destino: Path,
) -> None:
    filas = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(valor))}</td>" for valor in (
            e.etiqueta_metodo, e.repeticion, e.semilla,
            "Sí" if e.factible else "No", e.duras, e.penalizacion_blanda,
            e.fitness, e.evaluaciones, e.evaluaciones_busqueda_local,
            f"{e.duracion:.4f}", f"{e.tiempo_busqueda_local:.4f}", e.motivo_parada,
        )) + "</tr>"
        for e in resultado.ejecuciones
    )
    tarjetas = "".join(
        f"<section><h3>{html.escape(r['metodo'])}</h3>"
        f"<p>Muestras válidas: {r['muestras_validas']} · Factibles: {r['factibles']} · "
        f"Tasa: {r['tasa_factibilidad'] if r['tasa_factibilidad'] is not None else 'Sin datos'}%</p></section>"
        for r in resumen
    )
    imagenes = "".join(
        f"<figure><img src='{html.escape(p.name)}' alt='{html.escape(p.stem)}'><figcaption>{html.escape(p.stem)}</figcaption></figure>"
        for p in graficas
    )
    contenido = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>{html.escape(resultado.configuracion.nombre)}</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#17202a;background:#f4f6f8}}
h1,h2{{color:#12344d}} section,table,figure{{background:white;border:1px solid #d9e2ec;padding:14px;margin:12px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:7px;border-bottom:1px solid #e7edf2;text-align:left}}
img{{max-width:100%;height:auto}} .nota{{color:#5d6d7e}}
</style></head><body><h1>{html.escape(resultado.configuracion.nombre)}</h1>
<p>{html.escape(resultado.configuracion.descripcion)}</p>
<p><b>Estado:</b> {html.escape(resultado.estado)} · <b>Escenario:</b> {html.escape(resultado.configuracion.escenario)} ·
<b>Huella SHA-256:</b> <code>{resultado.huella_escenario}</code></p>
<h2>Metodología</h2><p>Todos los métodos usan la misma evaluación lexicográfica: primero minimizan violaciones duras y, entre empates, penalización blanda. El AG clásico permanece independiente. El híbrido puede combinar población inicial constructiva, búsqueda local sin retrocesos y mutación adaptativa acotada.</p>
<p><b>Configuración híbrida:</b> inicialización={resultado.configuracion.hibrido.inicializacion_heuristica}, búsqueda local={resultado.configuracion.hibrido.busqueda_local}, mutación adaptativa={resultado.configuracion.hibrido.mutacion_adaptativa}, presupuesto máximo={resultado.configuracion.hibrido.presupuesto_evaluaciones or 'sin límite explícito'}.</p>
<h2>Resumen estadístico</h2>{tarjetas}<h2>Ejecuciones</h2>
<table><thead><tr><th>Método</th><th>Rep.</th><th>Semilla</th><th>Factible</th><th>Duras</th><th>Blanda</th><th>Fitness</th><th>Evaluaciones</th><th>Eval. local</th><th>Tiempo (s)</th><th>Tiempo local</th><th>Parada</th></tr></thead><tbody>{filas}</tbody></table>
<h2>Gráficas</h2>{imagenes}<h2>Interpretación descriptiva</h2>
<pre>{html.escape(conclusiones_descriptivas(resultado.ejecuciones))}</pre>
<h2>Limitaciones</h2><p class="nota">Resultados condicionados al escenario, semillas, presupuesto y pesos del modelo. Las puntuaciones parciales usadas al construir individuos heurísticos no son evaluaciones completas; cada individuo terminado sí se evalúa y contabiliza. El tiempo depende del equipo. La ausencia de una solución factible no demuestra imposibilidad matemática. No se afirma optimalidad global ni superioridad general.</p>
</body></html>"""
    destino.write_text(contenido, encoding="utf-8")

