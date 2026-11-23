"""Laboratorio gráfico para experimentos reproducibles y comparativos."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from time import monotonic
from tkinter import filedialog, messagebox, ttk
from typing import Any, Mapping

from horarios_ga.estadisticas import (
    VISTAS_EXPERIMENTO, conclusiones_descriptivas, dibujar_resultados,
    resumir_ejecuciones,
)
from horarios_ga.experimentos import (
    ConfiguracionExperimento, ProgresoExperimento, ResultadoExperimento,
    estimar_experimento, ejecutar_experimento,
    exportar_experimento,
    generar_ablaciones, generar_variantes_un_parametro,
)
from horarios_ga.genetico import Configuracion

from .componentes import PanelDesplazable, SeccionPlegable
from .estilos import (
    ADVERTENCIA, AZUL, EXITO, FONDO, PANEL, PELIGRO, SECUNDARIO, TEXTO,
)


CAMPOS_GA = (
    ("poblacion", "Población", "40"),
    ("generaciones", "Generaciones", "40"),
    ("prob_cruza", "Prob. cruza", "0.85"),
    ("prob_mutacion", "Prob. mutación", "0.08"),
    ("elitismo", "Elitismo", "4"),
    ("torneo", "Torneo", "4"),
    ("semilla", "Semilla inicial", "42"),
    ("parada_sin_mejora", "Parada sin mejora", "0"),
    ("objetivo_penalizacion_blanda", "Objetivo blando", "0"),
    ("presupuesto_evaluaciones", "Máximo evaluaciones", "0"),
)


def _lista_numerica(texto: str, conversion: type) -> tuple[Any, ...]:
    try:
        return tuple(conversion(parte.strip()) for parte in texto.split(",") if parte.strip())
    except ValueError as exc:
        raise ValueError(f"Lista numérica no válida: {texto}") from exc


def configuracion_experimento_desde_valores(
    valores: Mapping[str, str],
    metodos: tuple[str, ...],
) -> ConfiguracionExperimento:
    """Convierte controles de texto en configuración validada y testeable."""
    base = Configuracion(
        poblacion=int(valores["poblacion"]), generaciones=int(valores["generaciones"]),
        prob_cruza=float(valores["prob_cruza"]), prob_mutacion=float(valores["prob_mutacion"]),
        elitismo=int(valores["elitismo"]), torneo=int(valores["torneo"]),
        semilla=int(valores["semilla"]),
        parada_sin_mejora=int(valores.get("parada_sin_mejora", "0")),
        objetivo_penalizacion_blanda=int(valores.get("objetivo_penalizacion_blanda", "0")),
        presupuesto_evaluaciones=int(valores.get("presupuesto_evaluaciones", "0")),
    )
    modo = valores.get("modo", "comparacion")
    variantes = ()
    if modo == "parametros":
        variantes = generar_variantes_un_parametro(
            base,
            poblaciones=_lista_numerica(valores.get("lista_poblaciones", ""), int),
            mutaciones=_lista_numerica(valores.get("lista_mutaciones", ""), float),
            cruzas=_lista_numerica(valores.get("lista_cruzas", ""), float),
            generaciones=_lista_numerica(valores.get("lista_generaciones", ""), int),
        )
    elif modo == "ablacion":
        variantes = generar_ablaciones(base)
    hibrido = replace(
        base, variante="hibrido", inicializacion_heuristica=True,
        busqueda_local=True, mutacion_adaptativa=True,
    )
    config = ConfiguracionExperimento(
        nombre=valores.get("nombre", "").strip(),
        descripcion=valores.get("descripcion", "").strip(),
        escenario=valores.get("escenario", "activo"),
        repeticiones=int(valores.get("repeticiones", "5")),
        metodos=metodos, genetico=base, hibrido=hibrido, semilla_inicial=base.semilla,
        modo=modo, variantes=variantes,
        repeticion_evolucion=int(valores.get("repeticion_evolucion", "1")),
    )
    config.validar()
    return config


class VistaExperimentacion(ttk.Frame):
    def __init__(
        self, padre: tk.Misc, base: Path,
        al_visualizar_evolucion: Any | None = None,
    ):
        super().__init__(padre, padding=8)
        self.base = Path(base)
        self.al_visualizar_evolucion = al_visualizar_evolucion
        self.raiz_experimentos = self.base / "experimentos"
        self.variables: dict[str, tk.StringVar] = {}
        self.metodos = {
            "genetico": tk.BooleanVar(value=True),
            "hibrido": tk.BooleanVar(value=True),
            "aleatorio": tk.BooleanVar(value=True),
            "constructivo": tk.BooleanVar(value=True),
        }
        self.escenario_activo_datos: dict[str, Any] | None = None
        self.escenario_activo_nombre = ""
        self.resultado: ResultadoExperimento | None = None
        self.carpeta_exportada: Path | None = None
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancelacion = threading.Event()
        self.hilo: threading.Thread | None = None
        self.inicio = 0.0
        self.vista_grafica = tk.StringVar(value="factibilidad")

        paneles = ttk.Panedwindow(self, orient="horizontal")
        paneles.pack(fill="both", expand=True)
        izquierda = ttk.Frame(paneles, style="Panel.TFrame", padding=10, width=338)
        derecha = ttk.Frame(paneles, style="Panel.TFrame", padding=(12, 10))
        paneles.add(izquierda, weight=0)
        paneles.add(derecha, weight=1)
        self._crear_configuracion(izquierda)
        self._crear_resultados(derecha)
        self.limpiar()

    @property
    def en_ejecucion(self) -> bool:
        return bool(self.hilo and self.hilo.is_alive())

    def solicitar_cancelacion(self) -> None:
        if self.en_ejecucion:
            self.cancelacion.set()

    def _variable(self, clave: str, valor: str) -> tk.StringVar:
        variable = tk.StringVar(value=valor)
        self.variables[clave] = variable
        return variable

    def _crear_configuracion(self, padre: tk.Misc) -> None:
        ttk.Label(padre, text="Laboratorio científico", style="PanelTitulo.TLabel").pack(anchor="w")
        ttk.Label(
            padre, text="Comparaciones reproducibles con presupuestos registrados",
            style="Ayuda.TLabel", wraplength=300,
        ).pack(anchor="w", pady=(1, 7))
        desplazable = PanelDesplazable(padre, ancho=310)
        desplazable.pack(fill="both", expand=True)

        general = SeccionPlegable(desplazable.interior, "Diseño experimental", True)
        general.pack(fill="x", pady=(0, 7))
        self._entrada(general.contenido, "nombre", "Nombre", "Comparación científica")
        self._entrada(general.contenido, "descripcion", "Descripción", "")
        self._combo(general.contenido, "modo", "Modo", ("comparacion", "parametros", "ablacion"), "comparacion")
        self._variable("escenario", "activo")
        self.etiqueta_escenario_activo = tk.StringVar(value="Configuración activa pendiente")
        ttk.Label(
            general.contenido, textvariable=self.etiqueta_escenario_activo,
            style="Ayuda.TLabel", wraplength=280,
        ).pack(fill="x", pady=(0, 5))
        self._combo(general.contenido, "repeticiones", "Repeticiones", ("5", "10", "20", "30"), "5", editable=True)
        self._entrada(general.contenido, "repeticion_evolucion", "Rep. evolución AG (0 desactiva)", "1", ancho=6)

        metodos = SeccionPlegable(desplazable.interior, "Métodos a comparar", True)
        metodos.pack(fill="x", pady=(0, 7))
        for clave, etiqueta in (
            ("genetico", "Algoritmo genético"),
            ("hibrido", "Algoritmo genético híbrido"),
            ("aleatorio", "Búsqueda aleatoria"),
            ("constructivo", "Heurística constructiva"),
        ):
            ttk.Checkbutton(metodos.contenido, text=etiqueta, variable=self.metodos[clave], command=self._actualizar_estimacion).pack(anchor="w", pady=2)

        genetica = SeccionPlegable(desplazable.interior, "Configuración genética", True)
        genetica.pack(fill="x", pady=(0, 7))
        for clave, etiqueta, valor in CAMPOS_GA:
            self._entrada(genetica.contenido, clave, etiqueta, valor, ancho=10)

        parametros = SeccionPlegable(desplazable.interior, "Análisis de parámetros", False)
        parametros.pack(fill="x", pady=(0, 7))
        self._entrada(parametros.contenido, "lista_poblaciones", "Poblaciones", "40, 80, 120")
        self._entrada(parametros.contenido, "lista_mutaciones", "Mutaciones", "0.03, 0.08, 0.15")
        self._entrada(parametros.contenido, "lista_cruzas", "Cruzas", "0.70, 0.85, 0.95")
        self._entrada(parametros.contenido, "lista_generaciones", "Generaciones", "40, 80, 120")
        ttk.Label(
            parametros.contenido,
            text="Se modifica un parámetro por vez respecto de la base.",
            style="Ayuda.TLabel", wraplength=280,
        ).pack(fill="x")

        self.estimacion = tk.StringVar(value="—")
        ttk.Label(
            desplazable.interior, textvariable=self.estimacion, style="Ayuda.TLabel",
            wraplength=285, justify="left",
        ).pack(fill="x", padx=4, pady=(2, 7))
        for variable in self.variables.values():
            variable.trace_add("write", lambda *_: self._actualizar_estimacion())

        acciones = ttk.Frame(padre, style="Panel.TFrame")
        acciones.pack(fill="x", pady=(8, 0))
        self.boton_ejecutar = ttk.Button(
            acciones, text="Ejecutar experimento", style="Primary.TButton", command=self.ejecutar,
        )
        self.boton_ejecutar.pack(fill="x", pady=(0, 5))
        fila = ttk.Frame(acciones, style="Panel.TFrame")
        fila.pack(fill="x")
        self.boton_cancelar = ttk.Button(
            fila, text="Cancelar", style="Danger.TButton", command=self.cancelar, state="disabled",
        )
        self.boton_cancelar.pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(fila, text="Limpiar", command=self.limpiar).pack(side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(acciones, text="Exportar resultados", command=self.exportar).pack(fill="x", pady=(5, 0))
        ttk.Button(acciones, text="Abrir carpeta de experimentos", command=self.abrir_carpeta).pack(fill="x", pady=(5, 0))

    def _entrada(self, padre: tk.Misc, clave: str, etiqueta: str, valor: str, ancho: int = 18) -> None:
        fila = ttk.Frame(padre, style="Panel.TFrame")
        fila.pack(fill="x", pady=3)
        ttk.Label(fila, text=etiqueta, style="Campo.TLabel").pack(side="left")
        ttk.Entry(fila, textvariable=self._variable(clave, valor), width=ancho, justify="right").pack(side="right")

    def _combo(
        self, padre: tk.Misc, clave: str, etiqueta: str, opciones: tuple[str, ...],
        valor: str, editable: bool = False,
    ) -> None:
        fila = ttk.Frame(padre, style="Panel.TFrame")
        fila.pack(fill="x", pady=3)
        ttk.Label(fila, text=etiqueta, style="Campo.TLabel").pack(side="left")
        ttk.Combobox(
            fila, textvariable=self._variable(clave, valor), values=opciones,
            state="normal" if editable else "readonly", width=16, justify="right",
        ).pack(side="right")

    def _crear_resultados(self, padre: tk.Misc) -> None:
        self._crear_progreso(padre)
        vistas = ttk.Notebook(padre)
        vistas.pack(fill="both", expand=True, pady=(8, 0))
        pagina_ejecuciones = ttk.Frame(vistas, style="Panel.TFrame", padding=6)
        pagina_resumen = ttk.Frame(vistas, style="Panel.TFrame", padding=6)
        pagina_graficas = ttk.Frame(vistas, style="Panel.TFrame", padding=6)
        pagina_conclusiones = ttk.Frame(vistas, style="Panel.TFrame", padding=8)
        vistas.add(pagina_ejecuciones, text="Ejecuciones")
        vistas.add(pagina_resumen, text="Resumen estadístico")
        vistas.add(pagina_graficas, text="Gráficas comparativas")
        vistas.add(pagina_conclusiones, text="Conclusiones")
        self._crear_tabla_ejecuciones(pagina_ejecuciones)
        self._crear_tabla_resumen(pagina_resumen)
        self._crear_graficas(pagina_graficas)
        self.conclusiones = tk.Text(
            pagina_conclusiones, wrap="word", relief="flat", bg=PANEL, fg=TEXTO,
            font=("Segoe UI", 10), padx=12, pady=10,
        )
        self.conclusiones.pack(fill="both", expand=True)
        self.conclusiones.configure(state="disabled")

    def _crear_progreso(self, padre: tk.Misc) -> None:
        marco = tk.Frame(padre, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1, padx=12, pady=9)
        marco.pack(fill="x")
        superior = tk.Frame(marco, bg=PANEL)
        superior.pack(fill="x")
        tk.Label(superior, text="Progreso experimental", bg=PANEL, fg=AZUL, font=("Segoe UI Semibold", 12)).pack(side="left")
        self.chip = tk.Label(superior, text="PENDIENTE", bg="#eaf2f8", fg=AZUL, font=("Segoe UI Semibold", 8), padx=9, pady=3)
        self.chip.pack(side="right")
        self.progreso_detalle = tk.StringVar(value="Configura el estudio y ejecuta el laboratorio.")
        tk.Label(marco, textvariable=self.progreso_detalle, bg=PANEL, fg=SECUNDARIO, anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(4, 6))
        fila = tk.Frame(marco, bg=PANEL)
        fila.pack(fill="x")
        self.barra = ttk.Progressbar(fila, maximum=100)
        self.barra.pack(side="left", fill="x", expand=True)
        self.progreso_texto = tk.StringVar(value="0 / 0 ejecuciones")
        tk.Label(fila, textvariable=self.progreso_texto, bg=PANEL, fg=TEXTO, font=("Segoe UI Semibold", 8), padx=8).pack(side="right")
        self.ultimo_resultado = tk.StringVar(value="Último resultado: —")
        tk.Label(marco, textvariable=self.ultimo_resultado, bg=PANEL, fg=SECUNDARIO, anchor="w", font=("Segoe UI", 8)).pack(fill="x", pady=(5, 0))

    def _crear_tabla_ejecuciones(self, padre: tk.Misc) -> None:
        acciones = ttk.Frame(padre, style="Panel.TFrame")
        acciones.pack(fill="x", pady=(0, 5))
        ttk.Label(
            acciones, text="Selecciona una ejecución genética con evolución capturada.",
            style="Ayuda.TLabel",
        ).pack(side="left")
        ttk.Button(
            acciones, text="Visualizar evolución seleccionada",
            command=self._visualizar_evolucion_seleccionada,
        ).pack(side="right")
        columnas = ("metodo", "rep", "semilla", "estado", "duras", "blanda", "fitness", "evals", "tiempo")
        self.tabla = ttk.Treeview(padre, columns=columnas, show="headings")
        for clave, titulo, ancho in (
            ("metodo", "Método/configuración", 190), ("rep", "Rep.", 45),
            ("semilla", "Semilla", 65), ("estado", "Factible", 65),
            ("duras", "Duras", 55), ("blanda", "Blanda", 65),
            ("fitness", "Fitness", 65), ("evals", "Evaluaciones", 85),
            ("tiempo", "Tiempo (s)", 75),
        ):
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=ancho, anchor="w" if clave == "metodo" else "center")
        barra = ttk.Scrollbar(padre, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

    def _crear_tabla_resumen(self, padre: tk.Misc) -> None:
        columnas = ("metodo", "n", "factibles", "tasa", "duras", "blanda", "tiempo", "evals")
        self.resumen = ttk.Treeview(padre, columns=columnas, show="headings")
        for clave, titulo, ancho in (
            ("metodo", "Método/configuración", 190), ("n", "n", 45),
            ("factibles", "Factibles", 65), ("tasa", "Tasa", 65),
            ("duras", "Mediana duras", 95), ("blanda", "Mediana blanda*", 105),
            ("tiempo", "Mediana s", 80), ("evals", "Mediana eval.", 95),
        ):
            self.resumen.heading(clave, text=titulo)
            self.resumen.column(clave, width=ancho, anchor="w" if clave == "metodo" else "center")
        self.resumen.pack(fill="both", expand=True)
        ttk.Label(padre, text="* Calidad blanda calculada sólo entre soluciones factibles.", style="Ayuda.TLabel").pack(anchor="w", pady=(5, 0))

    def _crear_graficas(self, padre: tk.Misc) -> None:
        controles = ttk.Frame(padre, style="Panel.TFrame")
        controles.pack(fill="x")
        for clave, etiqueta in VISTAS_EXPERIMENTO:
            ttk.Radiobutton(
                controles, text=etiqueta, value=clave, variable=self.vista_grafica,
                command=self._redibujar,
            ).pack(side="left", padx=3)
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            self.figura = self.canvas = None
            ttk.Label(padre, text="Matplotlib no está disponible.", style="Ayuda.TLabel").pack(expand=True)
            return
        self.figura = Figure(figsize=(8, 4.3), dpi=100, facecolor=PANEL)
        self.canvas = FigureCanvasTkAgg(self.figura, master=padre)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(4, 0))
        self.nota_grafica = tk.StringVar()
        ttk.Label(padre, textvariable=self.nota_grafica, style="Ayuda.TLabel", anchor="center").pack(fill="x")

    def obtener_configuracion(self) -> ConfiguracionExperimento:
        valores = {clave: variable.get() for clave, variable in self.variables.items()}
        valores["escenario"] = "activo"
        seleccionados = tuple(clave for clave, variable in self.metodos.items() if variable.get())
        return configuracion_experimento_desde_valores(valores, seleccionados)

    def _actualizar_estimacion(self) -> None:
        if not hasattr(self, "estimacion"):
            return
        try:
            estimacion = estimar_experimento(self.obtener_configuracion())
            self.estimacion.set(
                f"Estimación previa: {estimacion['configuraciones']} configuraciones · "
                f"{estimacion['ejecuciones']} ejecuciones sobre la configuración activa · "
                f"{estimacion['evaluaciones_nominales']:,} evaluaciones nominales."
            )
        except (ValueError, KeyError):
            self.estimacion.set("Completa valores válidos para calcular el costo estimado.")

    def establecer_escenario_activo(self, datos: dict[str, Any], nombre: str) -> None:
        """Recibe una copia del mismo escenario validado que usa Optimización."""
        self.escenario_activo_datos = deepcopy(datos)
        self.escenario_activo_nombre = nombre
        if hasattr(self, "etiqueta_escenario_activo"):
            self.etiqueta_escenario_activo.set(f"Configuración activa: {nombre}")
        if hasattr(self, "variables") and "escenario" in self.variables:
            self.variables["escenario"].set("activo")
        self._actualizar_estimacion()

    def ejecutar(self) -> None:
        if self.en_ejecucion:
            return
        try:
            configuracion = self.obtener_configuracion()
            estimacion = estimar_experimento(configuracion)
            if self.escenario_activo_datos is None:
                raise ValueError("No hay una configuración académica activa compartida")
            datos = deepcopy(self.escenario_activo_datos)
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showerror("Experimento no válido", str(exc), parent=self)
            return
        total_ejecuciones = estimacion["ejecuciones"]
        total_evaluaciones = estimacion["evaluaciones_nominales"]
        if (total_ejecuciones > 60 or total_evaluaciones > 5_000_000) and not messagebox.askyesno(
            "Experimento grande",
            f"Se ejecutarán {total_ejecuciones} corridas y aproximadamente "
            f"{total_evaluaciones:,} evaluaciones nominales. ¿Continuar?",
            parent=self,
        ):
            return
        self.cancelacion.clear()
        self.resultado = None
        self.carpeta_exportada = None
        self.inicio = monotonic()
        self._set_estado("EJECUTANDO", "warning")
        self.boton_ejecutar.configure(state="disabled")
        self.boton_cancelar.configure(state="normal")
        self.progreso_detalle.set(f"{configuracion.nombre} · preparando escenario {configuracion.escenario}")
        self.barra.configure(value=0)
        self.progreso_texto.set(f"0 / {total_ejecuciones} ejecuciones")

        def trabajador() -> None:
            try:
                resultado = ejecutar_experimento(
                    configuracion, datos,
                    al_progresar=lambda progreso: self.cola.put(("progreso", progreso)),
                    debe_cancelar=self.cancelacion.is_set,
                )
                carpeta = exportar_experimento(resultado, self.raiz_experimentos)
            except Exception as exc:
                self.cola.put(("error", exc))
            else:
                self.cola.put(("final", (resultado, carpeta)))

        self.hilo = threading.Thread(target=trabajador, name="laboratorio-experimental", daemon=True)
        self.hilo.start()
        self.after(50, self._procesar_cola)

    def cancelar(self) -> None:
        if self.en_ejecucion:
            self.cancelacion.set()
            self._set_estado("CANCELANDO", "warning")
            self.progreso_detalle.set("Cancelación solicitada; se conservarán las ejecuciones terminadas.")
            self.boton_cancelar.configure(state="disabled")

    def _procesar_cola(self) -> None:
        termino = False
        while True:
            try:
                tipo, contenido = self.cola.get_nowait()
            except queue.Empty:
                break
            if tipo == "progreso":
                self._aplicar_progreso(contenido)
            elif tipo == "final":
                termino = True
                self.resultado, self.carpeta_exportada = contenido
                self._mostrar_resultado()
            elif tipo == "error":
                termino = True
                self._set_estado("ERROR", "danger")
                self.progreso_detalle.set("El laboratorio terminó con un error no recuperable.")
                messagebox.showerror("Error experimental", str(contenido), parent=self)
        if termino:
            self.hilo = None
            self.boton_ejecutar.configure(state="normal")
            self.boton_cancelar.configure(state="disabled")
        elif self.en_ejecucion:
            self.after(70, self._procesar_cola)
        else:
            self.after(30, self._procesar_cola)

    def _aplicar_progreso(self, progreso: ProgresoExperimento) -> None:
        porcentaje = progreso.completadas / progreso.total * 100 if progreso.total else 0
        self.barra.configure(value=porcentaje)
        self.progreso_texto.set(f"{progreso.completadas} / {progreso.total} ejecuciones")
        transcurrido = monotonic() - self.inicio
        self.progreso_detalle.set(
            f"{progreso.experimento} · {progreso.metodo} · repetición "
            f"{progreso.repeticion or '—'} / {progreso.repeticiones} · {transcurrido:.1f} s"
        )
        if progreso.ultimo_resultado:
            self.ultimo_resultado.set(f"Último resultado: {progreso.ultimo_resultado}")

    def _mostrar_resultado(self) -> None:
        assert self.resultado is not None
        estado = self.resultado.estado
        tono = "success" if estado == "completado" else ("warning" if estado == "cancelado" else "danger")
        self._set_estado(estado.upper().replace("_", " "), tono)
        total = len(self.resultado.ejecuciones)
        estimado = estimar_experimento(self.resultado.configuracion)["ejecuciones"]
        self.barra.configure(value=total / estimado * 100 if estimado else 0)
        self.progreso_texto.set(f"{total} / {estimado} ejecuciones")
        self.progreso_detalle.set(
            f"{self.resultado.configuracion.nombre} · {estado} · "
            f"{self.resultado.duracion:.2f} s · SHA-256 {self.resultado.huella_escenario[:12]}…"
        )
        self._llenar_tablas()
        self._escribir_conclusiones(conclusiones_descriptivas(self.resultado.ejecuciones))
        self._redibujar()

    def _llenar_tablas(self) -> None:
        assert self.resultado is not None
        self.tabla.delete(*self.tabla.get_children())
        for ejecucion in self.resultado.ejecuciones:
            self.tabla.insert("", "end", iid=ejecucion.id, values=(
                ejecucion.etiqueta_metodo, ejecucion.repeticion, ejecucion.semilla,
                "Error" if ejecucion.error else ("Sí" if ejecucion.factible else "No"),
                ejecucion.duras if not ejecucion.error else "—",
                ejecucion.penalizacion_blanda if not ejecucion.error else "—",
                ejecucion.fitness if not ejecucion.error else "—", ejecucion.evaluaciones,
                f"{ejecucion.duracion:.4f}",
            ))
        self.resumen.delete(*self.resumen.get_children())
        for fila in resumir_ejecuciones(self.resultado.ejecuciones):
            self.resumen.insert("", "end", values=(
                fila["metodo"], fila["muestras_validas"], fila["factibles"],
                f"{fila['tasa_factibilidad']:.1f}%" if fila["tasa_factibilidad"] is not None else "—",
                _formatear(fila["violaciones_duras"]["mediana"]),
                _formatear(fila["penalizacion_blanda_factible"]["mediana"], "Sin factibles"),
                _formatear(fila["tiempo"]["mediana"]),
                _formatear(fila["evaluaciones"]["mediana"]),
            ))

    def _redibujar(self) -> None:
        if self.figura is None:
            return
        ejecuciones = self.resultado.ejecuciones if self.resultado else ()
        nota = dibujar_resultados(self.figura, ejecuciones, self.vista_grafica.get())
        self.nota_grafica.set(nota)
        self.canvas.draw_idle()

    def _visualizar_evolucion_seleccionada(self) -> None:
        if self.resultado is None or self.al_visualizar_evolucion is None:
            messagebox.showinfo("Sin evolución", "No hay una evolución experimental disponible.", parent=self)
            return
        seleccion = self.tabla.selection()
        candidatos = [
            e for e in self.resultado.ejecuciones
            if e.evolucion is not None and (not seleccion or e.id in seleccion)
        ]
        if not candidatos:
            messagebox.showinfo(
                "Sin captura detallada",
                "Selecciona la repetición genética configurada para captura evolutiva.",
                parent=self,
            )
            return
        self.al_visualizar_evolucion(candidatos[0].evolucion)

    def _escribir_conclusiones(self, texto: str) -> None:
        self.conclusiones.configure(state="normal")
        self.conclusiones.delete("1.0", "end")
        self.conclusiones.insert("1.0", texto)
        self.conclusiones.configure(state="disabled")

    def exportar(self) -> None:
        if self.resultado is None:
            messagebox.showinfo("Sin resultados", "Ejecuta un experimento antes de exportar.", parent=self)
            return
        raiz = filedialog.askdirectory(parent=self, title="Carpeta para guardar el experimento", initialdir=self.raiz_experimentos)
        if not raiz:
            return
        try:
            self.carpeta_exportada = exportar_experimento(self.resultado, raiz)
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror("No se pudo exportar", str(exc), parent=self)
            return
        messagebox.showinfo("Experimento exportado", f"Archivos guardados en:\n{self.carpeta_exportada}", parent=self)

    def abrir_carpeta(self) -> None:
        carpeta = self.carpeta_exportada or self.raiz_experimentos
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(carpeta)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("No se pudo abrir la carpeta", str(exc), parent=self)

    def limpiar(self) -> None:
        if self.en_ejecucion:
            messagebox.showinfo("Experimento en curso", "Cancela el experimento antes de limpiar.", parent=self)
            return
        self.resultado = None
        self.tabla.delete(*self.tabla.get_children()) if hasattr(self, "tabla") else None
        self.resumen.delete(*self.resumen.get_children()) if hasattr(self, "resumen") else None
        if hasattr(self, "barra"):
            self.barra.configure(value=0)
            self.progreso_texto.set("0 / 0 ejecuciones")
            self.progreso_detalle.set("Configura el estudio y ejecuta el laboratorio.")
            self.ultimo_resultado.set("Último resultado: —")
            self._set_estado("PENDIENTE", "neutral")
        if hasattr(self, "conclusiones"):
            self._escribir_conclusiones("Sin resultados. Las conclusiones se generan únicamente a partir de ejecuciones reales.")
        if hasattr(self, "figura"):
            self._redibujar()
        self._actualizar_estimacion()

    def _set_estado(self, texto: str, tono: str) -> None:
        estilos = {
            "neutral": (AZUL, "#eaf2f8"), "success": (EXITO, "#e8f5ee"),
            "warning": (ADVERTENCIA, "#fff4d6"), "danger": (PELIGRO, "#fdecea"),
        }
        color, fondo = estilos[tono]
        self.chip.configure(text=texto, fg=color, bg=fondo)


def _formatear(valor: float | int | None, vacio: str = "—") -> str:
    if valor is None:
        return vacio
    return f"{valor:.2f}"

