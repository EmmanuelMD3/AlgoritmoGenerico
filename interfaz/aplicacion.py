"""Ventana principal y coordinación segura entre Tk y el motor genético."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from time import monotonic
from tkinter import messagebox, ttk

from horarios_ga.genetico import Configuracion, EjecucionCancelada, Resultado, ejecutar
from horarios_ga.constructor_escenarios import resumen_escenario
from .constructor_escenarios import VistaConstructorEscenarios
from .datos_academicos import ModeloDatosAcademicos, VistaDatosAcademicos
from .estilos import AZUL, FONDO, configurar_estilos
from .evolucion import VistaEvolucion
from .experimentacion import VistaExperimentacion
from .historial import VistaHistorial
from .horarios import VistaHorarios
from .optimizacion import VistaOptimizacion


class Aplicacion(tk.Tk):
    def __init__(self, base: Path | None = None):
        super().__init__()
        self.base = Path(base or Path(__file__).resolve().parents[1])
        self.carpeta_resultados = self.base / "resultados"
        self.title("Algoritmo Genético de Horarios Universitarios")
        self.geometry("1280x760")
        self.minsize(1040, 650)
        configurar_estilos(self)
        self.configure(bg=FONDO)

        self.modelo_datos = ModeloDatosAcademicos(self.base / "datos" / "ejemplo.json")
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancelacion = threading.Event()
        self.hilo: threading.Thread | None = None
        self.inicio_ejecucion = 0.0
        self.config_ejecucion: Configuracion | None = None
        self.problema_ejecucion = None
        self.resultado: Resultado | None = None
        self.control_didactico = None

        self._construir_encabezado()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(10, 6))

        self.optimizacion = VistaOptimizacion(
            self.notebook, self.iniciar_ejecucion, self.detener_ejecucion, self.limpiar_resultados,
            self.carpeta_resultados,
        )
        self.datos = VistaDatosAcademicos(self.notebook, self.modelo_datos, self._datos_cambiaron)
        self.horarios = VistaHorarios(self.notebook, self.carpeta_resultados)
        self.historial = VistaHistorial(self.notebook, self.carpeta_resultados)
        self.informacion = self._crear_informacion()
        self.experimentacion = VistaExperimentacion(self.notebook, self.base)
        self.evolucion = VistaEvolucion(
            self.notebook, self.base, self.iniciar_ejecucion, self.detener_ejecucion,
            self.pausar_calculo, self.continuar_calculo, self.ejecutar_paso,
        )
        self.constructor = VistaConstructorEscenarios(
            self.notebook, self.base, self.modelo_datos, self._datos_cambiaron,
            lambda: self.notebook.select(self.datos), self._activar_escenario,
        )
        self.experimentacion.al_visualizar_evolucion = self._visualizar_evolucion_experimental
        self.notebook.add(self.optimizacion, text="Optimización")
        self.notebook.add(self.datos, text="Datos académicos")
        self.notebook.add(self.horarios, text="Horarios generados")
        self.notebook.add(self.historial, text="Historial evolutivo")
        self.notebook.add(self.informacion, text="Información del algoritmo")
        self.notebook.add(self.experimentacion, text="Experimentación")
        self.notebook.add(self.evolucion, text="Evolución en vivo")
        self.notebook.add(self.constructor, text="Constructor de escenarios")

        self.estado_general = tk.StringVar(value="Listo · datos de ejemplo cargados y validados")
        ttk.Label(self, textvariable=self.estado_general, anchor="w", padding=(14, 4)).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._activar_escenario(mostrar_estado=False)

    def _construir_encabezado(self) -> None:
        encabezado = ttk.Frame(self, style="Header.TFrame", padding=(20, 13))
        encabezado.pack(fill="x")
        ttk.Label(
            encabezado, text="Algoritmo Genético de Horarios Universitarios", style="Header.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            encabezado, text="Cómputo Evolutivo · Optimización académica", style="Subheader.TLabel",
        ).pack(anchor="w", pady=(2, 0))

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

Las duras incluyen colisiones, disponibilidades, franjas no lectivas, periodos permitidos y máximos consecutivos. Las blandas consideran huecos, jornadas largas, sesiones finales aisladas, balance semanal, cambios de salón y preferencias docentes. Los pesos son experimentales y se muestran en el desglose.

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
            problema = self.modelo_datos.validar()
            frecuencia_captura = self.evolucion.obtener_frecuencia_captura()
            control_didactico = self.evolucion.crear_control()
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se puede ejecutar", str(exc), parent=self)
            return
        self.cancelacion.clear()
        self.problema_ejecucion = problema
        self.config_ejecucion = config
        self.resultado = None
        self.control_didactico = control_didactico
        self.inicio_ejecucion = monotonic()
        self.optimizacion.iniciar(config)
        self.horarios.limpiar()
        self.historial.limpiar()
        self.evolucion.preparar(problema, config, self.modelo_datos.datos)
        self.notebook.tab(self.datos, state="disabled")
        self.notebook.tab(self.constructor, state="disabled")
        self.estado_general.set("Ejecutando el algoritmo genético… la interfaz permanece disponible")

        def trabajador() -> None:
            try:
                resultado = ejecutar(
                    problema, config,
                    callback=lambda registro: self.cola.put(("progreso", registro)),
                    debe_cancelar=lambda: self.cancelacion.is_set() or control_didactico.cancelado,
                    callback_instantanea=lambda instantanea: self.cola.put(("instantanea", instantanea)),
                    capturar_cada=frecuencia_captura,
                    esperar_si_pausado=control_didactico.esperar,
                )
            except EjecucionCancelada as exc:
                self.cola.put(("cancelada", exc.resultado))
            except Exception as exc:  # el detalle técnico no se expone como traza al usuario
                self.cola.put(("error", exc))
            else:
                self.cola.put(("completa", resultado))

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
        while True:
            try:
                tipo, contenido = self.cola.get_nowait()
            except queue.Empty:
                break
            segundos = monotonic() - self.inicio_ejecucion
            if tipo == "progreso":
                self.optimizacion.actualizar(
                    contenido, self.config_ejecucion.generaciones, segundos,
                )
            elif tipo == "instantanea":
                self.evolucion.agregar_instantanea(contenido)
            elif tipo in {"completa", "cancelada"}:
                terminado = True
                resultado = contenido
                self.resultado = resultado
                self.optimizacion.finalizar(resultado, segundos, cancelada=tipo == "cancelada")
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
                self.optimizacion.error()
                self.evolucion.estado_calculo.set("Error durante la ejecución")
                self.estado_general.set("La ejecución terminó con un error")
                messagebox.showerror(
                    "Error durante la optimización",
                    f"No fue posible completar el algoritmo:\n{contenido}", parent=self,
                )
        if terminado:
            self.notebook.tab(self.datos, state="normal")
            self.notebook.tab(self.constructor, state="normal")
            self.hilo = None
            self.control_didactico = None
        elif self.hilo and self.hilo.is_alive():
            self.after(40, self._procesar_cola)
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
        self.limpiar_resultados()
        self.datos.refrescar()
        if hasattr(self, "constructor"):
            self.constructor.refrescar_desde_modelo()
        self._activar_escenario(mostrar_estado=False)
        self.estado_general.set("Escenario académico actualizado y validado; vuelve a ejecutar el algoritmo")

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
        generando = self.constructor.generando_lote
        if optimizando or experimentando or generando:
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
            if generando:
                self.constructor.cancelar_lote()
        if self.modelo_datos.modificado and not messagebox.askyesno(
            "Cambios sin guardar", "Hay cambios académicos sin guardar. ¿Deseas cerrar de todos modos?", parent=self,
        ):
            return
        self.destroy()


def iniciar() -> None:
    app = Aplicacion()
    app.mainloop()

