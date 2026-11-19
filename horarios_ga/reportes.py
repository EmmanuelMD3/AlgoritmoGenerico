"""Exportacion de horarios, resumen, historial y grafica de evolucion."""
from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from .genetico import Resultado
from .fitness import indices_conflictivos
from .modelo import Problema


def hora_final(problema: Problema, inicio: int, duracion: int) -> str:
    base = datetime.strptime(problema.horas[inicio], "%H:%M")
    return (
        base + timedelta(minutes=problema.duracion_bloque_minutos * duracion)
    ).strftime("%H:%M")


def exportar_horario_csv(
    problema: Problema, resultado: Resultado, ruta: str | Path,
) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        csvw = csv.writer(f)
        conflictivos = indices_conflictivos(problema, resultado.cromosoma)
        csvw.writerow(["sesion", "materia", "grupo", "docente", "dia", "inicio", "fin", "salon", "violacion_dura"])
        for idx, (sesion, (dia, bloque, salon)) in enumerate(zip(problema.sesiones, resultado.cromosoma)):
            csvw.writerow([
                sesion.id, sesion.materia, sesion.grupo,
                problema.docentes[sesion.docente].nombre, problema.dias[dia],
                problema.horas[bloque], hora_final(problema, bloque, sesion.duracion),
                problema.salones[salon].id,
                "SI" if idx in conflictivos else "NO",
            ])
    return ruta


def exportar_historial_csv(resultado: Resultado, ruta: str | Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        csvw = csv.writer(f)
        csvw.writerow([
            "generacion", "mejor_fitness", "fitness_promedio", "conflictos_duros",
            "penalizacion_blanda", "huecos", "diversidad", "factible",
            "prob_mutacion", "evaluaciones_acumuladas", "aplicaciones_busqueda_local",
            "mejoras_busqueda_local", "mejora_global", "estancada",
        ])
        for r in resultado.historial:
            csvw.writerow([
                r.generacion, r.mejor_fitness, round(r.media_fitness, 2),
                r.conflictos_duros, r.penalizacion_blanda, r.huecos,
                round(r.diversidad, 4), "SI" if r.factible else "NO",
                round(r.prob_mutacion_usada, 6), r.evaluaciones_acumuladas,
                r.aplicaciones_busqueda_local, r.mejoras_busqueda_local,
                "SI" if r.mejoro_global else "NO", "SI" if r.estancada else "NO",
            ])
    return ruta


def exportar_horarios_html(
    problema: Problema, resultado: Resultado, ruta: str | Path,
) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(_html_horarios(problema, resultado), encoding="utf-8")
    return ruta


def exportar(problema: Problema, resultado: Resultado, carpeta: str | Path) -> tuple[Path, ...]:
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    archivos: list[Path] = []

    ruta = exportar_horario_csv(problema, resultado, carpeta / "horario_sesiones.csv")
    archivos.append(ruta)

    ruta = exportar_historial_csv(resultado, carpeta / "evolucion.csv")
    archivos.append(ruta)

    ruta = carpeta / "resumen.json"
    ruta.write_text(json.dumps({
        "configuracion": asdict(resultado.configuracion),
        "sesiones": len(problema.sesiones),
        "fitness_inicial": resultado.inicial.fitness,
        "fitness_final": resultado.evaluacion.fitness,
        "violaciones_duras": resultado.evaluacion.desglose_duro(),
        "total_violaciones_duras": resultado.evaluacion.duras,
        "criterios_blandos": resultado.evaluacion.desglose_blando(),
        "penalizacion_blanda": resultado.evaluacion.penalizacion_blanda,
        "factible": resultado.evaluacion.factible,
        "razones_no_factible": resultado.evaluacion.razones_no_factible(),
        "motivo_parada": resultado.motivo_parada,
        "estadisticas_ejecucion": asdict(resultado.estadisticas),
        "generaciones_ejecutadas": resultado.historial[-1].generacion,
        "nota": "Datos de demostracion simulados; resultados reales del algoritmo sobre esos datos.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    archivos.append(ruta)

    ruta = exportar_horarios_html(problema, resultado, carpeta / "horarios_por_grupo.html")
    archivos.append(ruta)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return tuple(archivos)  # algoritmo funcional; la grafica es opcional
    ruta = carpeta / "evolucion.png"
    xs = [r.generacion for r in resultado.historial]
    ys = [r.mejor_fitness for r in resultado.historial]
    medias = [r.media_fitness for r in resultado.historial]
    fig, (ax, ax_calidad) = plt.subplots(1, 2, figsize=(12, 5.2))
    ax.plot(xs, ys, label="Mejor individuo", linewidth=2)
    ax.plot(xs, medias, label="Promedio de población", alpha=0.8)
    ax.set(title="Evolución del fitness", xlabel="Generación", ylabel="Fitness")
    ax.grid(alpha=0.25)
    ax.legend()
    ax_calidad.step(xs, [r.conflictos_duros for r in resultado.historial], where="post", label="Duras")
    ax_calidad.plot(xs, [r.penalizacion_blanda for r in resultado.historial], label="Penalización blanda")
    locales = [r for r in resultado.historial if r.aplicaciones_busqueda_local]
    if locales:
        ax_calidad.scatter(
            [r.generacion for r in locales], [r.penalizacion_blanda for r in locales],
            marker="*", color="#16803c", label="Búsqueda local",
        )
    ax_calidad.set(title="Calidad académica", xlabel="Generación", ylabel="Cantidad / penalización")
    ax_calidad.grid(alpha=0.25)
    ax_calidad.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=210)
    plt.close(fig)
    archivos.append(ruta)
    return tuple(archivos)


def exportar_horario_imagen(
    problema: Problema,
    resultado: Resultado,
    ruta: str | Path,
    modo: str = "grupo",
    identificador: str | None = None,
) -> Path:
    """Exporta como PNG una vista semanal por grupo, docente o salón."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if modo not in {"grupo", "docente", "salon"}:
        raise ValueError("El modo debe ser grupo, docente o salón")
    if identificador is None:
        opciones = (
            list(problema.grupos) if modo == "grupo" else
            list(problema.docentes) if modo == "docente" else
            [salon.id for salon in problema.salones]
        )
        if not opciones:
            raise ValueError("No hay elementos para exportar")
        identificador = opciones[0]

    celdas = [["" for _ in problema.dias] for _ in problema.horas]
    for sesion, (dia, inicio, salon_idx) in zip(problema.sesiones, resultado.cromosoma):
        salon_id = problema.salones[salon_idx].id
        coincide = (
            (modo == "grupo" and sesion.grupo == identificador)
            or (modo == "docente" and sesion.docente == identificador)
            or (modo == "salon" and salon_id == identificador)
        )
        if not coincide:
            continue
        texto = f"{sesion.materia}\n{problema.docentes[sesion.docente].nombre}\n{salon_id}"
        for bloque in range(inicio, inicio + sesion.duracion):
            sufijo = "\n(continuación)" if bloque != inicio else ""
            actual = celdas[bloque][dia]
            celdas[bloque][dia] = (actual + "\n——\n" if actual else "") + texto + sufijo

    alto = max(5.5, len(problema.horas) * 0.72)
    fig, ax = plt.subplots(figsize=(13, alto))
    ax.axis("off")
    tabla = ax.table(
        cellText=celdas, rowLabels=problema.horas, colLabels=problema.dias,
        loc="center", cellLoc="center",
    )
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(8)
    tabla.scale(1, 2.2)
    ax.set_title(f"Horario por {modo}: {identificador}", fontsize=15, pad=18)
    fig.tight_layout()
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return destino


def _html_horarios(problema: Problema, resultado: Resultado) -> str:
    ocupacion = defaultdict(list)
    conflictivos = indices_conflictivos(problema, resultado.cromosoma)
    for idx, (sesion, (dia, inicio, salon)) in enumerate(zip(problema.sesiones, resultado.cromosoma)):
        for bloque in range(inicio, inicio + sesion.duracion):
            ocupacion[(sesion.grupo, dia, bloque)].append((sesion, salon, bloque == inicio, idx in conflictivos))

    partes = ["""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Horarios universitarios — algoritmo genético</title>
<style>
body{font:15px/1.45 Arial,sans-serif;color:#111;background:#fff;margin:32px auto;max-width:1160px}
h1,h2{margin:16px 0 8px}p{margin:8px 0 18px}
table{width:100%;border-collapse:collapse;table-layout:fixed;margin:12px 0 42px}
th,td{border:1px solid #888;padding:9px 7px;vertical-align:top;overflow-wrap:anywhere}
th{background:#e9e9e9}td{height:66px}.slot{background:#f5f5f5;font-weight:bold;width:90px}
.aula{font-size:12px;color:#444}.colision{border-left:4px solid #222;background:#ededed}
small{color:#555}@media print{body{margin:12mm;max-width:none}h2{break-before:page}h2:first-of-type{break-before:auto}table{break-inside:avoid}}
</style></head><body><h1>Horarios universitarios</h1>"""]
    e = resultado.evaluacion
    factible = "Sí, sin conflictos críticos" if e.factible else "No, revisar conflictos pendientes"
    partes.append(f"<p><strong>Fitness:</strong> {e.fitness} &nbsp; "
                  f"<strong>Conflictos críticos:</strong> {e.duras} &nbsp; "
                  f"<strong>Penalización blanda:</strong> {e.penalizacion_blanda} &nbsp; "
                  f"<strong>Factible:</strong> {factible}</p>")
    if not e.factible:
        razones = "; ".join(html.escape(razon) for razon in e.razones_no_factible())
        partes.append(f"<p><strong>Razones:</strong> {razones}</p>")
    partes.append("<p><small>Proyecto académico. Los datos son simulados; la distribución fue calculada "
                  "por el algoritmo genético.</small></p>")
    for grupo in problema.grupos:
        partes.append(f"<h2>Grupo {html.escape(grupo)}</h2><table><thead><tr><th>Hora</th>")
        for dia in problema.dias:
            partes.append(f"<th>{html.escape(dia)}</th>")
        partes.append("</tr></thead><tbody>")
        for bloque, hora in enumerate(problema.horas):
            siguiente = hora_final(problema, bloque, 1)
            partes.append(f'<tr><td class="slot">{hora}–{siguiente}</td>')
            for dia in range(len(problema.dias)):
                clases = ocupacion[(grupo, dia, bloque)]
                cls = ' class="colision"' if len(clases) > 1 or any(c[3] for c in clases) else ""
                contenido = "<hr>".join(
                    f"<strong>{html.escape(sesion.materia)}</strong>"
                    f"<div class='aula'>{html.escape(problema.docentes[sesion.docente].nombre)}"
                    f" · {html.escape(problema.salones[salon].id)}"
                    f"{' · continuación' if not primera else ''}</div>"
                    for sesion, salon, primera, _conflicto in clases
                )
                partes.append(f"<td{cls}>{contenido}</td>")
            partes.append("</tr>")
        partes.append("</tbody></table>")
    partes.append("</body></html>")
    return "\n".join(partes)
