"""Séptima pestaña: calendario interactivo y reproducción de la evolución real."""
from __future__ import annotations

import hashlib
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from time import monotonic
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from horarios_ga.datos import problema_desde_datos
from horarios_ga.evolucion import (
    ControlDidactico, InstantaneaEvolutiva, RegistroEvolucion, VERSION_EVOLUCION,
    cargar_evolucion, comparar_instantaneas, describir_diferencia, guardar_evolucion,
    resultado_desde_instantanea,
)
from horarios_ga.exportaciones_evolucion import (
    exportar_comparacion_png, exportar_gif, exportar_instantanea_png,
    exportar_secuencia_png,
)
from horarios_ga.genetico import Configuracion, Resultado
from horarios_ga.modelo import Problema

from .estilos import ADVERTENCIA, AZUL, EXITO, FONDO, PANEL, PELIGRO, SECUNDARIO, TEXTO
from .horarios import construir_matriz


PALETA_MATERIAS = ("#dbeafe", "#e0f2fe", "#dcfce7", "#fef3c7", "#ede9fe", "#fce7f3", "#ecfccb")
VELOCIDADES = ("0.25", "0.5", "1", "2", "5")


class MiniKPI(tk.Frame):
    def __init__(self, padre: tk.Misc, titulo: str):
        super().__init__(padre, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1, padx=8, pady=5)
        tk.Label(self, text=titulo, bg=PANEL, fg=SECUNDARIO, font=("Segoe UI", 8), anchor="w").pack(fill="x")
        self.valor = tk.Label(self, text="—", bg=PANEL, fg=AZUL, font=("Segoe UI Semibold", 11), anchor="w")
        self.valor.pack(fill="x")

    def establecer(self, texto: str, tono: str = "neutral") -> None:
        colores = {"neutral": AZUL, "success": EXITO, "danger": PELIGRO, "warning": ADVERTENCIA}
        self.valor.configure(text=texto, fg=colores.get(tono, AZUL))


class CalendarioEvolutivo(ttk.Frame):
    """Calendario desplazable basado en la misma matriz que Horarios generados."""

    def __init__(self, padre: tk.Misc):
        super().__init__(padre, style="Panel.TFrame")
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0)
        sx = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        sy = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tabla = tk.Frame(self.canvas, bg=PANEL)
        self.ventana = self.canvas.create_window((0, 0), window=self.tabla, anchor="nw")
        self.tabla.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._ancho)

    def _ancho(self, evento) -> None:
        self.canvas.itemconfigure(self.ventana, width=max(evento.width, self.tabla.winfo_reqwidth()))

    def limpiar(self, texto: str = "Sin instantáneas evolutivas") -> None:
        for hijo in self.tabla.winfo_children():
            hijo.destroy()
        tk.Label(self.tabla, text=texto, bg=PANEL, fg=SECUNDARIO, padx=20, pady=30).pack()

    def mostrar(
        self, problema: Problema, instantanea: InstantaneaEvolutiva,
        modo: str, identificador: str, cambiados: set[int] | None = None,
    ) -> None:
        for hijo in self.tabla.winfo_children():
            hijo.destroy()
        resultado = resultado_desde_instantanea(instantanea, Configuracion())
        matriz = construir_matriz(problema, resultado, modo, identificador)
        indice_por_id = {sesion.id: i for i, sesion in enumerate(problema.sesiones)}
        cambiados = cambiados or set()
        encabezados = ("Hora",) + problema.dias
        for columna, texto in enumerate(encabezados):
            tk.Label(
                self.tabla, text=texto, bg=AZUL, fg="white", font=("Segoe UI Semibold", 8),
                padx=6, pady=5, relief="solid", borderwidth=1,
            ).grid(row=0, column=columna, sticky="nsew")
            self.tabla.columnconfigure(columna, minsize=86 if columna else 72, weight=1)
        for bloque, hora in enumerate(problema.horas):
            tk.Label(
                self.tabla, text=hora, bg=FONDO, fg=AZUL, font=("Segoe UI Semibold", 8),
                padx=4, pady=5, relief="solid", borderwidth=1,
            ).grid(row=bloque + 1, column=0, sticky="nsew")
            for dia in range(len(problema.dias)):
                entradas = matriz.get((bloque, dia), ())
                textos, indices = [], []
                for entrada in entradas:
                    indice = indice_por_id[entrada.sesion.id]
                    indices.append(indice)
                    marcas = []
                    if indice in cambiados:
                        marcas.append("CAMBIO")
                    if entrada.conflicto:
                        marcas.append("⚠ CONFLICTO")
                    prefijo = (" · ".join(marcas) + "\n") if marcas else ""
                    continuidad = " (continuación)" if entrada.continuacion else ""
                    textos.append(
                        f"{prefijo}{entrada.sesion.materia}{continuidad}\n"
                        f"{entrada.sesion.grupo} · {problema.docentes[entrada.sesion.docente].nombre}\n"
                        f"{entrada.salon}"
                    )
                conflicto = any(e.conflicto for e in entradas)
                cambio = any(i in cambiados for i in indices)
                if conflicto:
                    fondo, frente = "#fee4e2", PELIGRO
                elif cambio:
                    fondo, frente = "#fff4d6", "#7a4b00"
                elif entradas:
                    materia = entradas[0].sesion.materia
                    color = int(hashlib.sha1(materia.encode("utf-8")).hexdigest()[:8], 16) % len(PALETA_MATERIAS)
                    fondo, frente = PALETA_MATERIAS[color], TEXTO
                else:
                    fondo, frente = PANEL, TEXTO
                tk.Label(
                    self.tabla, text="\n——\n".join(textos), bg=fondo, fg=frente,
                    justify="left", anchor="nw", padx=5, pady=4, wraplength=135,
                    relief="solid", borderwidth=1, font=("Segoe UI", 7),
                ).grid(row=bloque + 1, column=dia + 1, sticky="nsew")
            self.tabla.rowconfigure(bloque + 1, minsize=52, weight=1)


class VistaEvolucion(ttk.Frame):
    def __init__(
        self, padre: tk.Misc, base: Path,
        al_iniciar: Callable[[], None], al_detener: Callable[[], None],
        al_pausar: Callable[[], None], al_continuar: Callable[[], None],
        al_paso: Callable[[], None],
    ):
        super().__init__(padre, padding=8)
        self.base = Path(base)
        self.al_iniciar, self.al_detener = al_iniciar, al_detener
        self.al_pausar, self.al_continuar, self.al_paso = al_pausar, al_continuar, al_paso
        self.problema: Problema | None = None
        self.configuracion: Configuracion | None = None
        self.escenario_datos: dict | None = None
        self.instantaneas: list[InstantaneaEvolutiva] = []
        self.registro: RegistroEvolucion | None = None
        self.indice_actual = 0
        self.reproduciendo = False
        self.seguir_ultima = True
        self._ultima_grafica = 0.0
        self._ultima_vista = 0.0
        self._ajustando_escala = False
        self._marcadores = []
        self.modo = tk.StringVar(value="grupo")
        self.identificador = tk.StringVar()
        self.generacion = tk.StringVar(value="0")
        self.velocidad = tk.StringVar(value="0.5")
        self.didactico = tk.BooleanVar(value=False)
        self.retardo = tk.StringVar(value="0.5")
        self.frecuencia_captura = tk.StringVar(value="1")
        self.estado_calculo = tk.StringVar(value="Sin ejecución")

        self._crear_barra_calculo()
        self._crear_metricas()
        self._crear_reproduccion()
        self._crear_contenido()
        self.limpiar()

    def _crear_barra_calculo(self) -> None:
        marco = tk.Frame(self, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1, padx=9, pady=6)
        marco.pack(fill="x")
        tk.Label(marco, text="Evolución en vivo", bg=PANEL, fg=AZUL, font=("Segoe UI Semibold", 11)).pack(side="left")
        ttk.Button(marco, text="Iniciar", style="Accent.TButton", command=self.al_iniciar).pack(side="left", padx=(14, 3))
        ttk.Button(marco, text="Pausar cálculo", command=self.al_pausar).pack(side="left", padx=3)
        ttk.Button(marco, text="Continuar", command=self.al_continuar).pack(side="left", padx=3)
        ttk.Button(marco, text="Paso", command=self.al_paso).pack(side="left", padx=3)
        ttk.Button(marco, text="Detener", style="Danger.TButton", command=self.al_detener).pack(side="left", padx=3)
        ttk.Checkbutton(marco, text="Ejecución didáctica", variable=self.didactico).pack(side="left", padx=(12, 3))
        ttk.Label(marco, text="Retardo:", style="Campo.TLabel").pack(side="left")
        ttk.Combobox(marco, textvariable=self.retardo, values=VELOCIDADES, state="readonly", width=5).pack(side="left", padx=3)
        ttk.Label(marco, text="Capturar cada:", style="Campo.TLabel").pack(side="left", padx=(8, 0))
        ttk.Spinbox(marco, textvariable=self.frecuencia_captura, from_=1, to=100, width=4).pack(side="left", padx=3)
        tk.Label(marco, textvariable=self.estado_calculo, bg=PANEL, fg=SECUNDARIO, font=("Segoe UI", 8)).pack(side="right")

    def _crear_metricas(self) -> None:
        marco = ttk.Frame(self, style="Panel.TFrame")
        marco.pack(fill="x", pady=(6, 0))
        definiciones = (
            ("generacion", "Generación"), ("estado", "Factibilidad"),
            ("fitness", "Mejor fitness"), ("duras", "Violaciones duras"),
            ("blandas", "Penalización blanda"), ("diversidad", "Diversidad"),
            ("primera", "Primera factible"), ("cambios", "Asignaciones cambiadas"),
            ("tiempo", "Tiempo de cálculo"), ("capturas", "Instantáneas"),
        )
        self.kpis: dict[str, MiniKPI] = {}
        for indice, (clave, titulo) in enumerate(definiciones):
            tarjeta = MiniKPI(marco, titulo)
            tarjeta.grid(row=indice // 5, column=indice % 5, sticky="nsew", padx=2, pady=2)
            marco.columnconfigure(indice % 5, weight=1, uniform="live")
            self.kpis[clave] = tarjeta

    def _crear_reproduccion(self) -> None:
        barra = ttk.Frame(self, style="Panel.TFrame", padding=(4, 4))
        barra.pack(fill="x", pady=(4, 0))
        ttk.Label(barra, text="REPRODUCCIÓN VISUAL", style="Campo.TLabel").pack(side="left", padx=(0, 7))
        ttk.Button(barra, text="|◀", width=4, command=lambda: self._mostrar_indice(0)).pack(side="left", padx=2)
        ttk.Button(barra, text="◀", width=4, command=lambda: self._mostrar_indice(self.indice_actual - 1)).pack(side="left", padx=2)
        self.boton_play = ttk.Button(barra, text="Reproducir", command=self.reproducir)
        self.boton_play.pack(side="left", padx=2)
        ttk.Button(barra, text="Pausar animación", command=self.pausar_reproduccion).pack(side="left", padx=2)
        ttk.Button(barra, text="▶", width=4, command=lambda: self._mostrar_indice(self.indice_actual + 1)).pack(side="left", padx=2)
        ttk.Button(barra, text="▶|", width=4, command=self._ir_ultima).pack(side="left", padx=2)
        self.escala = ttk.Scale(barra, from_=0, to=0, command=self._mover_escala)
        self.escala.pack(side="left", fill="x", expand=True, padx=8)
        self.selector_generacion = ttk.Combobox(barra, textvariable=self.generacion, state="readonly", width=6)
        self.selector_generacion.pack(side="left", padx=3)
        self.selector_generacion.bind("<<ComboboxSelected>>", self._seleccionar_generacion)
        ttk.Label(barra, text="Velocidad:").pack(side="left", padx=(7, 2))
        ttk.Combobox(barra, textvariable=self.velocidad, values=VELOCIDADES, state="readonly", width=5).pack(side="left")

    def _crear_contenido(self) -> None:
        panel = ttk.Panedwindow(self, orient="vertical")
        panel.pack(fill="both", expand=True, pady=(4, 0))
        superior = ttk.Frame(panel, style="Panel.TFrame")
        inferior = ttk.Frame(panel, style="Panel.TFrame")
        panel.add(superior, weight=3)
        panel.add(inferior, weight=2)

        self.vistas = ttk.Notebook(superior)
        self.vistas.pack(fill="both", expand=True)
        reproduccion = ttk.Frame(self.vistas, style="Panel.TFrame", padding=4)
        comparacion = ttk.Frame(self.vistas, style="Panel.TFrame", padding=4)
        self.vistas.add(reproduccion, text="Horario reproducido")
        self.vistas.add(comparacion, text="Comparación de generaciones")
        self._crear_vista_reproduccion(reproduccion)
        self._crear_comparacion(comparacion)
        self._crear_grafica(inferior)

    def _crear_vista_reproduccion(self, padre: tk.Misc) -> None:
        filtros = ttk.Frame(padre, style="Panel.TFrame")
        filtros.pack(fill="x", pady=(0, 4))
        ttk.Label(filtros, text="Horario de:").pack(side="left")
        combo_modo = ttk.Combobox(filtros, textvariable=self.modo, values=("grupo", "docente", "salon"), state="readonly", width=10)
        combo_modo.pack(side="left", padx=5)
        combo_modo.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_opciones())
        self.selector_entidad = ttk.Combobox(filtros, textvariable=self.identificador, state="readonly", width=20)
        self.selector_entidad.pack(side="left")
        self.selector_entidad.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_vista())
        for texto, comando in (
            ("Guardar evolución", self.guardar), ("Abrir evolución", self.abrir),
            ("PNG mostrado", self.exportar_png), ("Secuencia PNG", self.exportar_secuencia),
            ("GIF", self.exportar_animacion),
        ):
            ttk.Button(filtros, text=texto, command=comando).pack(side="right", padx=2)
        cuerpo = ttk.Panedwindow(padre, orient="horizontal")
        cuerpo.pack(fill="both", expand=True)
        calendario = ttk.Frame(cuerpo, style="Panel.TFrame")
        cambios = ttk.Frame(cuerpo, style="Panel.TFrame", padding=6, width=310)
        cuerpo.add(calendario, weight=3)
        cuerpo.add(cambios, weight=1)
        self.calendario = CalendarioEvolutivo(calendario)
        self.calendario.pack(fill="both", expand=True)
        ttk.Label(cambios, text="Cambios reales", style="PanelTitulo.TLabel").pack(anchor="w")
        self.texto_cambios = tk.Text(
            cambios, wrap="word", bg=PANEL, fg=TEXTO, relief="flat",
            font=("Segoe UI", 8), padx=5, pady=5, width=34,
        )
        self.texto_cambios.pack(fill="both", expand=True)
        self.texto_cambios.configure(state="disabled")

    def _crear_comparacion(self, padre: tk.Misc) -> None:
        barra = ttk.Frame(padre, style="Panel.TFrame")
        barra.pack(fill="x", pady=(0, 4))
        ttk.Label(barra, text="Generación izquierda:").pack(side="left")
        self.gen_izquierda = tk.StringVar(value="0")
        self.combo_izquierda = ttk.Combobox(barra, textvariable=self.gen_izquierda, state="readonly", width=6)
        self.combo_izquierda.pack(side="left", padx=4)
        ttk.Label(barra, text="Generación derecha:").pack(side="left", padx=(10, 0))
        self.gen_derecha = tk.StringVar(value="0")
        self.combo_derecha = ttk.Combobox(barra, textvariable=self.gen_derecha, state="readonly", width=6)
        self.combo_derecha.pack(side="left", padx=4)
        self.combo_izquierda.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_comparacion())
        self.combo_derecha.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_comparacion())
        ttk.Button(barra, text="Inicial vs. final", command=self._comparar_extremos).pack(side="left", padx=8)
        ttk.Button(barra, text="Exportar comparación", command=self.exportar_comparacion).pack(side="right")
        self.resumen_comparacion = tk.StringVar(value="Sin datos")
        ttk.Label(barra, textvariable=self.resumen_comparacion, style="Ayuda.TLabel").pack(side="right", padx=10)
        paneles = ttk.Panedwindow(padre, orient="horizontal")
        paneles.pack(fill="both", expand=True)
        self.calendario_izquierdo = CalendarioEvolutivo(paneles)
        self.calendario_derecho = CalendarioEvolutivo(paneles)
        paneles.add(self.calendario_izquierdo, weight=1)
        paneles.add(self.calendario_derecho, weight=1)

    def _crear_grafica(self, padre: tk.Misc) -> None:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            self.figura = self.canvas_grafica = None
            return
        self.figura = Figure(figsize=(9, 2.0), dpi=100, facecolor=PANEL)
        self.ejes = [self.figura.add_subplot(2, 2, i) for i in range(1, 5)]
        self.figura.subplots_adjust(left=.06, right=.98, bottom=.22, top=.88, hspace=.75, wspace=.25)
        self.canvas_grafica = FigureCanvasTkAgg(self.figura, master=padre)
        self.canvas_grafica.get_tk_widget().pack(fill="both", expand=True)
        self._reconstruir_grafica()

    def obtener_frecuencia_captura(self) -> int:
        try:
            valor = int(self.frecuencia_captura.get())
        except ValueError as exc:
            raise ValueError("La frecuencia de captura debe ser un entero") from exc
        if not 1 <= valor <= 100:
            raise ValueError("La frecuencia de captura debe estar entre 1 y 100")
        return valor

    def crear_control(self) -> ControlDidactico:
        try:
            retardo = float(self.retardo.get()) if self.didactico.get() else 0.0
        except ValueError as exc:
            raise ValueError("El retardo didáctico no es válido") from exc
        return ControlDidactico(retardo)

    def preparar(self, problema: Problema, configuracion: Configuracion, escenario_datos: dict) -> None:
        self.limpiar()
        self.problema, self.configuracion = problema, configuracion
        self.escenario_datos = deepcopy(escenario_datos)
        self.estado_calculo.set("Ejecutando · modo didáctico" if self.didactico.get() else "Ejecutando · modo rápido")
        self._actualizar_opciones()

    def agregar_instantanea(self, instantanea: InstantaneaEvolutiva) -> None:
        if self.instantaneas and instantanea.generacion <= self.instantaneas[-1].generacion:
            return
        self.instantaneas.append(instantanea)
        generaciones = [str(i.generacion) for i in self.instantaneas]
        self.selector_generacion["values"] = generaciones
        self.combo_izquierda["values"] = generaciones
        self.combo_derecha["values"] = generaciones
        self.escala.configure(to=max(0, len(self.instantaneas) - 1))
        self.kpis["capturas"].establecer(str(len(self.instantaneas)))
        ahora = monotonic()
        if self.seguir_ultima:
            self.indice_actual = len(self.instantaneas) - 1
            if ahora - self._ultima_vista >= .15 or len(self.instantaneas) == 1:
                self._mostrar_indice(self.indice_actual, desde_escala=False)
                self._ultima_vista = ahora
        if ahora - self._ultima_grafica >= .30 or len(self.instantaneas) == 1:
            self._reconstruir_grafica()
            self._ultima_grafica = ahora

    def finalizar(self, resultado: Resultado, cancelada: bool = False) -> None:
        if not self.problema or not self.configuracion or self.escenario_datos is None:
            return
        self.registro = RegistroEvolucion(
            VERSION_EVOLUCION, self.configuracion, deepcopy(self.escenario_datos),
            tuple(s.id for s in self.problema.sesiones), tuple(self.instantaneas),
            resultado.motivo_parada, cancelada,
        )
        self.estado_calculo.set("Cancelada · registro parcial" if cancelada else "Finalizada · reproducción disponible")
        self._ir_ultima()
        self._reconstruir_grafica()
        self._comparar_extremos()

    def mostrar_registro(self, registro: RegistroEvolucion) -> None:
        self.limpiar()
        self.registro = registro
        self.configuracion = registro.configuracion
        self.escenario_datos = deepcopy(registro.escenario_datos)
        self.problema = problema_desde_datos(registro.escenario_datos)
        self.estado_calculo.set("Registro cargado · sin recalcular el algoritmo")
        for instantanea in registro.instantaneas:
            self.agregar_instantanea(instantanea)
        self._ir_ultima()
        self._comparar_extremos()

    def _actualizar_opciones(self) -> None:
        if not self.problema:
            return
        if self.modo.get() == "grupo":
            opciones = list(self.problema.grupos)
        elif self.modo.get() == "docente":
            opciones = list(self.problema.docentes)
        else:
            opciones = [s.id for s in self.problema.salones]
        self.selector_entidad["values"] = opciones
        if self.identificador.get() not in opciones:
            self.identificador.set(opciones[0] if opciones else "")
        self._actualizar_vista()

    def _mover_escala(self, valor: str) -> None:
        if self.instantaneas and not self._ajustando_escala:
            self._mostrar_indice(round(float(valor)), desde_escala=True)

    def _seleccionar_generacion(self, _evento=None) -> None:
        buscada = int(self.generacion.get())
        indice = next((i for i, x in enumerate(self.instantaneas) if x.generacion == buscada), 0)
        self._mostrar_indice(indice, desde_escala=True)

    def _mostrar_indice(self, indice: int, desde_escala: bool = True) -> None:
        if not self.instantaneas:
            return
        indice = max(0, min(indice, len(self.instantaneas) - 1))
        self.indice_actual = indice
        if desde_escala:
            self.seguir_ultima = indice == len(self.instantaneas) - 1
        self._ajustando_escala = True
        self.escala.set(indice)
        self._ajustando_escala = False
        self.generacion.set(str(self.instantaneas[indice].generacion))
        self._actualizar_vista()
        self._actualizar_marcador()

    def _ir_ultima(self) -> None:
        self.seguir_ultima = True
        self._mostrar_indice(len(self.instantaneas) - 1 if self.instantaneas else 0, desde_escala=False)

    def _actualizar_vista(self) -> None:
        if not self.problema or not self.instantaneas or not self.identificador.get():
            self.calendario.limpiar()
            return
        actual = self.instantaneas[self.indice_actual]
        diferencia = None
        cambiados: set[int] = set()
        if self.indice_actual > 0:
            diferencia = comparar_instantaneas(self.problema, self.instantaneas[self.indice_actual - 1], actual)
            cambiados = {c.indice for c in diferencia.cambios if c.cambio_asignacion}
        self.calendario.mostrar(self.problema, actual, self.modo.get(), self.identificador.get(), cambiados)
        self._aplicar_metricas(actual, diferencia.sesiones_reasignadas if diferencia else 0)
        if diferencia:
            self._escribir_cambios("\n".join(describir_diferencia(self.problema, diferencia)))
        else:
            self._escribir_cambios(
                "POBLACIÓN INICIAL · GENERACIÓN 0\n\n"
                "Mejor individuo evaluado antes de selección, cruza o mutación.\n"
                "La muestra aleatoria inicial también se conserva en el registro."
            )

    def _aplicar_metricas(self, instantanea: InstantaneaEvolutiva, cambios: int) -> None:
        e, r = instantanea.evaluacion_global, instantanea.registro
        total = self.configuracion.generaciones if self.configuracion else "—"
        self.kpis["generacion"].establecer(f"{instantanea.generacion} / {total}")
        self.kpis["estado"].establecer("Factible" if e.factible else "No factible", "success" if e.factible else "danger")
        self.kpis["fitness"].establecer(str(e.fitness))
        self.kpis["duras"].establecer(str(e.duras), "success" if e.duras == 0 else "danger")
        self.kpis["blandas"].establecer(str(e.penalizacion_blanda), "success" if e.penalizacion_blanda == 0 else "warning")
        self.kpis["diversidad"].establecer(f"{r.diversidad:.1%}")
        self.kpis["primera"].establecer(
            f"G{instantanea.primera_generacion_factible}" if instantanea.primera_generacion_factible is not None else "Aún no",
            "success" if instantanea.primera_generacion_factible is not None else "neutral",
        )
        self.kpis["cambios"].establecer(str(cambios), "warning" if cambios else "neutral")
        self.kpis["tiempo"].establecer(f"{instantanea.tiempo_calculo:.3f} s")
        self.kpis["capturas"].establecer(str(len(self.instantaneas)))

    def _escribir_cambios(self, texto: str) -> None:
        self.texto_cambios.configure(state="normal")
        self.texto_cambios.delete("1.0", "end")
        self.texto_cambios.insert("1.0", texto)
        self.texto_cambios.configure(state="disabled")

    def reproducir(self) -> None:
        if not self.instantaneas:
            return
        if self.indice_actual >= len(self.instantaneas) - 1:
            self.indice_actual = 0
        self.reproduciendo = True
        self.seguir_ultima = False
        self.boton_play.configure(text="Reproduciendo…")
        self._paso_reproduccion()

    def pausar_reproduccion(self) -> None:
        self.reproduciendo = False
        self.boton_play.configure(text="Reproducir")

    def _paso_reproduccion(self) -> None:
        if not self.reproduciendo:
            return
        self._mostrar_indice(self.indice_actual, desde_escala=True)
        if self.indice_actual >= len(self.instantaneas) - 1:
            self.pausar_reproduccion()
            return
        self.indice_actual += 1
        try:
            demora = float(self.velocidad.get())
        except ValueError:
            demora = .5
        self.after(max(20, round(demora * 1000)), self._paso_reproduccion)

    def _reconstruir_grafica(self) -> None:
        if self.figura is None:
            return
        datos = (
            ("conflictos_duros", "Violaciones duras", lambda s: s.evaluacion_global.duras, PELIGRO),
            ("penalizacion", "Penalización blanda", lambda s: s.evaluacion_global.penalizacion_blanda, ADVERTENCIA),
            ("fitness", "Fitness", lambda s: s.evaluacion_global.fitness, "#1f6f8b"),
            ("diversidad", "Diversidad (%)", lambda s: s.registro.diversidad * 100, "#6f42c1"),
        )
        xs = [s.generacion for s in self.instantaneas]
        self._marcadores = []
        for eje, (_, titulo, valor, color) in zip(self.ejes, datos):
            eje.clear()
            if xs:
                eje.plot(xs, [valor(s) for s in self.instantaneas], color=color, linewidth=1.3)
                marcador = eje.axvline(self.instantaneas[self.indice_actual].generacion, color="#17202a", linestyle="--", linewidth=.8)
                self._marcadores.append(marcador)
            eje.set_title(titulo, fontsize=8)
            eje.tick_params(labelsize=7)
            eje.grid(alpha=.18)
        if xs:
            # Superposiciones de Fase 6: tasa adaptativa, búsqueda local,
            # mejoras globales y regiones de estancamiento registradas por el motor.
            eje_fitness = self.ejes[2]
            locales = [s for s in self.instantaneas if s.registro.aplicaciones_busqueda_local]
            if locales:
                eje_fitness.scatter(
                    [s.generacion for s in locales],
                    [s.evaluacion_global.fitness for s in locales],
                    marker="*", s=28, color="#0f9d58", label="Búsqueda local", zorder=4,
                )
            mejoras = [s for s in self.instantaneas if s.registro.mejoro_global]
            if mejoras:
                eje_fitness.scatter(
                    [s.generacion for s in mejoras],
                    [s.evaluacion_global.fitness for s in mejoras],
                    marker="o", s=10, color="#1f6f8b", label="Mejora global", zorder=3,
                )
            for s in self.instantaneas:
                if s.registro.estancada:
                    eje_fitness.axvspan(s.generacion - .5, s.generacion + .5, color="#94a3b8", alpha=.09)
            if locales or mejoras:
                eje_fitness.legend(fontsize=6, loc="best")
            eje_diversidad = self.ejes[3]
            eje_diversidad.plot(
                xs, [s.registro.prob_mutacion_usada * 100 for s in self.instantaneas],
                color="#e67e22", linestyle="--", linewidth=1.0, label="Mutación (%)",
            )
            eje_diversidad.legend(fontsize=6, loc="best")
            eje_diversidad.set_title("Diversidad y mutación (%)", fontsize=8)
        self.canvas_grafica.draw_idle()

    def _actualizar_marcador(self) -> None:
        if not self._marcadores or not self.instantaneas:
            return
        x = self.instantaneas[self.indice_actual].generacion
        for marcador in self._marcadores:
            marcador.set_xdata([x, x])
        self.canvas_grafica.draw_idle()

    def _comparar_extremos(self) -> None:
        if not self.instantaneas:
            return
        self.gen_izquierda.set(str(self.instantaneas[0].generacion))
        self.gen_derecha.set(str(self.instantaneas[-1].generacion))
        self._actualizar_comparacion()

    def _instantanea_por_generacion(self, texto: str) -> InstantaneaEvolutiva:
        generacion = int(texto)
        return next(s for s in self.instantaneas if s.generacion == generacion)

    def _actualizar_comparacion(self) -> None:
        if not self.problema or not self.instantaneas or not self.identificador.get():
            return
        izquierda = self._instantanea_por_generacion(self.gen_izquierda.get())
        derecha = self._instantanea_por_generacion(self.gen_derecha.get())
        diferencia = comparar_instantaneas(self.problema, izquierda, derecha)
        cambios = {c.indice for c in diferencia.cambios if c.cambio_asignacion}
        self.calendario_izquierdo.mostrar(self.problema, izquierda, self.modo.get(), self.identificador.get())
        self.calendario_derecho.mostrar(self.problema, derecha, self.modo.get(), self.identificador.get(), cambios)
        self.resumen_comparacion.set(
            f"Duras {diferencia.duras_antes}→{diferencia.duras_despues} · "
            f"sesiones {diferencia.sesiones_reasignadas} · día {diferencia.cambios_dia} · "
            f"hora {diferencia.cambios_hora} · salón {diferencia.cambios_salon}"
        )

    def _registro_disponible(self) -> RegistroEvolucion | None:
        if self.registro:
            return self.registro
        if self.problema and self.configuracion and self.escenario_datos and self.instantaneas:
            return RegistroEvolucion(
                VERSION_EVOLUCION, self.configuracion, deepcopy(self.escenario_datos),
                tuple(s.id for s in self.problema.sesiones), tuple(self.instantaneas),
                "en_curso", True,
            )
        return None

    def guardar(self) -> None:
        registro = self._registro_disponible()
        if registro is None:
            messagebox.showinfo("Sin evolución", "Ejecuta o abre una evolución antes de guardarla.", parent=self)
            return
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Guardar evolución", initialdir=self.base / "resultados",
            initialfile="evolucion_completa.json.gz", defaultextension=".json.gz",
            filetypes=[("JSON comprimido", "*.json.gz"), ("JSON", "*.json")],
        )
        if ruta:
            try:
                guardar_evolucion(registro, ruta)
            except OSError as exc:
                messagebox.showerror("No se pudo guardar", str(exc), parent=self)
                return
            messagebox.showinfo("Evolución guardada", f"Registro guardado en:\n{ruta}", parent=self)

    def abrir(self) -> None:
        ruta = filedialog.askopenfilename(
            parent=self, title="Abrir evolución", initialdir=self.base / "resultados",
            filetypes=[("Registros evolutivos", "*.json.gz *.json")],
        )
        if not ruta:
            return
        try:
            self.mostrar_registro(cargar_evolucion(ruta))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Registro no válido", str(exc), parent=self)

    def exportar_png(self) -> None:
        if not self.problema or not self.configuracion or not self.instantaneas:
            return
        ruta = filedialog.asksaveasfilename(parent=self, title="Exportar horario mostrado", defaultextension=".png", initialfile=f"generacion_{self.instantaneas[self.indice_actual].generacion}.png", filetypes=[("PNG", "*.png")])
        if ruta:
            exportar_instantanea_png(self.problema, self.configuracion, self.instantaneas[self.indice_actual], ruta, self.modo.get(), self.identificador.get())

    def exportar_comparacion(self) -> None:
        if not self.problema or not self.configuracion or not self.instantaneas:
            return
        ruta = filedialog.asksaveasfilename(parent=self, title="Exportar comparación", defaultextension=".png", initialfile="comparacion_generaciones.png", filetypes=[("PNG", "*.png")])
        if ruta:
            exportar_comparacion_png(self.problema, self.configuracion, self._instantanea_por_generacion(self.gen_izquierda.get()), self._instantanea_por_generacion(self.gen_derecha.get()), ruta, self.modo.get(), self.identificador.get())

    def exportar_secuencia(self) -> None:
        registro = self._registro_disponible()
        if registro is None or self.problema is None:
            return
        cada = simpledialog.askinteger("Intervalo", "Exportar una imagen cada cuántas instantáneas:", initialvalue=1, minvalue=1, maxvalue=100, parent=self)
        if cada is None:
            return
        carpeta = filedialog.askdirectory(parent=self, title="Carpeta para la secuencia")
        if carpeta:
            try:
                rutas = exportar_secuencia_png(self.problema, registro, carpeta, modo=self.modo.get(), identificador=self.identificador.get(), cada=cada)
            except (ValueError, ImportError, OSError) as exc:
                messagebox.showerror("No se pudo exportar", str(exc), parent=self)
                return
            messagebox.showinfo("Secuencia exportada", f"Se generaron {len(rutas)} imágenes.", parent=self)

    def exportar_animacion(self) -> None:
        registro = self._registro_disponible()
        if registro is None or self.problema is None:
            return
        cada = simpledialog.askinteger("Intervalo GIF", "Usar una instantánea de cada:", initialvalue=1, minvalue=1, maxvalue=100, parent=self)
        if cada is None:
            return
        duracion = simpledialog.askfloat("Duración GIF", "Segundos por fotograma:", initialvalue=.5, minvalue=.05, maxvalue=10, parent=self)
        if duracion is None:
            return
        ruta = filedialog.asksaveasfilename(parent=self, title="Exportar GIF", defaultextension=".gif", initialfile="evolucion.gif", filetypes=[("GIF", "*.gif")])
        if ruta:
            try:
                exportar_gif(self.problema, registro, ruta, modo=self.modo.get(), identificador=self.identificador.get(), cada=cada, duracion=duracion)
            except (ValueError, ImportError, OSError) as exc:
                messagebox.showerror("No se pudo exportar", str(exc), parent=self)

    def limpiar(self) -> None:
        self.pausar_reproduccion()
        self.problema = self.configuracion = self.escenario_datos = self.registro = None
        self.instantaneas.clear()
        self.indice_actual = 0
        self.seguir_ultima = True
        if hasattr(self, "calendario"):
            self.calendario.limpiar()
            self.calendario_izquierdo.limpiar("Sin comparación")
            self.calendario_derecho.limpiar("Sin comparación")
            self._escribir_cambios("Sin instantáneas. Inicia una ejecución o abre un registro guardado.")
        if hasattr(self, "kpis"):
            for tarjeta in self.kpis.values():
                tarjeta.establecer("—")
        if hasattr(self, "escala"):
            self.escala.configure(to=0)
            self.escala.set(0)
            self.selector_generacion["values"] = ()
        if hasattr(self, "estado_calculo"):
            self.estado_calculo.set("Sin ejecución")
        if hasattr(self, "figura"):
            self._reconstruir_grafica()

