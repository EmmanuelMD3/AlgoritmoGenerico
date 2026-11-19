"""Estadística descriptiva y gráficas para resultados experimentales reales."""
from __future__ import annotations

from collections import defaultdict
from math import floor
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Iterable, Sequence


VISTAS_EXPERIMENTO = (
    ("factibilidad", "Tasa de factibilidad"),
    ("penalizaciones", "Penalización blanda"),
    ("tiempos", "Tiempo de ejecución"),
    ("convergencia", "Convergencia genética"),
    ("convergencia_evaluaciones", "Convergencia por evaluaciones"),
    ("operadores", "Operadores híbridos"),
    ("parametros", "Comparación de parámetros"),
)


def percentil(valores: Sequence[float], porcentaje: float) -> float:
    if not valores:
        raise ValueError("No se puede calcular un percentil sin datos")
    if not 0 <= porcentaje <= 100:
        raise ValueError("El percentil debe estar entre 0 y 100")
    ordenados = sorted(float(v) for v in valores)
    posicion = (len(ordenados) - 1) * porcentaje / 100
    inferior = floor(posicion)
    superior = min(inferior + 1, len(ordenados) - 1)
    fraccion = posicion - inferior
    return ordenados[inferior] * (1 - fraccion) + ordenados[superior] * fraccion


def estadisticas_descriptivas(valores: Iterable[float | int | None]) -> dict[str, float | int | None]:
    validos = [float(v) for v in valores if v is not None]
    if not validos:
        return {clave: None for clave in ("media", "mediana", "desviacion", "minimo", "maximo", "p25", "p75")} | {"n": 0}
    return {
        "n": len(validos),
        "media": mean(validos),
        "mediana": median(validos),
        "desviacion": stdev(validos) if len(validos) > 1 else 0.0,
        "minimo": min(validos),
        "maximo": max(validos),
        "p25": percentil(validos, 25),
        "p75": percentil(validos, 75),
    }


def _validas(ejecuciones: Iterable[Any]) -> list[Any]:
    return [e for e in ejecuciones if not getattr(e, "error", None)]


def _etiqueta(ejecucion: Any) -> str:
    return getattr(ejecucion, "etiqueta_metodo", None) or getattr(ejecucion, "metodo", "Método")


def agrupar_ejecuciones(ejecuciones: Iterable[Any]) -> dict[str, list[Any]]:
    grupos: dict[str, list[Any]] = defaultdict(list)
    for ejecucion in ejecuciones:
        grupos[_etiqueta(ejecucion)].append(ejecucion)
    return dict(grupos)


def resumir_ejecuciones(ejecuciones: Iterable[Any]) -> list[dict[str, Any]]:
    """Resume por método/configuración y separa calidad de factibilidad."""
    resumen: list[dict[str, Any]] = []
    for etiqueta, todas in agrupar_ejecuciones(ejecuciones).items():
        validas = _validas(todas)
        factibles = [e for e in validas if e.factible]
        resumen.append({
            "metodo": etiqueta,
            "ejecuciones": len(todas),
            "muestras_validas": len(validas),
            "errores": len(todas) - len(validas),
            "factibles": len(factibles),
            "no_factibles": len(validas) - len(factibles),
            "tasa_factibilidad": (len(factibles) / len(validas) * 100) if validas else None,
            "violaciones_duras": estadisticas_descriptivas(e.duras for e in validas),
            "penalizacion_blanda_factible": estadisticas_descriptivas(e.penalizacion_blanda for e in factibles),
            "fitness_factible": estadisticas_descriptivas(e.fitness for e in factibles),
            "tiempo": estadisticas_descriptivas(e.duracion for e in validas),
            "evaluaciones": estadisticas_descriptivas(e.evaluaciones for e in validas),
            "evaluaciones_factibilidad": estadisticas_descriptivas(e.evaluaciones_hasta_factible for e in factibles),
            "generaciones": estadisticas_descriptivas(e.generaciones_ejecutadas for e in validas if e.generaciones_ejecutadas is not None),
        })
    return resumen


def conclusiones_descriptivas(ejecuciones: Iterable[Any]) -> str:
    resumen = resumir_ejecuciones(ejecuciones)
    if not resumen:
        return "Sin ejecuciones disponibles para interpretar."
    lineas = ["Interpretación descriptiva; no constituye una prueba de superioridad estadística."]
    con_tasa = [r for r in resumen if r["tasa_factibilidad"] is not None]
    if con_tasa:
        mejor_tasa = max(r["tasa_factibilidad"] for r in con_tasa)
        nombres = ", ".join(r["metodo"] for r in con_tasa if r["tasa_factibilidad"] == mejor_tasa)
        lineas.append(f"Mayor tasa de factibilidad observada: {mejor_tasa:.1f}% ({nombres}).")
    con_factibles = [r for r in resumen if r["penalizacion_blanda_factible"]["n"]]
    if con_factibles:
        mejor_calidad = min(r["penalizacion_blanda_factible"]["mediana"] for r in con_factibles)
        nombres = ", ".join(
            r["metodo"] for r in con_factibles
            if r["penalizacion_blanda_factible"]["mediana"] == mejor_calidad
        )
        lineas.append(
            f"Menor mediana de penalización entre soluciones factibles: {mejor_calidad:.2f} ({nombres})."
        )
    else:
        lineas.append("Sin soluciones factibles; no se calcula calidad blanda comparativa.")
    lineas.append("El tiempo es secundario y puede variar según el equipo y la carga del sistema.")
    return "\n".join(lineas)


def _preparar_figura(figura: Any, titulo: str):
    figura.clear()
    figura.suptitle(titulo, fontsize=11)


def dibujar_resultados(figura: Any, ejecuciones: Sequence[Any], vista: str) -> str:
    """Dibuja únicamente observaciones registradas; nunca completa generaciones."""
    if vista not in {clave for clave, _ in VISTAS_EXPERIMENTO}:
        raise ValueError(f"Gráfica experimental desconocida: {vista}")
    grupos = agrupar_ejecuciones(_validas(ejecuciones))
    titulo = dict(VISTAS_EXPERIMENTO)[vista]
    _preparar_figura(figura, titulo)
    if not grupos:
        eje = figura.add_subplot(111)
        eje.text(.5, .5, "Sin resultados experimentales", ha="center", va="center", transform=eje.transAxes)
        eje.set_axis_off()
        return "Ejecuta un experimento para generar observaciones."

    if vista == "factibilidad":
        eje = figura.add_subplot(111)
        etiquetas = list(grupos)
        tasas = [sum(e.factible for e in grupos[k]) / len(grupos[k]) * 100 for k in etiquetas]
        barras = eje.bar(etiquetas, tasas, color="#1f6f8b")
        eje.set_ylim(0, 105)
        eje.set_ylabel("Ejecuciones factibles (%)")
        eje.bar_label(barras, fmt="%.1f%%", padding=3, fontsize=8)
        eje.tick_params(axis="x", rotation=12)
        nota = "La tasa usa sólo ejecuciones válidas; los errores se informan por separado."
    elif vista == "penalizaciones":
        eje = figura.add_subplot(111)
        etiquetas, datos = [], []
        sin_factibles = []
        for etiqueta, corridas in grupos.items():
            valores = [e.penalizacion_blanda for e in corridas if e.factible]
            if valores:
                etiquetas.append(etiqueta)
                datos.append(valores)
            else:
                sin_factibles.append(etiqueta)
        if datos:
            eje.boxplot(datos, tick_labels=etiquetas, showmeans=True)
            eje.set_ylabel("Penalización ponderada")
            eje.tick_params(axis="x", rotation=12)
        else:
            eje.text(.5, .5, "Sin soluciones factibles", ha="center", va="center", transform=eje.transAxes)
            eje.set_xticks([])
        nota = "Sólo soluciones factibles." + (f" Sin factibles: {', '.join(sin_factibles)}." if sin_factibles else "")
    elif vista == "tiempos":
        eje = figura.add_subplot(111)
        etiquetas = list(grupos)
        datos = [[e.duracion for e in grupos[k]] for k in etiquetas]
        eje.boxplot(datos, tick_labels=etiquetas, showmeans=True)
        eje.set_ylabel("Segundos")
        eje.tick_params(axis="x", rotation=12)
        nota = "Caja: Q1–Q3; línea: mediana; triángulo: media. El tiempo es dependiente del entorno."
    elif vista == "convergencia":
        metricas = (
            ("conflictos_duros", "Violaciones duras", 1.0),
            ("penalizacion_blanda", "Penalización blanda", 1.0),
            ("mejor_fitness", "Fitness", 1.0),
            ("diversidad", "Diversidad (%)", 100.0),
        )
        geneticas = [e for corridas in grupos.values() for e in corridas if e.metodo in {"genetico", "hibrido"} and e.historial]
        if not geneticas:
            eje = figura.add_subplot(111)
            eje.text(.5, .5, "Sin historiales genéticos", ha="center", va="center", transform=eje.transAxes)
            eje.set_axis_off()
        else:
            for posicion, (campo, etiqueta, factor) in enumerate(metricas, start=1):
                eje = figura.add_subplot(2, 2, posicion)
                por_generacion: dict[int, list[float]] = defaultdict(list)
                for ejecucion in geneticas:
                    for registro in ejecucion.historial:
                        por_generacion[int(registro["generacion"])].append(float(registro[campo]) * factor)
                xs = sorted(por_generacion)
                medias = [median(por_generacion[x]) for x in xs]
                q1 = [percentil(por_generacion[x], 25) for x in xs]
                q3 = [percentil(por_generacion[x], 75) for x in xs]
                eje.plot(xs, medias, color="#1f6f8b", linewidth=1.6)
                eje.fill_between(xs, q1, q3, color="#1f6f8b", alpha=.18)
                eje.set_title(etiqueta, fontsize=9)
                eje.set_xlabel("Generación", fontsize=8)
                eje.grid(alpha=.2)
        nota = "Mediana y rango intercuartílico por generación observada; no se prolongan corridas terminadas."
    elif vista == "convergencia_evaluaciones":
        geneticas = [e for corridas in grupos.values() for e in corridas if e.metodo in {"genetico", "hibrido"} and e.historial]
        if not geneticas:
            eje = figura.add_subplot(111)
            eje.text(.5, .5, "Sin historiales con evaluaciones", ha="center", va="center", transform=eje.transAxes)
            eje.set_axis_off()
        else:
            colores = {etiqueta: color for etiqueta, color in zip(grupos, ("#1f6f8b", "#b7791f", "#6f42c1", "#16803c"))}
            for posicion, (campo, etiqueta_y) in enumerate((("conflictos_duros", "Violaciones duras"), ("penalizacion_blanda", "Penalización blanda")), start=1):
                eje = figura.add_subplot(1, 2, posicion)
                etiquetas_vistas: set[str] = set()
                for ejecucion in geneticas:
                    etiqueta = _etiqueta(ejecucion)
                    registros = [r for r in ejecucion.historial if int(r.get("evaluaciones_acumuladas", 0)) > 0]
                    if not registros:
                        continue
                    eje.plot(
                        [int(r["evaluaciones_acumuladas"]) for r in registros],
                        [float(r[campo]) for r in registros],
                        color=colores.get(etiqueta, "#64748b"), alpha=.45, linewidth=1.1,
                        label=etiqueta if etiqueta not in etiquetas_vistas else None,
                    )
                    etiquetas_vistas.add(etiqueta)
                eje.set(title=etiqueta_y, xlabel="Evaluaciones acumuladas", ylabel=etiqueta_y)
                eje.grid(alpha=.2)
                eje.legend(fontsize=7)
        nota = "Cada línea es una semilla real; el eje X usa evaluaciones acumuladas y no prolonga corridas terminadas."
    elif vista == "operadores":
        geneticas = [e for corridas in grupos.values() for e in corridas if e.metodo in {"genetico", "hibrido"}]
        if not geneticas:
            eje = figura.add_subplot(111)
            eje.text(.5, .5, "Sin ejecuciones genéticas", ha="center", va="center", transform=eje.transAxes)
            eje.set_axis_off()
        else:
            eje_mutacion = figura.add_subplot(2, 2, 1)
            eje_local = figura.add_subplot(2, 2, 2)
            for etiqueta, corridas in grupos.items():
                corridas = [e for e in corridas if e.metodo in {"genetico", "hibrido"} and e.historial]
                if not corridas:
                    continue
                por_generacion: dict[int, list[float]] = defaultdict(list)
                mejoras_generacion: dict[int, list[float]] = defaultdict(list)
                for ejecucion in corridas:
                    for registro in ejecucion.historial:
                        generacion = int(registro["generacion"])
                        por_generacion[generacion].append(float(registro.get("prob_mutacion_usada", 0)))
                        mejoras_generacion[generacion].append(float(registro.get("mejoras_busqueda_local", 0)))
                xs = sorted(por_generacion)
                eje_mutacion.plot(xs, [median(por_generacion[x]) for x in xs], label=etiqueta)
                eje_local.plot(xs, [median(mejoras_generacion[x]) for x in xs], label=etiqueta)
            eje_mutacion.set(title="Tasa de mutación", xlabel="Generación", ylabel="Probabilidad")
            eje_local.set(title="Mejoras de búsqueda local", xlabel="Generación", ylabel="Mejoras")
            eje_mutacion.legend(fontsize=7)
            eje_local.legend(fontsize=7)
            etiquetas = [_etiqueta(e) for e in geneticas]
            unicas = list(dict.fromkeys(etiquetas))
            eje_eval = figura.add_subplot(2, 2, 3)
            eje_tiempo = figura.add_subplot(2, 2, 4)
            for eje, campos, titulo, unidad in (
                (eje_eval, ("evaluaciones_inicializacion", "evaluaciones_evolucion", "evaluaciones_busqueda_local"), "Evaluaciones por fase", "Evaluaciones"),
                (eje_tiempo, ("tiempo_inicializacion", "tiempo_evolucion", "tiempo_busqueda_local"), "Tiempo por fase", "Segundos"),
            ):
                fondo = [0.0] * len(unicas)
                for campo, nombre, color in zip(campos, ("Inicialización", "Evolución", "Búsqueda local"), ("#4c78a8", "#72b7b2", "#f2cf5b")):
                    valores = [median([float(getattr(e, campo, 0)) for e in geneticas if _etiqueta(e) == etiqueta]) for etiqueta in unicas]
                    eje.bar(unicas, valores, bottom=fondo, label=nombre, color=color)
                    fondo = [a + b for a, b in zip(fondo, valores)]
                eje.set_title(titulo)
                eje.set_ylabel(unidad)
                eje.tick_params(axis="x", rotation=12)
                eje.legend(fontsize=6)
        nota = "Tasas, mejoras y costos observados; cero indica componente desactivado o no registrado."
    else:
        eje = figura.add_subplot(111)
        ejecuciones_validas = [e for corridas in grupos.values() for e in corridas]
        if len(grupos) < 2 or any(e.metodo not in {"genetico", "hibrido"} for e in ejecuciones_validas):
            eje.text(
                .5, .5, "Disponible en el modo\nAnálisis de parámetros del algoritmo genético",
                ha="center", va="center", transform=eje.transAxes,
            )
            eje.set_axis_off()
            nota = "Ejecuta dos o más configuraciones genéticas variando un parámetro a la vez."
            figura.tight_layout(rect=(0, 0.03, 1, .94))
            return nota
        etiquetas = list(grupos)
        tasas = [sum(e.factible for e in grupos[k]) / len(grupos[k]) * 100 for k in etiquetas]
        penalizaciones = [
            median([e.penalizacion_blanda for e in grupos[k] if e.factible])
            if any(e.factible for e in grupos[k]) else None
            for k in etiquetas
        ]
        posiciones = list(range(len(etiquetas)))
        eje.bar(posiciones, tasas, color="#1f6f8b", alpha=.78, label="Factibilidad")
        eje.set_ylabel("Factibilidad (%)")
        eje.set_ylim(0, 105)
        eje.set_xticks(posiciones, etiquetas, rotation=18, ha="right")
        segundo = eje.twinx()
        puntos = [(i, v) for i, v in enumerate(penalizaciones) if v is not None]
        if puntos:
            segundo.plot([p[0] for p in puntos], [p[1] for p in puntos], "o-", color="#b7791f", label="Mediana blanda factible")
        segundo.set_ylabel("Penalización factible")
        nota = "Cada etiqueta cambia un solo parámetro respecto de la configuración base."
    figura.tight_layout(rect=(0, 0.03, 1, .94))
    return nota


def exportar_graficas(
    ejecuciones: Sequence[Any], carpeta: str | Path, incluir_parametros: bool = False,
) -> tuple[Path, ...]:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    vistas = ["factibilidad", "penalizaciones", "tiempos", "convergencia", "convergencia_evaluaciones", "operadores"]
    if incluir_parametros:
        vistas.append("parametros")
    rutas = []
    for vista in vistas:
        figura = Figure(figsize=(9, 5.2), dpi=120, facecolor="white")
        FigureCanvasAgg(figura)
        nota = dibujar_resultados(figura, ejecuciones, vista)
        figura.text(.5, .01, nota, ha="center", fontsize=8, color="#5d6d7e")
        ruta = destino / f"{vista}.png"
        figura.savefig(ruta, dpi=120, bbox_inches="tight")
        rutas.append(ruta)
    return tuple(rutas)

