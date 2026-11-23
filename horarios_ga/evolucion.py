"""Instantáneas inmutables, diferencias y reproducción de la evolución genética."""
from __future__ import annotations

import gzip
import json
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .datos import problema_desde_datos
from .fitness import Evaluacion, evaluar
from .genetico import Configuracion, Registro, Resultado
from .modelo import Cromosoma, Problema


VERSION_EVOLUCION = 1


def copiar_cromosoma(cromosoma: Cromosoma) -> Cromosoma:
    """Copia estructural explícita; evita compartir contenedores con el motor."""
    return tuple((int(dia), int(hora), int(salon)) for dia, hora, salon in cromosoma)


@dataclass(frozen=True)
class InstantaneaEvolutiva:
    generacion: int
    mejor_generacion: Cromosoma
    mejor_global: Cromosoma
    evaluacion_generacion: Evaluacion
    evaluacion_global: Evaluacion
    registro: Registro
    conflictivos: tuple[int, ...]
    tiempo_calculo: float
    primera_generacion_factible: int | None = None
    muestra_inicial: Cromosoma | None = None

    @property
    def factible(self) -> bool:
        return self.evaluacion_global.factible


@dataclass(frozen=True)
class CambioSesion:
    sesion_id: str
    indice: int
    anterior: tuple[int, int, int]
    actual: tuple[int, int, int]
    cambio_dia: bool
    cambio_hora: bool
    cambio_salon: bool
    conflicto_desaparecio: bool
    conflicto_aparecio: bool

    @property
    def cambio_asignacion(self) -> bool:
        return self.anterior != self.actual


@dataclass(frozen=True)
class DiferenciaEvolutiva:
    generacion_anterior: int
    generacion_actual: int
    cambios: tuple[CambioSesion, ...]
    duras_antes: int
    duras_despues: int
    desglose_duro_antes: dict[str, int]
    desglose_duro_despues: dict[str, int]

    @property
    def sesiones_reasignadas(self) -> int:
        return sum(c.cambio_asignacion for c in self.cambios)

    @property
    def cambios_dia(self) -> int:
        return sum(c.cambio_dia for c in self.cambios)

    @property
    def cambios_hora(self) -> int:
        return sum(c.cambio_hora for c in self.cambios)

    @property
    def cambios_salon(self) -> int:
        return sum(c.cambio_salon for c in self.cambios)


@dataclass(frozen=True)
class RegistroEvolucion:
    version: int
    configuracion: Configuracion
    escenario_datos: dict[str, Any]
    ids_sesiones: tuple[str, ...]
    instantaneas: tuple[InstantaneaEvolutiva, ...]
    motivo_parada: str
    cancelada: bool = False


def crear_instantanea(
    problema: Problema,
    generacion: int,
    mejor_generacion: Cromosoma,
    mejor_global: Cromosoma,
    evaluacion_generacion: Evaluacion,
    evaluacion_global: Evaluacion,
    registro: Registro,
    tiempo_calculo: float,
    *,
    muestra_inicial: Cromosoma | None = None,
    primera_generacion_factible: int | None = None,
    al_evaluar: Callable[[Evaluacion], None] | None = None,
    evaluador_detallado: Callable[[Cromosoma], tuple[Evaluacion, frozenset[int]]] | None = None,
) -> InstantaneaEvolutiva:
    from .fitness import evaluar_detallado

    global_copia = copiar_cromosoma(mejor_global)
    evaluacion_comprobada, conflictos = (
        evaluador_detallado(global_copia)
        if evaluador_detallado is not None
        else evaluar_detallado(problema, global_copia)
    )
    if al_evaluar is not None and evaluador_detallado is None:
        al_evaluar(evaluacion_comprobada)
    return InstantaneaEvolutiva(
        generacion=int(generacion),
        mejor_generacion=copiar_cromosoma(mejor_generacion),
        mejor_global=global_copia,
        evaluacion_generacion=evaluacion_generacion,
        evaluacion_global=evaluacion_global,
        registro=registro,
        conflictivos=tuple(sorted(conflictos)),
        tiempo_calculo=float(tiempo_calculo),
        primera_generacion_factible=primera_generacion_factible,
        muestra_inicial=copiar_cromosoma(muestra_inicial) if muestra_inicial is not None else None,
    )


def comparar_instantaneas(
    problema: Problema,
    anterior: InstantaneaEvolutiva,
    actual: InstantaneaEvolutiva,
) -> DiferenciaEvolutiva:
    if len(anterior.mejor_global) != len(problema.sesiones) or len(actual.mejor_global) != len(problema.sesiones):
        raise ValueError("Las instantáneas no corresponden al problema académico")
    conflictos_antes = set(anterior.conflictivos)
    conflictos_despues = set(actual.conflictivos)
    cambios = []
    for indice, sesion in enumerate(problema.sesiones):
        antes = anterior.mejor_global[indice]
        despues = actual.mejor_global[indice]
        cambios.append(CambioSesion(
            sesion_id=sesion.id, indice=indice, anterior=antes, actual=despues,
            cambio_dia=antes[0] != despues[0], cambio_hora=antes[1] != despues[1],
            cambio_salon=antes[2] != despues[2],
            conflicto_desaparecio=indice in conflictos_antes and indice not in conflictos_despues,
            conflicto_aparecio=indice not in conflictos_antes and indice in conflictos_despues,
        ))
    return DiferenciaEvolutiva(
        anterior.generacion, actual.generacion, tuple(cambios),
        anterior.evaluacion_global.duras, actual.evaluacion_global.duras,
        anterior.evaluacion_global.desglose_duro(), actual.evaluacion_global.desglose_duro(),
    )


def describir_diferencia(
    problema: Problema, diferencia: DiferenciaEvolutiva, limite: int = 12,
) -> tuple[str, ...]:
    lineas = [f"CAMBIOS EN LA GENERACIÓN {diferencia.generacion_actual}"]
    modificados = [c for c in diferencia.cambios if c.cambio_asignacion or c.conflicto_aparecio or c.conflicto_desaparecio]
    if not modificados:
        lineas.append("El mejor horario se mantuvo sin cambios.")
    for cambio in modificados[:limite]:
        sesion = problema.sesiones[cambio.indice]
        detalles = []
        if cambio.cambio_dia:
            detalles.append(f"día {problema.dias[cambio.anterior[0]]} → {problema.dias[cambio.actual[0]]}")
        if cambio.cambio_hora:
            detalles.append(f"hora {problema.horas[cambio.anterior[1]]} → {problema.horas[cambio.actual[1]]}")
        if cambio.cambio_salon:
            detalles.append(
                f"salón {problema.salones[cambio.anterior[2]].id} → {problema.salones[cambio.actual[2]].id}"
            )
        if cambio.conflicto_desaparecio:
            detalles.append("conflicto desaparecido")
        if cambio.conflicto_aparecio:
            detalles.append("conflicto aparecido")
        lineas.append(f"• {sesion.materia} [{sesion.id}]: {', '.join(detalles)}.")
    if len(modificados) > limite:
        lineas.append(f"• … y {len(modificados) - limite} sesiones adicionales.")
    for nombre, antes in diferencia.desglose_duro_antes.items():
        despues = diferencia.desglose_duro_despues.get(nombre, 0)
        if antes != despues:
            lineas.append(f"• {nombre}: {antes} → {despues}.")
    lineas.append(f"• Violaciones duras totales: {diferencia.duras_antes} → {diferencia.duras_despues}.")
    return tuple(lineas)


def resultado_desde_instantanea(
    instantanea: InstantaneaEvolutiva, configuracion: Configuracion,
) -> Resultado:
    return Resultado(
        instantanea.mejor_global, instantanea.evaluacion_global,
        instantanea.evaluacion_global, (instantanea.registro,), configuracion,
        "instantanea_evolutiva",
    )


class ControlDidactico:
    """Pausa cooperativa y sincronización opcional con la presentación visual.

    Todas las esperas ocurren en el trabajador. La interfaz sólo confirma qué
    generación llegó a dibujarse y nunca espera a que termine el algoritmo.
    """

    def __init__(
        self, retardo: float = 0.0, *, sincronizar_presentacion: bool = False,
    ):
        self.retardo = max(0.0, float(retardo))
        self.sincronizar_presentacion = sincronizar_presentacion
        self._condicion = threading.Condition()
        self._pausado = False
        self._pasos = 0
        self._cancelado = False
        self._generacion_pendiente = -1
        self._generacion_presentada = -1

    @property
    def pausado(self) -> bool:
        with self._condicion:
            return self._pausado

    @property
    def cancelado(self) -> bool:
        with self._condicion:
            return self._cancelado

    def pausar(self) -> None:
        with self._condicion:
            self._pausado = True

    def continuar(self) -> None:
        with self._condicion:
            self._pausado = False
            self._pasos = 0
            self._condicion.notify_all()

    def paso(self) -> None:
        with self._condicion:
            self._pausado = True
            self._pasos += 1
            self._condicion.notify_all()

    def cancelar(self) -> None:
        with self._condicion:
            self._cancelado = True
            self._condicion.notify_all()

    def notificar_captura(self, generacion: int) -> None:
        """Registra una captura que el trabajador espera ver presentada."""
        if not self.sincronizar_presentacion:
            return
        with self._condicion:
            self._generacion_pendiente = max(self._generacion_pendiente, generacion)

    def confirmar_presentacion(self, generacion: int) -> None:
        """La llama Tk después de actualizar calendario, métricas y marcador."""
        if not self.sincronizar_presentacion:
            return
        with self._condicion:
            self._generacion_presentada = max(self._generacion_presentada, generacion)
            self._condicion.notify_all()

    def esperar(self) -> float:
        """Devuelve tiempo artificial para excluirlo del tiempo algorítmico."""
        inicio = perf_counter()
        with self._condicion:
            while (
                self.sincronizar_presentacion
                and self._generacion_presentada < self._generacion_pendiente
                and not self._cancelado
            ):
                self._condicion.wait(timeout=.2)
            fin_retardo = perf_counter() + self.retardo
            while not self._cancelado:
                restante = fin_retardo - perf_counter()
                if restante <= 0:
                    break
                self._condicion.wait(timeout=restante)
            while self._pausado and self._pasos == 0 and not self._cancelado:
                self._condicion.wait(timeout=.2)
            if self._pasos > 0:
                self._pasos -= 1
        return perf_counter() - inicio


def _instantanea_dict(instantanea: InstantaneaEvolutiva) -> dict[str, Any]:
    return asdict(instantanea)


def guardar_evolucion(registro: RegistroEvolucion, ruta: str | Path) -> Path:
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(asdict(registro), ensure_ascii=False, separators=(",", ":"))
    if destino.suffix.lower() == ".gz":
        with gzip.open(destino, "wt", encoding="utf-8") as archivo:
            archivo.write(contenido)
    else:
        destino.write_text(contenido + "\n", encoding="utf-8")
    return destino


def cargar_evolucion(ruta: str | Path) -> RegistroEvolucion:
    origen = Path(ruta)
    try:
        if origen.suffix.lower() == ".gz":
            with gzip.open(origen, "rt", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        else:
            datos = json.loads(origen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el registro evolutivo: {exc}") from exc
    if not isinstance(datos, dict) or datos.get("version") != VERSION_EVOLUCION:
        raise ValueError("Versión de registro evolutivo no compatible")
    try:
        escenario = deepcopy(datos["escenario_datos"])
        problema = problema_desde_datos(escenario)
        ids = tuple(str(x) for x in datos["ids_sesiones"])
        if ids != tuple(s.id for s in problema.sesiones):
            raise ValueError("Los identificadores de sesión no corresponden al escenario")
        configuracion = Configuracion(**datos["configuracion"])
        configuracion.validar()
        instantaneas = []
        for item in datos["instantaneas"]:
            mejor_generacion = copiar_cromosoma(tuple(tuple(g) for g in item["mejor_generacion"]))
            mejor_global = copiar_cromosoma(tuple(tuple(g) for g in item["mejor_global"]))
            problema.validar_cromosoma(mejor_generacion)
            problema.validar_cromosoma(mejor_global)
            ev_generacion = Evaluacion(**item["evaluacion_generacion"])
            ev_global = Evaluacion(**item["evaluacion_global"])
            if evaluar(problema, mejor_generacion) != ev_generacion or evaluar(problema, mejor_global) != ev_global:
                raise ValueError("Una evaluación almacenada no coincide con su cromosoma")
            registro = Registro(**item["registro"])
            muestra = item.get("muestra_inicial")
            muestra_copia = copiar_cromosoma(tuple(tuple(g) for g in muestra)) if muestra is not None else None
            if muestra_copia is not None:
                problema.validar_cromosoma(muestra_copia)
            instantaneas.append(InstantaneaEvolutiva(
                int(item["generacion"]), mejor_generacion, mejor_global,
                ev_generacion, ev_global, registro,
                tuple(int(x) for x in item["conflictivos"]),
                float(item["tiempo_calculo"]), item.get("primera_generacion_factible"), muestra_copia,
            ))
        if not instantaneas or instantaneas[0].generacion != 0:
            raise ValueError("El registro debe comenzar en la generación 0")
        if any(b.generacion <= a.generacion for a, b in zip(instantaneas, instantaneas[1:])):
            raise ValueError("Las generaciones deben estar ordenadas y no repetirse")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Estructura de registro evolutivo inválida") from exc
    return RegistroEvolucion(
        VERSION_EVOLUCION, configuracion, escenario, ids, tuple(instantaneas),
        str(datos.get("motivo_parada", "desconocido")), bool(datos.get("cancelada", False)),
    )

