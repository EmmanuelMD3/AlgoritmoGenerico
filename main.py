"""Ejecutar: python main.py --generaciones 200 --semilla 42"""
from __future__ import annotations

import argparse
from pathlib import Path

from horarios_ga.datos import cargar_problema
from horarios_ga.genetico import Configuracion, ejecutar
from horarios_ga.reportes import exportar

BASE = Path(__file__).resolve().parent


def ruta_datos_predeterminada(base: Path = BASE) -> Path:
    """Usa la configuración canónica si existe y el ejemplo sólo como respaldo."""
    canonica = base / "datos" / "configuracion_academica.json"
    return canonica if canonica.exists() else base / "datos" / "ejemplo.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimizacion de horarios mediante algoritmos geneticos")
    parser.add_argument("--datos", type=Path, default=ruta_datos_predeterminada())
    parser.add_argument("--salida", type=Path, default=BASE / "resultados")
    parser.add_argument("--poblacion", type=int, default=120)
    parser.add_argument("--generaciones", type=int, default=200)
    parser.add_argument("--mutacion", type=float, default=0.08)
    parser.add_argument("--cruza", type=float, default=0.85)
    parser.add_argument("--elitismo", type=int, default=4)
    parser.add_argument("--torneo", type=int, default=4)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--mutacion-dirigida", type=float, default=0.35)
    parser.add_argument("--reparacion", type=float, default=0.25)
    parser.add_argument("--inmigrantes", type=float, default=0.03)
    parser.add_argument("--parada-sin-mejora", type=int, default=0)
    parser.add_argument("--objetivo-blandas", type=int, default=0)
    parser.add_argument("--modo", choices=("clasico", "hibrido"), default="clasico")
    parser.add_argument("--inicializacion-heuristica", action="store_true")
    parser.add_argument("--fraccion-heuristica", type=float, default=0.30)
    parser.add_argument("--busqueda-local", action="store_true")
    parser.add_argument("--estrategia-local", choices=("mejores", "aleatoria", "estancamiento"), default="mejores")
    parser.add_argument("--vecindario-local", choices=("reasignacion", "intercambio", "mixta"), default="mixta")
    parser.add_argument("--criterio-local", choices=("primera", "mejor"), default="primera")
    parser.add_argument("--frecuencia-local", type=int, default=5)
    parser.add_argument("--fraccion-local", type=float, default=0.20)
    parser.add_argument("--evaluaciones-locales", type=int, default=12)
    parser.add_argument("--mejoras-locales", type=int, default=2)
    parser.add_argument("--mutacion-adaptativa", action="store_true")
    parser.add_argument("--mutacion-min", type=float, default=0.02)
    parser.add_argument("--mutacion-max", type=float, default=0.25)
    parser.add_argument("--estancamiento-mutacion", type=int, default=10)
    parser.add_argument("--umbral-diversidad", type=float, default=0.25)
    parser.add_argument("--factor-incremento-mutacion", type=float, default=1.5)
    parser.add_argument("--factor-recuperacion-mutacion", type=float, default=0.85)
    parser.add_argument("--presupuesto-evaluaciones", type=int, default=0)
    args = parser.parse_args()

    problema = cargar_problema(args.datos)
    config = Configuracion(
        poblacion=args.poblacion, generaciones=args.generaciones,
        prob_mutacion=args.mutacion, prob_cruza=args.cruza,
        elitismo=args.elitismo, torneo=args.torneo, semilla=args.semilla,
        mutacion_dirigida=args.mutacion_dirigida,
        prob_reparacion=args.reparacion, inmigrantes=args.inmigrantes,
        parada_sin_mejora=args.parada_sin_mejora,
        objetivo_penalizacion_blanda=args.objetivo_blandas,
        variante=args.modo,
        inicializacion_heuristica=args.inicializacion_heuristica,
        porcentaje_inicializacion_heuristica=args.fraccion_heuristica,
        busqueda_local=args.busqueda_local,
        estrategia_busqueda_local=args.estrategia_local,
        vecindario_busqueda_local=args.vecindario_local,
        criterio_busqueda_local=args.criterio_local,
        frecuencia_busqueda_local=args.frecuencia_local,
        porcentaje_busqueda_local=args.fraccion_local,
        evaluaciones_busqueda_local=args.evaluaciones_locales,
        mejoras_busqueda_local=args.mejoras_locales,
        mutacion_adaptativa=args.mutacion_adaptativa,
        mutacion_min=args.mutacion_min,
        mutacion_max=args.mutacion_max,
        estancamiento_mutacion=args.estancamiento_mutacion,
        umbral_diversidad=args.umbral_diversidad,
        factor_incremento_mutacion=args.factor_incremento_mutacion,
        factor_recuperacion_mutacion=args.factor_recuperacion_mutacion,
        presupuesto_evaluaciones=args.presupuesto_evaluaciones,
    )
    print("\nALGORITMO GENETICO PARA HORARIOS UNIVERSITARIOS")
    print(f"Sesiones: {len(problema.sesiones)} | Grupos: {len(problema.grupos)} "
          f"| Docentes: {len(problema.docentes)} | Salones: {len(problema.salones)}")
    print(f"Modo: {config.variante} | Poblacion: {config.poblacion} | Generaciones: {config.generaciones} "
          f"| Semilla: {config.semilla}")
    resultado = ejecutar(problema, config)
    print(f"\nFitness inicial: {resultado.inicial.fitness} "
          f"(duras: {resultado.historial[0].conflictos_duros}, "
          f"penalizacion blanda: {resultado.historial[0].penalizacion_blanda})")
    e = resultado.evaluacion
    print(f"Fitness final:   {e.fitness} (duras: {e.duras}, "
          f"penalizacion blanda: {e.penalizacion_blanda})")
    print("Restricciones duras:")
    for nombre, cantidad in e.desglose_duro().items():
        print(f" - {nombre}: {cantidad}")
    print("Criterios blandos:")
    for nombre, cantidad in e.desglose_blando().items():
        print(f" - {nombre}: {cantidad}")
    print("Estado:", "HORARIO FACTIBLE" if e.factible else "HORARIO CON CONFLICTOS (ajustar parametros)")
    if not e.factible:
        print("Razones:", "; ".join(e.razones_no_factible()))
    print(f"Parada: {resultado.motivo_parada} en generacion {resultado.historial[-1].generacion}")
    s = resultado.estadisticas
    print(
        f"Evaluaciones: {s.evaluaciones_totales} | Iniciales aleatorios/heuristicos: "
        f"{s.individuos_aleatorios}/{s.individuos_heuristicos} | "
        f"Busqueda local: {s.aplicaciones_busqueda_local} aplicaciones, "
        f"{s.mejoras_busqueda_local} mejoras"
    )
    archivos = exportar(problema, resultado, args.salida)
    print("\nArchivos generados:")
    for archivo in archivos:
        print(" -", archivo.resolve())


if __name__ == "__main__":
    main()
