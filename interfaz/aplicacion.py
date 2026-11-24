"""Ventana principal y coordinación segura entre Tk y el motor genético."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from time import monotonic
from tkinter import messagebox, ttk

from horarios_ga.genetico import Configuracion, EjecucionCancelada, Resultado, ejecutar
from horarios_ga.diagnostico import diagnosticar_horario
from horarios_ga.constructor_escenarios import resumen_escenario
from .datos_academicos import ModeloDatosAcademicos, VistaDatosAcademicos
from .estilos import AZUL, EXITO, FONDO, PANEL, SECUNDARIO, configurar_estilos
from .evolucion import VistaEvolucion
from .experimentacion import VistaExperimentacion
from .historial import VistaHistorial
from .horarios import VistaHorarios
from .optimizacion import VistaOptimizacion


PESTANAS_APLICACION = (
    "Optimización", "Datos académicos", "Horarios generados",
    "Historial evolutivo", "Información del algoritmo", "Experimentación",
    "Evolución en vivo",
)

ICONOS_APLICACION = ("▶", "▦", "▤", "↗", "i", "◫", "◉")

EVENTOS_MAXIMOS_POR_CICLO = 8
PRESUPUESTO_CICLO_SEGUNDOS = .008
CAPACIDAD_COLA_EJECUCION = 2048


def extraer_lote_eventos(
    cola: queue.Queue,
    *,
    limite: int = EVENTOS_MAXIMOS_POR_CICLO,
    presupuesto: float = PRESUPUESTO_CICLO_SEGUNDOS,
    reloj=monotonic,
) -> list[tuple[str, object]]:
    """Extrae sin bloquear un lote acotado para devolver pronto el control a Tk."""
    inicio = reloj()
    lote: list[tuple[str, object]] = []
    while len(lote) < limite:
        if lote and reloj() - inicio >= presupuesto:
            break
        try:
            lote.append(cola.get_nowait())
        except queue.Empty:
            break
    return lote


class Aplicacion(tk.Tk):
    def __init__(self, base: Path | None = None):
        super().__init__()
        self.base = Path(base or Path(__file__).resolve().parents[1])
        self.carpeta_resultados = self.base / "resultados"
        self.title("Algoritmo Genético de Horarios Universitarios")
        self.geometry("1360x820")
        self.minsize(1100, 680)
        configurar_estilos(self)
        self.configure(bg=FONDO)

        self.modelo_datos = ModeloDatosAcademicos(
            self.base / "datos" / "ejemplo.json",
            self.base / "datos" / "configuracion_academica.json",
        )
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue(
            maxsize=CAPACIDAD_COLA_EJECUCION,
        )
        self.cancelacion = threading.Event()
        self.hilo: threading.Thread | None = None
        self.inicio_ejecucion = 0.0
        self.config_ejecucion: Configuracion | None = None
        self.problema_ejecucion = None
        self.resultado: Resultado | None = None
        self.huella_ejecucion: str | None = None
        self.nombre_ejecucion = ""
        self.control_didactico = None
        self.eventos_procesados = 0
        self.maximo_lote_procesado = 0

        cuerpo = tk.Frame(self, bg=FONDO)
        cuerpo.pack(fill="both", expand=True)
        self.barra_lateral = tk.Frame(cuerpo, bg=AZUL, width=218)
        self.barra_lateral.pack(side="left", fill="y")
        self.barra_lateral.pack_propagate(False)
        self._construir_marca_lateral()
        contenido = tk.Frame(cuerpo, bg=FONDO)
        contenido.pack(side="left", fill="both", expand=True)
        self._construir_encabezado(contenido)
        self.notebook = ttk.Notebook(contenido, style="Sidebar.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(8, 8))

        self.optimizacion = VistaOptimizacion(
            self.notebook, self.iniciar_ejecucion, self.detener_ejecucion, self.limpiar_resultados,
            self.carpeta_resultados,
        )
        self.datos = VistaDatosAcademicos(
            self.notebook, self.modelo_datos, self._datos_cambiaron,
            self._ejecutar_desde_datos,
        )
        self.horarios = VistaHorarios(self.notebook, self.carpeta_resultados)
        self.historial = VistaHistorial(self.notebook, self.carpeta_resultados)
        self.informacion = self._crear_informacion()
        self.experimentacion = VistaExperimentacion(self.notebook, self.base)
        self.evolucion = VistaEvolucion(
            self.notebook, self.base, self.iniciar_ejecucion, self.detener_ejecucion,
            self.pausar_calculo, self.continuar_calculo, self.ejecutar_paso,
        )
        self.experimentacion.al_visualizar_evolucion = self._visualizar_evolucion_experimental
        vistas = (
            self.optimizacion, self.datos, self.horarios, self.historial,
            self.informacion, self.experimentacion, self.evolucion,
        )
        for vista, titulo in zip(vistas, PESTANAS_APLICACION, strict=True):
            self.notebook.add(vista, text=titulo)
        self._construir_navegacion_lateral(vistas)
        self.notebook.bind("<<NotebookTabChanged>>", self._sincronizar_navegacion)

        self.estado_general = tk.StringVar(value="Listo · configuración académica validada")
        ttk.Label(
            contenido, textvariable=self.estado_general, anchor="w", padding=(16, 5),
        ).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._activar_escenario(mostrar_estado=False)

    def _construir_marca_lateral(self) -> None:
        marca = tk.Frame(self.barra_lateral, bg=AZUL, padx=18, pady=20)
        marca.pack(fill="x")
        tk.Label(
            marca, text="HG", bg="#16845b", fg="white", width=3, height=1,
            font=("Segoe UI Semibold", 15),
        ).pack(side="left")
        textos = tk.Frame(marca, bg=AZUL)
        textos.pack(side="left", padx=(10, 0))
        tk.Label(
            textos, text="Horarios", bg=AZUL, fg="white",
            font=("Segoe UI Semibold", 12), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            textos, text="Geneticos", bg=AZUL, fg="#a9bfd4",
            font=("Segoe UI", 9), anchor="w",
        ).pack(anchor="w")
        tk.Frame(self.barra_lateral, bg="#2b3d52", height=1).pack(fill="x", padx=16)
        self.contenedor_navegacion = tk.Frame(self.barra_lateral, bg=AZUL, padx=10, pady=15)
        self.contenedor_navegacion.pack(fill="both", expand=True)

    def _construir_encabezado(self, padre: tk.Misc) -> None:
        encabezado = tk.Frame(
            padre, bg=PANEL, highlightbackground="#e2e8f0",
            highlightthickness=1, padx=18, pady=10,
        )
        encabezado.pack(fill="x")
        self.titulo_seccion = tk.StringVar(value=PESTANAS_APLICACION[0])
        tk.Label(
            encabezado, textvariable=self.titulo_seccion, bg=PANEL, fg=AZUL,
            font=("Segoe UI Semibold", 16), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            encabezado, text="Administración académica y optimización evolutiva",
            bg=PANEL, fg=SECUNDARIO, font=("Segoe UI", 9), anchor="w",
        ).pack(anchor="w", pady=(1, 0))

    def _construir_navegacion_lateral(self, vistas) -> None:
        self.botones_navegacion: dict[str, tk.Button] = {}
        self.vistas_navegacion = tuple(vistas)
        for indice, (vista, titulo, icono) in enumerate(
            zip(vistas, PESTANAS_APLICACION, ICONOS_APLICACION, strict=True),
        ):
            boton = tk.Button(
                self.contenedor_navegacion, text=f" {icono}   {titulo}",
                command=lambda i=indice: self._seleccionar_seccion(i),
                anchor="w", relief="flat", borderwidth=0, padx=10, pady=10,
                bg=AZUL, fg="#c7d5e3", activebackground="#20364f",
                activeforeground="white", font=("Segoe UI Semibold", 9),
                cursor="hand2",
            )
            boton.pack(fill="x", pady=2)
            self.botones_navegacion[str(vista)] = boton
        self._sincronizar_navegacion()

    def _seleccionar_seccion(self, indice: int) -> None:
        vista = self.vistas_navegacion[indice]
        if str(self.notebook.tab(vista, "state")) != "disabled":
            self.notebook.select(vista)

    def _sincronizar_navegacion(self, _evento=None) -> None:
        if not hasattr(self, "botones_navegacion"):
            return
        seleccion = self.notebook.select()
        for indice, vista in enumerate(self.vistas_navegacion):
            activo = str(vista) == seleccion
            boton = self.botones_navegacion[str(vista)]
            boton.configure(
                bg="#16845b" if activo else AZUL,
                fg="white" if activo else "#c7d5e3",
            )
            if activo:
                self.titulo_seccion.set(PESTANAS_APLICACION[indice])

    def _establecer_navegacion_habilitada(self, vista, habilitada: bool) -> None:
        boton = self.botones_navegacion.get(str(vista))
        if boton is not None:
            boton.configure(state="normal" if habilitada else "disabled")

    def _crear_informacion(self) -> ttk.Frame:
        pagina = ttk.Frame(self.notebook, padding=16)
        marco = ttk.Frame(pagina, style="Panel.TFrame")
        marco.pack(fill="both", expand=True)
        texto = tk.Text(
            marco, wrap="word", bg="white", fg="#17202a", relief="flat",
            padx=24, pady=18, font=("Segoe UI", 10), spacing1=3, spacing3=7,
        )
        scroll = ttk.Scrollbar(marco, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=scroll.set)
        texto.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        contenido = """INFORMACIÓN DEL ALGORITMO

Individuo
Un individuo es un horario universitario completo: contiene una asignación para cada sesión que debe impartirse.

Cromosoma y gen
El cromosoma es la secuencia de todas las asignaciones. Cada gen representa (día, bloque de inicio, salón) para una sesión concreta. La materia, el grupo, el docente y la duración permanecen ligados a esa sesión.

Población inicial
Se generan horarios aleatorios que ya respetan los rangos, la duración, el tipo de salón y su capacidad. Todavía pueden contener colisiones entre clases o violar disponibilidad docente.

Selección por torneo
Se eligen varios individuos al azar. Gana primero el de menos violaciones duras y, en empate, el de menor penalización blanda. El fitness conserva una lectura numérica complementaria.

Cruza uniforme
Dos padres intercambian asignaciones gen a gen mediante una máscara aleatoria. La identidad de cada sesión no cambia.

Mutación y reparación
Cada gen puede cambiar de día, hora, salón o asignación completa. La mutación dirigida favorece sesiones conflictivas y la reparación local sólo conserva reasignaciones que mejoran la prioridad. Los inmigrantes aleatorios preservan diversidad.

Elitismo
Los mejores individuos pasan sin cambios a la siguiente generación, evitando perder las soluciones de mayor prioridad ya encontradas.

Evaluación
Prioridad(H) = (−violaciones_duras, −penalización_blanda)
Fitness(H) = 1000 − penalización_dura − penalización_blanda

Las duras incluyen colisiones, disponibilidades, franjas no lectivas, periodos permitidos y máximos consecutivos. Las blandas activas consideran huecos, jornadas largas, sesiones finales aisladas, balance semanal y cambios de salón. Los mapas preferidos de configuraciones anteriores se conservan como historial, pero la interfaz 7.2 registra explícitamente su desactivación para evitar penalizaciones invisibles.

Horario factible
Es factible respecto al modelo cuando la suma de violaciones duras es cero. Puede conservar penalizaciones blandas: factible no significa óptimo. La parada anticipada requiere además alcanzar el objetivo blando y permanecer varias generaciones sin mejora.
"""
        texto.insert("1.0", contenido)
        texto.tag_configure("titulo", font=("Segoe UI Semibold", 15), foreground=AZUL, spacing3=12)
        texto.tag_add("titulo", "1.0", "1.end")
        for encabezado in (
            "Individuo", "Cromosoma y gen", "Población inicial", "Selección por torneo",
            "Cruza uniforme", "Mutación y reparación", "Elitismo", "Evaluación", "Horario factible",
        ):
            inicio = texto.search(encabezado, "1.0", stopindex="end")
            if inicio:
                texto.tag_add("seccion", inicio, f"{inicio}+{len(encabezado)}c")
        texto.tag_configure("seccion", font=("Segoe UI Semibold", 11), foreground=AZUL, spacing1=8)
        texto.configure(state="disabled")
        return pagina

    def iniciar_ejecucion(self) -> None:
        if self.hilo and self.hilo.is_alive():
            return
        try:
            config = self.optimizacion.obtener_configuracion()
            datos_ejecucion = self.modelo_datos.instantanea()
            problema = self.modelo_datos.validar()
            resumen_ejecucion = resumen_escenario(datos_ejecucion)
            frecuencia_captura = self.evolucion.obtener_frecuencia_captura()
            control_didactico = self.evolucion.crear_control()
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se puede ejecutar", str(exc), parent=self)
            return
        self.cancelacion.clear()
        self.cola = queue.Queue(maxsize=CAPACIDAD_COLA_EJECUCION)
        self.eventos_procesados = 0
        self.maximo_lote_procesado = 0
        self.problema_ejecucion = problema
        self.config_ejecucion = config
        self.resultado = None
        self.huella_ejecucion = resumen_ejecucion["huella"]
        self.nombre_ejecucion = resumen_ejecucion["nombre"]
        self.control_didactico = control_didactico
        self.inicio_ejecucion = monotonic()
        self.optimizacion.iniciar(config)
        self.optimizacion.establecer_origen_resultado(
            self.nombre_ejecucion, self.huella_ejecucion,
        )
        self.horarios.limpiar()
        self.historial.limpiar()
        self.evolucion.preparar(problema, config, datos_ejecucion)
        self.notebook.tab(self.datos, state="disabled")
        self._establecer_navegacion_habilitada(self.datos, False)
        self.estado_general.set("Ejecutando el algoritmo genético… la interfaz permanece disponible")

        def trabajador() -> None:
            def enviar_instantanea(instantanea) -> None:
                control_didactico.notificar_captura(instantanea.generacion)
                self.cola.put(("instantanea", instantanea))

            try:
                resultado = ejecutar(
                    problema, config,
                    callback=lambda registro: self.cola.put(("progreso", registro)),
                    debe_cancelar=lambda: self.cancelacion.is_set() or control_didactico.cancelado,
                    callback_instantanea=enviar_instantanea,
                    capturar_cada=frecuencia_captura,
                    esperar_si_pausado=(
                        control_didactico.esperar
                        if self.evolucion.modo_didactico_activo else None
                    ),
                )
            except EjecucionCancelada as exc:
                diagnostico = diagnosticar_horario(problema, exc.resultado.cromosoma)
                self.cola.put(("cancelada", (exc.resultado, diagnostico)))
            except Exception as exc:  # el detalle técnico no se expone como traza al usuario
                self.cola.put(("error", exc))
            else:
                diagnostico = diagnosticar_horario(problema, resultado.cromosoma)
                self.cola.put(("completa", (resultado, diagnostico)))

        self.hilo = threading.Thread(target=trabajador, name="algoritmo-genetico", daemon=True)
        self.hilo.start()
        self.after(40, self._procesar_cola)

    def detener_ejecucion(self) -> None:
        if self.hilo and self.hilo.is_alive():
            self.cancelacion.set()
            if self.control_didactico is not None:
                self.control_didactico.cancelar()
            self.optimizacion.marcar_cancelacion()
            self.estado_general.set("Cancelación solicitada; esperando a que termine la generación actual…")

    def _procesar_cola(self) -> None:
        terminado = False
        presentar_rapido = False
        # El primer ciclo consume únicamente progreso + captura para que G0
        # alcance el bucle de dibujo antes de agrupar avances del modo rápido.
        limite = 2 if not self.evolucion.instantaneas else EVENTOS_MAXIMOS_POR_CICLO
        lote = extraer_lote_eventos(self.cola, limite=limite)
        self.eventos_procesados += len(lote)
        self.maximo_lote_procesado = max(self.maximo_lote_procesado, len(lote))
        for tipo, contenido in lote:
            segundos = monotonic() - self.inicio_ejecucion
            if tipo == "progreso":
                self.optimizacion.actualizar(
                    contenido, self.config_ejecucion.generaciones, segundos,
                )
            elif tipo == "instantanea":
                try:
                    agregada = self.evolucion.agregar_instantanea(
                        contenido,
                        actualizar_visual=self.evolucion.modo_didactico_activo,
                    )
                    presentar_rapido = presentar_rapido or (
                        agregada and not self.evolucion.modo_didactico_activo
                    )
                finally:
                    if self.control_didactico is not None:
                        self.control_didactico.confirmar_presentacion(
                            contenido.generacion,
                        )
            elif tipo in {"completa", "cancelada"}:
                terminado = True
                presentar_rapido = False
                resultado, diagnostico = contenido
                self.resultado = resultado
                self.optimizacion.finalizar(
                    resultado, segundos, cancelada=tipo == "cancelada",
                    diagnostico=diagnostico,
                )
                self.horarios.establecer_resultado(self.problema_ejecucion, resultado)
                self.historial.establecer_resultado(resultado)
                self.evolucion.finalizar(resultado, cancelada=tipo == "cancelada")
                self.estado_general.set(
                    "Ejecución cancelada; se conserva el mejor resultado parcial."
                    if tipo == "cancelada" else
                    f"Ejecución terminada en {segundos:.2f} s · "
                    + ("horario factible" if resultado.evaluacion.factible else "horario con conflictos")
                    + f" · penalización blanda {resultado.evaluacion.penalizacion_blanda}"
                )
            elif tipo == "error":
                terminado = True
                presentar_rapido = False
                self.optimizacion.error()
                self.evolucion.error()
                self.estado_general.set("La ejecución terminó con un error")
                messagebox.showerror(
                    "Error durante la optimización",
                    f"No fue posible completar el algoritmo:\n{contenido}", parent=self,
                )
        if presentar_rapido:
            self.evolucion.presentar_pendientes()
        if terminado:
            self.notebook.tab(self.datos, state="normal")
            self._establecer_navegacion_habilitada(self.datos, True)
            self.hilo = None
            self.control_didactico = None
        elif not self.cola.empty():
            self.after(1, self._procesar_cola)
        elif self.hilo and self.hilo.is_alive():
            self.after(16, self._procesar_cola)
        else:
            # El hilo puede finalizar justo después de vaciar la cola.
            self.after(20, self._procesar_cola)

    def limpiar_resultados(self) -> None:
        if self.hilo and self.hilo.is_alive():
            messagebox.showinfo(
                "Ejecución en curso", "Detén la ejecución antes de limpiar sus resultados.", parent=self,
            )
            return
        self.resultado = None
        self.optimizacion.limpiar()
        self.horarios.limpiar()
        self.historial.limpiar()
        self.evolucion.limpiar()
        self.estado_general.set("Resultados limpiados; los datos académicos se conservaron")

    def _datos_cambiaron(self) -> None:
        self.datos.refrescar()
        self._activar_escenario(mostrar_estado=False)
        actual = resumen_escenario(self.modelo_datos.datos)
        if self.resultado is not None and self.huella_ejecucion != actual["huella"]:
            self.optimizacion.establecer_origen_resultado(
                self.nombre_ejecucion, self.huella_ejecucion, historico=True,
            )
            self.estado_general.set(
                f"Datos activos actualizados · el resultado mostrado conserva la instantánea "
                f"{self.nombre_ejecucion} · SHA-256 {self.huella_ejecucion[:12]}…"
            )
        else:
            if self.resultado is not None and self.huella_ejecucion:
                self.optimizacion.establecer_origen_resultado(
                    self.nombre_ejecucion, self.huella_ejecucion,
                )
            self.estado_general.set("Configuración académica activa actualizada y validada")

    def _activar_escenario(self, mostrar_estado: bool = True) -> None:
        problema = self.modelo_datos.validar()
        resumen = resumen_escenario(self.modelo_datos.datos)
        texto = (
            f"{resumen['nombre']} · {resumen['grupos']} grupos · {resumen['docentes']} docentes · "
            f"{resumen['sesiones']} sesiones · {resumen['salones']} salones · "
            f"SHA-256 {resumen['huella'][:12]}…"
        )
        self.optimizacion.establecer_escenario(texto)
        self.experimentacion.establecer_escenario_activo(self.modelo_datos.datos, resumen["nombre"])
        if mostrar_estado:
            sucio = " (instantánea validada en memoria; cambios sin guardar)" if self.modelo_datos.modificado else ""
            self.estado_general.set(f"Escenario activo: {texto}{sucio}")

    def _ejecutar_desde_datos(self) -> None:
        """Conserva la navegación explícita y ejecuta la instantánea activa."""
        self.notebook.select(self.optimizacion)
        self.after_idle(self.iniciar_ejecucion)

    def pausar_calculo(self) -> None:
        if not (self.hilo and self.hilo.is_alive() and self.control_didactico):
            return
        if not self.evolucion.didactico.get():
            self.evolucion.estado_calculo.set("La pausa real sólo está disponible en ejecución didáctica")
            return
        self.control_didactico.pausar()
        self.evolucion.estado_calculo.set("Cálculo pausado en un punto seguro · la animación es independiente")

    def continuar_calculo(self) -> None:
        if self.hilo and self.hilo.is_alive() and self.control_didactico:
            self.control_didactico.continuar()
            self.evolucion.estado_calculo.set("Cálculo reanudado")

    def ejecutar_paso(self) -> None:
        if not (self.hilo and self.hilo.is_alive() and self.control_didactico):
            return
        if not self.evolucion.didactico.get():
            self.evolucion.estado_calculo.set("Activa ejecución didáctica para avanzar una generación")
            return
        self.control_didactico.paso()
        self.evolucion.estado_calculo.set("Avance de una generación solicitado")

    def _visualizar_evolucion_experimental(self, registro) -> None:
        self.evolucion.mostrar_registro(registro)
        self.notebook.select(self.evolucion)
        self.estado_general.set("Evolución experimental cargada para reproducción; no se recalculó el algoritmo")

    def _cerrar(self) -> None:
        optimizando = bool(self.hilo and self.hilo.is_alive())
        experimentando = self.experimentacion.en_ejecucion
        if optimizando or experimentando:
            if not messagebox.askyesno(
                "Cerrar aplicación",
                "Hay una ejecución en curso. ¿Deseas solicitar su cancelación y cerrar?",
                parent=self,
            ):
                return
            if optimizando:
                self.cancelacion.set()
                if self.control_didactico is not None:
                    self.control_didactico.cancelar()
            if experimentando:
                self.experimentacion.solicitar_cancelacion()
        if self.modelo_datos.modificado and not messagebox.askyesno(
            "Cambios sin guardar", "Hay cambios académicos sin guardar. ¿Deseas cerrar de todos modos?", parent=self,
        ):
            return
        self.destroy()


def iniciar() -> None:
    app = Aplicacion()
    app.mainloop()

