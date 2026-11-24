"""Dashboard profesional de configuración y análisis evolutivo."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from time import monotonic
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Mapping, Sequence

from horarios_ga.fitness import Evaluacion, PESOS_BLANDOS, PESOS_DUROS
from horarios_ga.genetico import Configuracion, Registro, Resultado
from horarios_ga.diagnostico import DiagnosticoHorario, formatear_diagnostico
from .componentes import PanelDesplazable, SeccionPlegable, TarjetaKPI
from .estilos import (
    ADVERTENCIA, AZUL, AZUL_MEDIO, EXITO, PANEL, PELIGRO, SECUNDARIO, TEXTO,
)


PARAMETROS_POR_SECCION = (
    ("Configuración general", True, (
        ("variante", "Modo de optimización", "Clásico conserva el AG anterior; híbrido habilita los operadores avanzados."),
        ("poblacion", "Tamaño de población", "Horarios candidatos evaluados por generación."),
        ("generaciones", "Generaciones máximas", "Límite evolutivo; puede terminar antes por calidad."),
        ("semilla", "Semilla aleatoria", "Permite reproducir exactamente una ejecución."),
        ("presupuesto_evaluaciones", "Máximo de evaluaciones", "0 no limita; otro valor debe alcanzar al menos la población."),
    )),
    ("Operadores genéticos", True, (
        ("prob_cruza", "Probabilidad de cruza", "Probabilidad de combinar cada pareja de padres (0 a 1)."),
        ("prob_mutacion", "Probabilidad de mutación", "Probabilidad de cambiar cada gen (0 a 1)."),
        ("elitismo", "Individuos elitistas", "Mejores horarios conservados sin cambios."),
        ("torneo", "Tamaño del torneo", "Candidatos que compiten en cada selección."),
    )),
    ("Parámetros avanzados", False, (
        ("mutacion_dirigida", "Mutación dirigida", "Fuerza cambios sobre sesiones conflictivas (0 a 1)."),
        ("prob_reparacion", "Reparación local", "Intenta mejorar descendientes sin aceptar retrocesos (0 a 1)."),
        ("inmigrantes", "Inmigrantes aleatorios", "Fracción renovada para preservar diversidad (0 a <1)."),
    )),
    ("Inicialización híbrida", False, (
        ("inicializacion_heuristica", "Activar inicialización heurística", "Sólo actúa en modo híbrido y no conoce soluciones testigo."),
        ("porcentaje_inicializacion_heuristica", "Fracción heurística", "Proporción constructiva de la población inicial (0 a 0.5)."),
        ("reparacion_avanzada", "Reparación dirigida avanzada", "Explora dominios críticos y movimientos coordinados; el modo clásico conserva la reparación histórica."),
        ("reinicio_estancamiento", "Reinicio parcial por estancamiento", "Inyecta un 12 % de individuos nuevos en pulsos periódicos sin reemplazar élites."),
    )),
    ("Búsqueda local híbrida", False, (
        ("busqueda_local", "Activar búsqueda local", "Refina candidatos sin aceptar retrocesos lexicográficos."),
        ("estrategia_busqueda_local", "Aplicar sobre", "Mejores, muestra aleatoria o sólo durante estancamiento."),
        ("vecindario_busqueda_local", "Vecindario", "Reasignación, intercambio de sesiones o ambos."),
        ("criterio_busqueda_local", "Aceptación", "Primera mejora o mejor vecino revisado."),
        ("frecuencia_busqueda_local", "Frecuencia (generaciones)", "Cada cuántas generaciones puede ejecutarse."),
        ("porcentaje_busqueda_local", "Fracción refinada", "Proporción de individuos que recibe búsqueda local."),
        ("evaluaciones_busqueda_local", "Evaluaciones por aplicación", "Presupuesto máximo de vecinos por individuo."),
        ("mejoras_busqueda_local", "Mejoras por aplicación", "Límite de movimientos aceptados por individuo."),
    )),
    ("Mutación adaptativa", False, (
        ("mutacion_adaptativa", "Activar adaptación", "Ajusta la mutación por estancamiento y diversidad."),
        ("mutacion_min", "Tasa mínima", "Límite inferior de mutación adaptativa."),
        ("mutacion_max", "Tasa máxima", "Límite superior de mutación adaptativa."),
        ("estancamiento_mutacion", "Umbral de estancamiento", "Generaciones sin mejora que elevan exploración."),
        ("umbral_diversidad", "Umbral de diversidad", "Por debajo de este valor aumenta la mutación."),
        ("factor_incremento_mutacion", "Factor de incremento", "Multiplicador mayor que 1 cuando falta exploración."),
        ("factor_recuperacion_mutacion", "Factor de recuperación", "Factor entre 0 y 1 para regresar a la tasa base."),
    )),
    ("Parada anticipada", False, (
        ("parada_sin_mejora", "Generaciones sin mejora", "Estancamiento permitido después de alcanzar calidad; 0 desactiva."),
        ("objetivo_penalizacion_blanda", "Objetivo blando máximo", "Penalización requerida, además de factibilidad, para poder parar."),
    )),
)

# Alias plano conservado para código que inspeccionaba la definición anterior.
PARAMETROS = tuple(
    parametro
    for _titulo, _expandida, parametros in PARAMETROS_POR_SECCION
    for parametro in parametros
)

VISTAS_GRAFICA = (
    ("factibilidad", "Factibilidad"),
    ("calidad", "Calidad académica"),
    ("fitness", "Fitness"),
    ("diversidad", "Diversidad"),
)

MOTIVOS_PARADA = {
    "generaciones_completadas": "Límite de generaciones",
    "calidad_sin_mejora": "Calidad + estancamiento",
    "cancelada": "Cancelación solicitada",
    "presupuesto_evaluaciones": "Presupuesto máximo de evaluaciones",
}


def configuracion_desde_textos(valores: Mapping[str, str]) -> Configuracion:
    """Convierte los controles usando la validación real del motor."""
    defaults = Configuracion()
    try:
        config = Configuracion(
            poblacion=int(valores["poblacion"]),
            generaciones=int(valores["generaciones"]),
            prob_cruza=float(valores["prob_cruza"]),
            prob_mutacion=float(valores["prob_mutacion"]),
            elitismo=int(valores["elitismo"]),
            torneo=int(valores["torneo"]),
            semilla=int(valores["semilla"]),
            mutacion_dirigida=float(valores.get("mutacion_dirigida", str(defaults.mutacion_dirigida))),
            prob_reparacion=float(valores.get("prob_reparacion", str(defaults.prob_reparacion))),
            inmigrantes=float(valores.get("inmigrantes", str(defaults.inmigrantes))),
            parada_sin_mejora=int(valores.get("parada_sin_mejora", str(defaults.parada_sin_mejora))),
            objetivo_penalizacion_blanda=int(valores.get(
                "objetivo_penalizacion_blanda", str(defaults.objetivo_penalizacion_blanda),
            )),
            variante=valores.get("variante", defaults.variante).strip().lower(),
            inicializacion_heuristica=valores.get("inicializacion_heuristica", str(defaults.inicializacion_heuristica)).strip().lower() in {"1", "true", "sí", "si"},
            porcentaje_inicializacion_heuristica=float(valores.get("porcentaje_inicializacion_heuristica", str(defaults.porcentaje_inicializacion_heuristica))),
            busqueda_local=valores.get("busqueda_local", str(defaults.busqueda_local)).strip().lower() in {"1", "true", "sí", "si"},
            estrategia_busqueda_local=valores.get("estrategia_busqueda_local", defaults.estrategia_busqueda_local).strip().lower(),
            vecindario_busqueda_local=valores.get("vecindario_busqueda_local", defaults.vecindario_busqueda_local).strip().lower(),
            criterio_busqueda_local=valores.get("criterio_busqueda_local", defaults.criterio_busqueda_local).strip().lower(),
            frecuencia_busqueda_local=int(valores.get("frecuencia_busqueda_local", str(defaults.frecuencia_busqueda_local))),
            porcentaje_busqueda_local=float(valores.get("porcentaje_busqueda_local", str(defaults.porcentaje_busqueda_local))),
            evaluaciones_busqueda_local=int(valores.get("evaluaciones_busqueda_local", str(defaults.evaluaciones_busqueda_local))),
            mejoras_busqueda_local=int(valores.get("mejoras_busqueda_local", str(defaults.mejoras_busqueda_local))),
            mutacion_adaptativa=valores.get("mutacion_adaptativa", str(defaults.mutacion_adaptativa)).strip().lower() in {"1", "true", "sí", "si"},
            mutacion_min=float(valores.get("mutacion_min", str(defaults.mutacion_min))),
            mutacion_max=float(valores.get("mutacion_max", str(defaults.mutacion_max))),
            estancamiento_mutacion=int(valores.get("estancamiento_mutacion", str(defaults.estancamiento_mutacion))),
            umbral_diversidad=float(valores.get("umbral_diversidad", str(defaults.umbral_diversidad))),
            factor_incremento_mutacion=float(valores.get("factor_incremento_mutacion", str(defaults.factor_incremento_mutacion))),
            factor_recuperacion_mutacion=float(valores.get("factor_recuperacion_mutacion", str(defaults.factor_recuperacion_mutacion))),
            presupuesto_evaluaciones=int(valores.get("presupuesto_evaluaciones", str(defaults.presupuesto_evaluaciones))),
            reparacion_avanzada=valores.get(
                "reparacion_avanzada", str(defaults.reparacion_avanzada),
            ).strip().lower() in {"1", "true", "sí", "si"},
            reinicio_estancamiento=valores.get(
                "reinicio_estancamiento", str(defaults.reinicio_estancamiento),
            ).strip().lower() in {"1", "true", "sí", "si"},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Los parámetros contienen un valor no válido") from exc
    config.validar()
    return config


def filas_desglose(evaluacion: Evaluacion) -> tuple[tuple[str, str, int, int, int], ...]:
    """Filas respaldadas por cantidades y pesos oficiales del motor."""
    filas: list[tuple[str, str, int, int, int]] = []
    for (nombre, cantidad), peso in zip(
        evaluacion.desglose_duro().items(), PESOS_DUROS.values(), strict=True,
    ):
        filas.append(("Dura", nombre, cantidad, peso, cantidad * peso))
    for (nombre, cantidad), peso in zip(
        evaluacion.desglose_blando().items(), PESOS_BLANDOS.values(), strict=True,
    ):
        filas.append(("Blanda", nombre, cantidad, peso, cantidad * peso))
    return tuple(filas)


def construir_comparacion(resultado: Resultado) -> tuple[tuple[str, str, str, str, str], ...]:
    """Comparación inicial/final sin porcentajes ni prioridades inventadas."""
    inicial, final = resultado.inicial, resultado.evaluacion

    def diferencia(valor_inicial: int, valor_final: int) -> str:
        cambio = valor_final - valor_inicial
        return f"{cambio:+d}" if cambio else "0"

    def interpretacion_menor(inicial_n: int, final_n: int, mejora: str) -> str:
        if final_n < inicial_n:
            return mejora
        if final_n > inicial_n:
            return "Empeoró"
        return "Sin cambio"

    fact_inicial = "Factible" if inicial.factible else "No factible"
    fact_final = "Factible" if final.factible else "No factible"
    return (
        (
            "Violaciones duras", str(inicial.duras), str(final.duras),
            diferencia(inicial.duras, final.duras),
            interpretacion_menor(inicial.duras, final.duras, "Mejora prioritaria"),
        ),
        (
            "Penalización blanda", str(inicial.penalizacion_blanda), str(final.penalizacion_blanda),
            diferencia(inicial.penalizacion_blanda, final.penalizacion_blanda),
            interpretacion_menor(
                inicial.penalizacion_blanda, final.penalizacion_blanda, "Mejora académica",
            ),
        ),
        (
            "Fitness", str(inicial.fitness), str(final.fitness),
            diferencia(inicial.fitness, final.fitness),
            "Indicador secundario; no sustituye la prioridad lexicográfica",
        ),
        (
            "Factibilidad", fact_inicial, fact_final, "—",
            "Cambió" if fact_inicial != fact_final else "Sin cambio",
        ),
    )


def metricas_resultado(
    resultado: Resultado | None,
    segundos: float = 0.0,
    cancelada: bool = False,
) -> dict[str, tuple[str, str, str]]:
    """Valores KPI finales: ``valor, detalle, tono``."""
    if resultado is None:
        return {}
    evaluacion = resultado.evaluacion
    ultimo = resultado.historial[-1] if resultado.historial else None
    generacion = ultimo.generacion if ultimo else 0
    diversidad = ultimo.diversidad if ultimo else 0.0
    estado = "Factible" if evaluacion.factible else "No factible"
    tono_estado = "success" if evaluacion.factible else "danger"
    detalle_estado = "Resultado parcial · ejecución cancelada" if cancelada else "Según restricciones duras"
    motivo = MOTIVOS_PARADA.get(resultado.motivo_parada, resultado.motivo_parada or "No indicado")
    if cancelada:
        motivo = "Cancelación solicitada"
    return {
        "estado": (estado, detalle_estado, "warning" if cancelada else tono_estado),
        "duras": (str(evaluacion.duras), "Incumplimientos sin ponderar", "success" if not evaluacion.duras else "danger"),
        "blandas": (str(evaluacion.penalizacion_blanda), "Suma ponderada · menor es mejor", "warning" if evaluacion.penalizacion_blanda else "success"),
        "fitness": (str(evaluacion.fitness), "Mejor individuo según prioridad", "neutral"),
        "diversidad": (f"{diversidad:.1%}", "Cromosomas únicos en población", "neutral"),
        "generaciones": (f"{generacion} / {resultado.configuracion.generaciones}", "Generaciones realmente evaluadas", "neutral"),
        "tiempo": (f"{segundos:.2f} s", "Tiempo de pared transcurrido", "neutral"),
        "motivo": (motivo, "Condición que finalizó la ejecución", "warning" if cancelada else "neutral"),
    }


def resumen_finalizacion(resultado: Resultado, cancelada: bool = False) -> str:
    e = resultado.evaluacion
    prefijo = "Ejecución cancelada; se conserva el mejor resultado parcial." if cancelada else "Ejecución finalizada."
    if e.factible:
        estado = (
            f"El horario es factible: no presenta violaciones duras. Su penalización blanda "
            f"ponderada es {e.penalizacion_blanda}. Factible no significa óptimo global."
        )
    else:
        razones = "; ".join(e.razones_no_factible()) or "No se recibió un desglose de causas."
        estado = f"El horario no es factible. Razones: {razones}."
    estadisticas = resultado.estadisticas
    detalle_hibrido = (
        f"\n\nModo: {estadisticas.variante}. Evaluaciones reales: {estadisticas.evaluaciones_totales}; "
        f"población inicial aleatoria/heurística: {estadisticas.individuos_aleatorios}/"
        f"{estadisticas.individuos_heuristicos}. Tiempos (s): inicialización "
        f"{estadisticas.tiempo_inicializacion:.3f}, evolución {estadisticas.tiempo_evolucion:.3f}, "
        f"espera didáctica excluida {estadisticas.tiempo_espera_didactica:.3f}."
    )
    if resultado.configuracion.variante == "hibrido" and resultado.configuracion.busqueda_local:
        detalle_hibrido += (
            f" Búsqueda local: {estadisticas.aplicaciones_busqueda_local} aplicaciones, "
            f"{estadisticas.individuos_mejorados_busqueda_local} individuos mejorados, "
            f"{estadisticas.mejoras_busqueda_local} movimientos y "
            f"{estadisticas.evaluaciones_busqueda_local} evaluaciones en "
            f"{estadisticas.tiempo_busqueda_local:.3f} s."
        )
    return (
        f"{prefijo}\n\n{estado}\n\n"
        f"Motivo de finalización: {MOTIVOS_PARADA.get(resultado.motivo_parada, resultado.motivo_parada)}. "
        f"Se evaluaron {resultado.historial[-1].generacion if resultado.historial else 0} "
        f"de {resultado.configuracion.generaciones} generaciones configuradas."
        f"{detalle_hibrido}"
    )


def debe_redibujar(
    generacion: int,
    total: int,
    ultimo_redibujo: float,
    ahora: float,
    intervalo: float = 0.20,
) -> bool:
    """Agrupa redibujos sin descartar registros históricos."""
    if generacion in {0, total}:
        return True
    paso = max(1, total // 80)
    return generacion % paso == 0 and ahora - ultimo_redibujo >= intervalo


def dibujar_historial(eje, registros: Sequence[Registro], vista: str) -> str:
    """Dibuja una vista usando exclusivamente puntos del historial real."""
    eje.clear()
    if vista not in {clave for clave, _ in VISTAS_GRAFICA}:
        raise ValueError(f"Vista gráfica desconocida: {vista}")
    if not registros:
        titulo = dict(VISTAS_GRAFICA)[vista]
        eje.set_title(titulo)
        eje.text(.5, .5, "Sin datos · ejecuta el algoritmo", ha="center", va="center", transform=eje.transAxes, color=SECUNDARIO)
        eje.set_xlabel("Generación")
        eje.grid(alpha=.16)
        return "No hay puntos históricos disponibles."

    xs = [r.generacion for r in registros]
    nota = ""
    if vista == "factibilidad":
        ys = [r.conflictos_duros for r in registros]
        eje.step(xs, ys, where="post", color=PELIGRO, linewidth=2, label="Violaciones duras")
        factibles = [r for r in registros if r.factible]
        if factibles:
            primera = factibles[0]
            eje.axvline(primera.generacion, color=EXITO, linestyle="--", linewidth=1.2)
            eje.scatter([primera.generacion], [primera.conflictos_duros], color=EXITO, zorder=3, label=f"Primera factible: G{primera.generacion}")
            nota = f"Primera generación factible: {primera.generacion}."
        else:
            nota = "No se observó una generación factible."
        eje.set(title="Evolución de la factibilidad", ylabel="Violaciones")
        eje.set_ylim(bottom=0)
    elif vista == "calidad":
        ys = [r.penalizacion_blanda for r in registros]
        eje.plot(xs, ys, color=ADVERTENCIA, linewidth=2, label="Penalización blanda ponderada")
        candidatos = [r for r in registros if r.factible] or list(registros)
        mejor = min(candidatos, key=lambda r: r.penalizacion_blanda)
        etiqueta = "Mejor factible" if any(r.factible for r in registros) else "Menor observada"
        eje.scatter([mejor.generacion], [mejor.penalizacion_blanda], color=EXITO, zorder=3, label=f"{etiqueta}: {mejor.penalizacion_blanda}")
        nota = "La penalización es ponderada; menor es mejor."
        eje.set(title="Calidad académica del mejor individuo", ylabel="Penalización")
        eje.set_ylim(bottom=0)
    elif vista == "fitness":
        eje.plot(xs, [r.mejor_fitness for r in registros], color=AZUL_MEDIO, linewidth=2, label="Mejor individuo")
        eje.plot(xs, [r.media_fitness for r in registros], color="#7c8ea3", linewidth=1.3, label="Promedio poblacional")
        nota = "La selección es lexicográfica: duras → blandas → fitness."
        eje.set(title="Fitness y promedio poblacional", ylabel="Fitness")
        eje.text(
            .01, .96, "Prioridad: duras → blandas → fitness",
            transform=eje.transAxes, va="top", fontsize=7, color=SECUNDARIO,
        )
    else:
        eje.plot(xs, [r.diversidad * 100 for r in registros], color="#6f42c1", linewidth=2, label="Cromosomas únicos")
        nota = "Diversidad = cromosomas únicos / tamaño de población."
        eje.set(title="Diversidad poblacional", ylabel="Diversidad (%)")
        eje.set_ylim(0, 105)

    eje.set_xlabel("Generación")
    eje.grid(alpha=.22)
    eje.legend(fontsize=8, loc="best")
    return nota


def exportar_grafica_png(
    registros: Sequence[Registro], vista: str, ruta: str | Path,
) -> Path:
    """Exporta una vista histórica sin requerir una ventana Tk."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figura = Figure(figsize=(10, 5.2), dpi=120, facecolor="white")
    FigureCanvasAgg(figura)
    eje = figura.add_subplot(111)
    nota = dibujar_historial(eje, registros, vista)
    figura.text(.5, .015, nota, ha="center", fontsize=8, color=SECUNDARIO)
    figura.subplots_adjust(left=.10, right=.96, bottom=.16, top=.88)
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    figura.savefig(destino, dpi=180, facecolor="white")
    return destino


class VistaOptimizacion(ttk.Frame):
    def __init__(
        self,
        padre: tk.Misc,
        al_ejecutar: Callable[[], None],
        al_detener: Callable[[], None],
        al_limpiar: Callable[[], None],
        carpeta_resultados: Path | None = None,
    ):
        super().__init__(padre, padding=8)
        self.al_ejecutar = al_ejecutar
        self.al_detener = al_detener
        self.al_limpiar = al_limpiar
        self.carpeta_resultados = Path(carpeta_resultados or Path.cwd() / "resultados")
        self.variables: dict[str, tk.StringVar] = {}
        self.configuracion_activa: Configuracion | None = None
        self.registros: list[Registro] = []
        self.resultado: Resultado | None = None
        self._ultimo_redibujo = 0.0
        self.vista_grafica = tk.StringVar(value="factibilidad")
        self.escenario_actual = tk.StringVar(value="Escenario actual: datos de ejemplo")
        self.origen_resultado = tk.StringVar(value="Resultado mostrado: —")
        self.kpis: dict[str, TarjetaKPI] = {}

        paneles = ttk.Panedwindow(self, orient="horizontal")
        paneles.pack(fill="both", expand=True)
        izquierda = ttk.Frame(paneles, style="Panel.TFrame", padding=(10, 10), width=328)
        derecha = ttk.Frame(paneles, style="Panel.TFrame", padding=(12, 10))
        paneles.add(izquierda, weight=0)
        paneles.add(derecha, weight=1)
        self._crear_configuracion(izquierda)
        self._crear_dashboard(derecha)
        self.limpiar()

    def _crear_configuracion(self, padre: tk.Misc) -> None:
        cabecera = ttk.Frame(padre, style="Panel.TFrame")
        cabecera.pack(fill="x", pady=(0, 7))
        ttk.Label(cabecera, text="Configuración", style="PanelTitulo.TLabel").pack(anchor="w")
        ttk.Label(
            cabecera, text="Parámetros del experimento genético", style="Ayuda.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            cabecera, textvariable=self.escenario_actual, style="Ayuda.TLabel",
            wraplength=300, justify="left",
        ).pack(anchor="w", pady=(3, 0))

        desplazable = PanelDesplazable(padre, ancho=300)
        desplazable.pack(fill="both", expand=True)
        defaults = Configuracion()
        self.secciones_hibridas: list[SeccionPlegable] = []
        for titulo, expandida, parametros in PARAMETROS_POR_SECCION:
            seccion = SeccionPlegable(desplazable.interior, titulo, expandida)
            seccion.pack(fill="x", pady=(0, 7))
            if titulo in {"Inicialización híbrida", "Búsqueda local híbrida", "Mutación adaptativa"}:
                self.secciones_hibridas.append(seccion)
            for clave, etiqueta, ayuda in parametros:
                self._agregar_parametro(seccion.contenido, clave, etiqueta, ayuda, getattr(defaults, clave))
        self._actualizar_visibilidad_hibrida()

        acciones = ttk.Frame(padre, style="Panel.TFrame")
        acciones.pack(fill="x", pady=(8, 0))
        self.boton_ejecutar = ttk.Button(
            acciones, text="Ejecutar algoritmo", style="Primary.TButton", command=self.al_ejecutar,
        )
        self.boton_ejecutar.pack(fill="x", pady=(0, 5))
        fila = ttk.Frame(acciones, style="Panel.TFrame")
        fila.pack(fill="x")
        self.boton_detener = ttk.Button(
            fila, text="Detener", style="Danger.TButton", command=self.al_detener, state="disabled",
        )
        self.boton_detener.pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(fila, text="Restablecer", command=self.restablecer).pack(
            side="left", fill="x", expand=True, padx=(3, 0),
        )
        ttk.Button(acciones, text="Limpiar resultados", command=self.al_limpiar).pack(fill="x", pady=(5, 0))

    def _agregar_parametro(
        self, padre: tk.Misc, clave: str, etiqueta: str, ayuda: str, valor,
    ) -> None:
        fila = ttk.Frame(padre, style="Panel.TFrame")
        fila.pack(fill="x", pady=(2, 5))
        superior = ttk.Frame(fila, style="Panel.TFrame")
        superior.pack(fill="x")
        ttk.Label(superior, text=etiqueta, style="Campo.TLabel").pack(side="left")
        variable = tk.StringVar(value=str(valor))
        self.variables[clave] = variable
        opciones = {
            "variante": ("clasico", "hibrido"),
            "inicializacion_heuristica": ("False", "True"),
            "busqueda_local": ("False", "True"),
            "mutacion_adaptativa": ("False", "True"),
            "reparacion_avanzada": ("False", "True"),
            "reinicio_estancamiento": ("False", "True"),
            "estrategia_busqueda_local": ("mejores", "aleatoria", "estancamiento"),
            "vecindario_busqueda_local": ("reasignacion", "intercambio", "mixta"),
            "criterio_busqueda_local": ("primera", "mejor"),
            "porcentaje_inicializacion_heuristica": ("0.0", "0.1", "0.2", "0.3", "0.5"),
        }.get(clave)
        if opciones:
            control = ttk.Combobox(
                superior, textvariable=variable, values=opciones,
                state="readonly", width=12,
            )
            control.pack(side="right")
            if clave == "variante":
                control.bind("<<ComboboxSelected>>", lambda _evento: self._actualizar_visibilidad_hibrida())
        else:
            ttk.Entry(superior, textvariable=variable, width=10, justify="right").pack(side="right")
        ttk.Label(
            fila, text=ayuda, style="Ayuda.TLabel", wraplength=270, justify="left",
        ).pack(fill="x", pady=(2, 0))

    def _actualizar_visibilidad_hibrida(self) -> None:
        """Mantiene limpio el panel clásico y revela controles sólo al elegir híbrido."""
        if not hasattr(self, "secciones_hibridas") or "variante" not in self.variables:
            return
        mostrar = self.variables["variante"].get() == "hibrido"
        for seccion in self.secciones_hibridas:
            if mostrar:
                if not seccion.winfo_manager():
                    seccion.pack(fill="x", pady=(0, 7))
            else:
                seccion.pack_forget()

    def _crear_dashboard(self, padre: tk.Misc) -> None:
        self._crear_cabecera_ejecucion(padre)
        self._crear_kpis(padre)

        analitica = ttk.Panedwindow(padre, orient="vertical")
        analitica.pack(fill="both", expand=True, pady=(7, 0))
        graficas = ttk.Frame(analitica, style="Panel.TFrame")
        detalle = ttk.Frame(analitica, style="Panel.TFrame")
        analitica.add(graficas, weight=2)
        analitica.add(detalle, weight=2)
        self._crear_grafica(graficas)
        self._crear_panel_inferior(detalle)

    def _crear_cabecera_ejecucion(self, padre: tk.Misc) -> None:
        marco = tk.Frame(
            padre, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1,
            padx=11, pady=8,
        )
        marco.pack(fill="x")
        superior = tk.Frame(marco, bg=PANEL)
        superior.pack(fill="x")
        tk.Label(
            superior, text="Ejecución evolutiva", bg=PANEL, fg=AZUL,
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        self.estado_chip = tk.Label(
            superior, text="SIN EJECUTAR", bg="#eaf2f8", fg=AZUL,
            font=("Segoe UI Semibold", 8), padx=9, pady=3,
        )
        self.estado_chip.pack(side="right")
        self.cabecera_detalle = tk.StringVar(value="Configura los parámetros y ejecuta el algoritmo.")
        tk.Label(
            marco, textvariable=self.cabecera_detalle, bg=PANEL, fg=SECUNDARIO,
            font=("Segoe UI", 8), anchor="w",
        ).pack(fill="x", pady=(3, 1))
        tk.Label(
            marco, textvariable=self.origen_resultado, bg=PANEL, fg=AZUL,
            font=("Segoe UI Semibold", 8), anchor="w",
        ).pack(fill="x", pady=(0, 5))
        progreso_fila = tk.Frame(marco, bg=PANEL)
        progreso_fila.pack(fill="x")
        self.progreso = ttk.Progressbar(progreso_fila, mode="determinate", maximum=100)
        self.progreso.pack(side="left", fill="x", expand=True)
        self.progreso_texto = tk.StringVar(value="Generación — / —")
        tk.Label(
            progreso_fila, textvariable=self.progreso_texto, bg=PANEL, fg=TEXTO,
            font=("Segoe UI Semibold", 8), padx=8,
        ).pack(side="right")

    def _crear_kpis(self, padre: tk.Misc) -> None:
        marco = ttk.Frame(padre, style="Panel.TFrame")
        marco.pack(fill="x", pady=(7, 0))
        definiciones = (
            ("estado", "Estado del horario"),
            ("duras", "Violaciones duras"),
            ("blandas", "Penalización blanda"),
            ("fitness", "Fitness del mejor"),
            ("diversidad", "Diversidad poblacional"),
            ("generaciones", "Generaciones ejecutadas"),
            ("tiempo", "Tiempo de ejecución"),
            ("motivo", "Motivo de finalización"),
        )
        for indice, (clave, titulo) in enumerate(definiciones):
            tarjeta = TarjetaKPI(marco, titulo)
            tarjeta.grid(row=indice // 4, column=indice % 4, sticky="nsew", padx=3, pady=3)
            if clave == "motivo":
                tarjeta.valor.configure(
                    font=("Segoe UI Semibold", 10), wraplength=175, justify="left",
                )
            self.kpis[clave] = tarjeta
        for columna in range(4):
            marco.columnconfigure(columna, weight=1, uniform="kpi")

    def _crear_grafica(self, padre: tk.Misc) -> None:
        cabecera = ttk.Frame(padre, style="Panel.TFrame", padding=(5, 4))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Evolución", style="PanelTitulo.TLabel").pack(side="left", padx=(0, 8))
        for clave, etiqueta in VISTAS_GRAFICA:
            ttk.Radiobutton(
                cabecera, text=etiqueta, value=clave, variable=self.vista_grafica,
                command=lambda: self._redibujar(forzar=True),
            ).pack(side="left", padx=3)
        ttk.Button(cabecera, text="Exportar PNG", command=self._exportar_grafica).pack(side="right")

        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            self.figura = self.eje = self.canvas_grafica = None
            ttk.Label(
                padre, text="Instala Matplotlib para visualizar las gráficas.", style="Ayuda.TLabel",
            ).pack(fill="both", expand=True)
            return
        self.figura = Figure(figsize=(8.5, 1.8), dpi=100, facecolor=PANEL)
        self.eje = self.figura.add_subplot(111)
        self.figura.subplots_adjust(left=.09, right=.97, bottom=.40, top=.82)
        self.canvas_grafica = FigureCanvasTkAgg(self.figura, master=padre)
        self.canvas_grafica.get_tk_widget().pack(fill="both", expand=True)
        self.nota_grafica = tk.StringVar()
        ttk.Label(
            padre, textvariable=self.nota_grafica, style="Ayuda.TLabel", anchor="center",
        ).pack(fill="x", pady=(0, 3))

    def _crear_panel_inferior(self, padre: tk.Misc) -> None:
        vistas = ttk.Notebook(padre)
        vistas.pack(fill="both", expand=True)
        pagina_desglose = ttk.Frame(vistas, style="Panel.TFrame", padding=5)
        pagina_comparacion = ttk.Frame(vistas, style="Panel.TFrame", padding=5)
        pagina_resumen = ttk.Frame(vistas, style="Panel.TFrame", padding=7)
        pagina_diagnostico = ttk.Frame(vistas, style="Panel.TFrame", padding=7)
        vistas.add(pagina_desglose, text="Desglose académico")
        vistas.add(pagina_comparacion, text="Inicial vs. final")
        vistas.add(pagina_resumen, text="Resumen de finalización")
        vistas.add(pagina_diagnostico, text="Diagnóstico de conflictos")
        self._crear_desglose(pagina_desglose)
        self._crear_comparacion(pagina_comparacion)
        self.resumen_texto = tk.Text(
            pagina_resumen, wrap="word", relief="flat", bg=PANEL, fg=TEXTO,
            font=("Segoe UI", 9), padx=8, pady=6, height=5,
        )
        self.resumen_texto.pack(fill="both", expand=True)
        self.resumen_texto.configure(state="disabled")
        self.diagnostico_texto = tk.Text(
            pagina_diagnostico, wrap="word", relief="flat", bg=PANEL, fg=TEXTO,
            font=("Segoe UI", 9), padx=8, pady=6, height=5,
        )
        self.diagnostico_texto.pack(fill="both", expand=True)
        self.diagnostico_texto.configure(state="disabled")

    def _crear_desglose(self, padre: tk.Misc) -> None:
        columnas = ("tipo", "criterio", "cantidad", "peso", "contribucion")
        self.detalle = ttk.Treeview(padre, columns=columnas, show="headings", height=5)
        for clave, titulo, ancho in (
            ("tipo", "Tipo", 75), ("criterio", "Restricción", 260),
            ("cantidad", "Cantidad", 85), ("peso", "Peso", 70),
            ("contribucion", "Contribución ponderada", 145),
        ):
            self.detalle.heading(clave, text=titulo)
            self.detalle.column(clave, width=ancho, anchor="w" if clave == "criterio" else "center")
        self.detalle.tag_configure("dura_activa", foreground=PELIGRO)
        self.detalle.tag_configure("blanda_activa", foreground=ADVERTENCIA)
        self.detalle.tag_configure("cumplida", foreground=SECUNDARIO)
        barra = ttk.Scrollbar(padre, orient="vertical", command=self.detalle.yview)
        self.detalle.configure(yscrollcommand=barra.set)
        self.detalle.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def _crear_comparacion(self, padre: tk.Misc) -> None:
        columnas = ("metrica", "inicial", "final", "diferencia", "interpretacion")
        self.comparacion = ttk.Treeview(padre, columns=columnas, show="headings", height=4)
        for clave, titulo, ancho in (
            ("metrica", "Métrica", 155), ("inicial", "Inicial", 90),
            ("final", "Final", 90), ("diferencia", "Diferencia", 90),
            ("interpretacion", "Interpretación", 310),
        ):
            self.comparacion.heading(clave, text=titulo)
            self.comparacion.column(clave, width=ancho, anchor="w" if clave in {"metrica", "interpretacion"} else "center")
        self.comparacion.pack(fill="both", expand=True)

    def obtener_configuracion(self) -> Configuracion:
        return configuracion_desde_textos({clave: var.get() for clave, var in self.variables.items()})

    def establecer_escenario(self, texto: str) -> None:
        self.escenario_actual.set(f"Escenario actual: {texto}")

    def establecer_origen_resultado(self, nombre: str, huella: str, *, historico: bool = False) -> None:
        estado = "histórico · datos activos diferentes" if historico else "instantánea exacta activa"
        self.origen_resultado.set(
            f"Resultado mostrado: {nombre} · SHA-256 {huella[:12]}… · {estado}"
        )

    def restablecer(self) -> None:
        defaults = Configuracion()
        for clave, variable in self.variables.items():
            variable.set(str(getattr(defaults, clave)))
        self._actualizar_visibilidad_hibrida()

    def iniciar(self, config: Configuracion) -> None:
        self.configuracion_activa = config
        self.limpiar()
        self.resultado = None
        self._set_estado_chip("EN CURSO", "warning")
        self.cabecera_detalle.set(
            f"Modo {config.variante} · inicializando población y evaluando la generación 0…"
        )
        self.progreso_texto.set(f"Generación 0 / {config.generaciones}")
        self.kpis["estado"].establecer("En curso", "Ejecución asíncrona", "warning")
        self.kpis["generaciones"].establecer(f"0 / {config.generaciones}", "Generaciones evaluadas")
        self.kpis["motivo"].establecer("Procesando", "Todavía sin finalización")
        self.boton_ejecutar.configure(state="disabled")
        self.boton_detener.configure(state="normal")

    def actualizar(self, registro: Registro, total: int, segundos: float) -> None:
        if self.registros and self.registros[-1].generacion == registro.generacion:
            self.registros[-1] = registro
        else:
            self.registros.append(registro)
        tono = "success" if registro.factible else "danger"
        self.kpis["estado"].establecer(
            "Factible" if registro.factible else "No factible",
            "Mejor individuo actual · ejecución en curso", tono,
        )
        self.kpis["duras"].establecer(
            str(registro.conflictos_duros), "Incumplimientos sin ponderar",
            "success" if registro.conflictos_duros == 0 else "danger",
        )
        self.kpis["blandas"].establecer(
            str(registro.penalizacion_blanda), "Suma ponderada · menor es mejor",
            "success" if registro.penalizacion_blanda == 0 else "warning",
        )
        self.kpis["fitness"].establecer(str(registro.mejor_fitness), "Mejor según prioridad lexicográfica")
        self.kpis["diversidad"].establecer(f"{registro.diversidad:.1%}", "Cromosomas únicos en población")
        self.kpis["generaciones"].establecer(f"{registro.generacion} / {total}", "Generaciones evaluadas")
        self.kpis["tiempo"].establecer(f"{segundos:.2f} s", "Tiempo transcurrido")
        self.progreso.configure(value=(registro.generacion / total * 100) if total else 100)
        self.progreso_texto.set(f"Generación {registro.generacion} / {total}")
        detalle_avanzado = ""
        if self.configuracion_activa and self.configuracion_activa.variante == "hibrido":
            detalle_avanzado = f" · mutación {registro.prob_mutacion_usada:.3f} · evaluaciones {registro.evaluaciones_acumuladas}"
            if self.configuracion_activa.busqueda_local:
                detalle_avanzado += (
                    f" · búsqueda local {registro.aplicaciones_busqueda_local}/"
                    f"{registro.individuos_mejorados_busqueda_local}"
                )
        self.cabecera_detalle.set(
            f"Mejor actual · duras {registro.conflictos_duros} · "
            f"blanda {registro.penalizacion_blanda} · fitness {registro.mejor_fitness}"
            f"{detalle_avanzado}"
        )
        ahora = monotonic()
        if debe_redibujar(registro.generacion, total, self._ultimo_redibujo, ahora):
            self._redibujar(forzar=True)
            self._ultimo_redibujo = ahora

    def finalizar(
        self, resultado: Resultado, segundos: float, cancelada: bool = False,
        diagnostico: DiagnosticoHorario | None = None,
    ) -> None:
        self.resultado = resultado
        self.registros = list(resultado.historial)
        self._aplicar_metricas(metricas_resultado(resultado, segundos, cancelada))
        evaluacion = resultado.evaluacion
        if cancelada:
            self._set_estado_chip("CANCELADA", "warning")
        elif evaluacion.factible:
            self._set_estado_chip("FINALIZADA · FACTIBLE", "success")
        else:
            self._set_estado_chip("FINALIZADA · NO FACTIBLE", "danger")
        generacion = resultado.historial[-1].generacion if resultado.historial else 0
        self.progreso.configure(value=(generacion / resultado.configuracion.generaciones * 100))
        self.progreso_texto.set(f"Generación {generacion} / {resultado.configuracion.generaciones}")
        self.cabecera_detalle.set(
            f"Modo {resultado.configuracion.variante} · resultado {'parcial' if cancelada else 'final'} · duras {evaluacion.duras} · "
            f"penalización blanda {evaluacion.penalizacion_blanda} · fitness {evaluacion.fitness}"
        )
        self._actualizar_desglose(evaluacion)
        self._actualizar_comparacion(resultado)
        self._escribir_resumen(resumen_finalizacion(resultado, cancelada))
        self._escribir_diagnostico(
            formatear_diagnostico(diagnostico)
            if diagnostico is not None else
            "El diagnóstico detallado no está disponible para este resultado."
        )
        self.boton_ejecutar.configure(state="normal")
        self.boton_detener.configure(state="disabled")
        self._redibujar(forzar=True)

    def error(self) -> None:
        self._set_estado_chip("ERROR", "danger")
        self.cabecera_detalle.set("La ejecución terminó con un error; no se generó una evaluación final.")
        self.kpis["estado"].establecer("Error", "Consulta el mensaje mostrado", "danger")
        self.boton_ejecutar.configure(state="normal")
        self.boton_detener.configure(state="disabled")

    def marcar_cancelacion(self) -> None:
        self._set_estado_chip("CANCELANDO", "warning")
        self.cabecera_detalle.set("Cancelación solicitada; esperando el fin de la generación actual…")
        self.kpis["motivo"].establecer("Cancelando", "Se conserva el mejor resultado parcial", "warning")
        self.boton_detener.configure(state="disabled")

    def limpiar(self) -> None:
        self.registros.clear()
        self.resultado = None
        self._ultimo_redibujo = 0.0
        for tarjeta in self.kpis.values():
            tarjeta.limpiar()
        self._set_estado_chip("SIN EJECUTAR", "neutral")
        self.cabecera_detalle.set("Configura los parámetros y ejecuta el algoritmo.")
        self.origen_resultado.set("Resultado mostrado: —")
        self.progreso.configure(value=0)
        self.progreso_texto.set("Generación — / —")
        if hasattr(self, "detalle"):
            self.detalle.delete(*self.detalle.get_children())
            self.detalle.insert("", "end", values=("—", "Sin evaluación", "—", "—", "—"), tags=("cumplida",))
        if hasattr(self, "comparacion"):
            self.comparacion.delete(*self.comparacion.get_children())
            self.comparacion.insert(
                "", "end", values=("Sin resultados", "—", "—", "—", "Ejecuta el algoritmo"),
            )
        if hasattr(self, "resumen_texto"):
            self._escribir_resumen("Sin resultados. La comparación y las razones de factibilidad aparecerán al finalizar.")
        if hasattr(self, "diagnostico_texto"):
            self._escribir_diagnostico(
                "Sin resultados. Las asignaciones conflictivas y sus alternativas aparecerán al finalizar."
            )
        self._redibujar(forzar=True)

    def _aplicar_metricas(self, metricas: Mapping[str, tuple[str, str, str]]) -> None:
        for clave, valores in metricas.items():
            if clave in self.kpis:
                self.kpis[clave].establecer(*valores)

    def _actualizar_desglose(self, evaluacion: Evaluacion) -> None:
        self.detalle.delete(*self.detalle.get_children())
        for tipo, criterio, cantidad, peso, contribucion in filas_desglose(evaluacion):
            etiqueta = "cumplida"
            if cantidad and tipo == "Dura":
                etiqueta = "dura_activa"
            elif cantidad:
                etiqueta = "blanda_activa"
            self.detalle.insert(
                "", "end", values=(tipo, criterio, cantidad, peso, contribucion), tags=(etiqueta,),
            )

    def _actualizar_comparacion(self, resultado: Resultado) -> None:
        self.comparacion.delete(*self.comparacion.get_children())
        for fila in construir_comparacion(resultado):
            self.comparacion.insert("", "end", values=fila)

    def _escribir_resumen(self, contenido: str) -> None:
        self.resumen_texto.configure(state="normal")
        self.resumen_texto.delete("1.0", "end")
        self.resumen_texto.insert("1.0", contenido)
        self.resumen_texto.configure(state="disabled")

    def _escribir_diagnostico(self, contenido: str) -> None:
        self.diagnostico_texto.configure(state="normal")
        self.diagnostico_texto.delete("1.0", "end")
        self.diagnostico_texto.insert("1.0", contenido)
        self.diagnostico_texto.configure(state="disabled")

    def _set_estado_chip(self, texto: str, tono: str) -> None:
        estilos = {
            "neutral": (AZUL, "#eaf2f8"),
            "success": (EXITO, "#e8f5ee"),
            "danger": (PELIGRO, "#fdecea"),
            "warning": (ADVERTENCIA, "#fff4d6"),
        }
        color, fondo = estilos.get(tono, estilos["neutral"])
        self.estado_chip.configure(text=texto, fg=color, bg=fondo)

    def _redibujar(self, forzar: bool = False) -> None:
        if getattr(self, "eje", None) is None:
            return
        nota = dibujar_historial(self.eje, self.registros, self.vista_grafica.get())
        self.nota_grafica.set(nota)
        if forzar:
            self.canvas_grafica.draw_idle()

    def _exportar_grafica(self) -> None:
        if not self.registros:
            messagebox.showinfo("Sin historial", "Ejecuta el algoritmo antes de exportar una gráfica.", parent=self)
            return
        vista = self.vista_grafica.get()
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar gráfica evolutiva", defaultextension=".png",
            initialdir=self.carpeta_resultados, initialfile=f"evolucion_{vista}.png",
            filetypes=[("Imagen PNG", "*.png")],
        )
        if not ruta:
            return
        try:
            exportar_grafica_png(self.registros, vista, ruta)
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror("No se pudo exportar", str(exc), parent=self)
            return
        messagebox.showinfo("Gráfica exportada", f"Se guardó:\n{ruta}", parent=self)
