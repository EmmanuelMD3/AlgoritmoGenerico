"""Comparación reproducible de la búsqueda híbrida antes/después de la mejora."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Iterable

from .datos import cargar_datos, problema_desde_datos
from .escenarios import huella_escenario
from .genetico import Configuracion, ejecutar
from .modelo import Problema


@dataclass(frozen=True)
class FilaFactibilidad:
    variante: str
    semilla: int
    presupuesto: int
    evaluaciones: int
    generaciones_ejecutadas: int
    factible: bool
    violaciones_duras: int
    penalizacion_blanda: int
    fitness: int
    motivo_parada: str
    segundos_observados: float


def _configuracion(
    semilla: int,
    *,
    poblacion: int,
    generaciones: int,
    presupuesto: int,
    avanzada: bool,
) -> Configuracion:
    """Aísla las mejoras nuevas manteniendo iguales los demás parámetros."""
    return Configuracion(
        poblacion=poblacion,
        generaciones=generaciones,
        semilla=semilla,
        variante="hibrido",
        inicializacion_heuristica=False,
        busqueda_local=False,
        mutacion_adaptativa=True,
        presupuesto_evaluaciones=presupuesto,
        reparacion_avanzada=avanzada,
        reinicio_estancamiento=avanzada,
    )


def ejecutar_comparacion(
    problema: Problema,
    *,
    semillas: Iterable[int] = (40, 41, 42),
    poblacion: int = 120,
    generaciones: int = 600,
    presupuesto: int = 30_000,
) -> tuple[FilaFactibilidad, ...]:
    """Ejecuta línea base y mejora con semilla y presupuesto idénticos."""
    filas: list[FilaFactibilidad] = []
    for semilla in semillas:
        for etiqueta, avanzada in (("antes", False), ("despues", True)):
            configuracion = _configuracion(
                int(semilla), poblacion=poblacion, generaciones=generaciones,
                presupuesto=presupuesto, avanzada=avanzada,
            )
            inicio = perf_counter()
            resultado = ejecutar(problema, configuracion)
            segundos = perf_counter() - inicio
            filas.append(FilaFactibilidad(
                etiqueta, int(semilla), presupuesto,
                resultado.estadisticas.evaluaciones_totales,
                resultado.historial[-1].generacion,
                resultado.evaluacion.factible,
                resultado.evaluacion.duras,
                resultado.evaluacion.penalizacion_blanda,
                resultado.evaluacion.fitness,
                resultado.motivo_parada,
                segundos,
            ))
    return tuple(filas)


def resumir(filas: Iterable[FilaFactibilidad]) -> dict[str, dict[str, float | int]]:
    grupos: dict[str, list[FilaFactibilidad]] = {"antes": [], "despues": []}
    for fila in filas:
        grupos.setdefault(fila.variante, []).append(fila)
    resumen: dict[str, dict[str, float | int]] = {}
    for etiqueta, grupo in grupos.items():
        if not grupo:
            continue
        resumen[etiqueta] = {
            "corridas": len(grupo),
            "factibles": sum(fila.factible for fila in grupo),
            "media_violaciones_duras": mean(fila.violaciones_duras for fila in grupo),
            "mediana_violaciones_duras": median(fila.violaciones_duras for fila in grupo),
            "media_segundos_observados": mean(fila.segundos_observados for fila in grupo),
        }
    return resumen


def exportar_comparacion(
    filas: Iterable[FilaFactibilidad],
    ruta: str | Path,
    *,
    huella: str | None = None,
    escenario: str = "",
) -> Path:
    filas = tuple(filas)
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "escenario": escenario,
        "huella_escenario_sha256": huella,
        "metodologia": (
            "Mismas semillas, población, generaciones y presupuesto de evaluaciones; "
            "sin inicialización heurística ni búsqueda local. Sólo cambian reparación "
            "dirigida avanzada y reinicio por estancamiento."
        ),
        "resultados": [asdict(fila) for fila in filas],
        "resumen": resumir(filas),
        "advertencia": (
            "Los tiempos son observaciones del equipo. No hallar factibilidad no "
            "demuestra imposibilidad. La calidad blanda sólo se compara después de factibilidad."
        ),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Comparación reproducible de factibilidad")
    parser.add_argument("--datos", type=Path, default=base / "datos" / "configuracion_academica.json")
    parser.add_argument("--salida", type=Path, default=base / "resultados" / "comparacion_factibilidad.json")
    parser.add_argument("--semillas", type=int, nargs="+", default=[40, 41, 42])
    parser.add_argument("--poblacion", type=int, default=120)
    parser.add_argument("--generaciones", type=int, default=600)
    parser.add_argument("--presupuesto", type=int, default=30_000)
    args = parser.parse_args()

    datos = cargar_datos(args.datos)
    problema = problema_desde_datos(datos)
    filas = ejecutar_comparacion(
        problema, semillas=args.semillas, poblacion=args.poblacion,
        generaciones=args.generaciones, presupuesto=args.presupuesto,
    )
    destino = exportar_comparacion(
        filas, args.salida, huella=huella_escenario(datos),
        escenario=str(args.datos.resolve()),
    )
    for fila in filas:
        print(
            f"{fila.variante:8} semilla={fila.semilla} "
            f"duras={fila.violaciones_duras} blanda={fila.penalizacion_blanda} "
            f"evaluaciones={fila.evaluaciones} tiempo={fila.segundos_observados:.3f}s"
        )
    print(json.dumps(resumir(filas), ensure_ascii=False, indent=2))
    print("Informe:", destino.resolve())


if __name__ == "__main__":
    main()
