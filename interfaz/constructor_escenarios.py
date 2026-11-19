"""Octava pestaña: construcción y administración de escenarios académicos."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections import Counter
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from horarios_ga.constructor_escenarios import (
    PERFILES, ConfiguracionEscenario, GestorEscenarios, crear_escenario_manual,
    generar_escenario_configurable, generar_lote, resumen_escenario,
    validar_escenario_detallado,
)
from horarios_ga.datos import cargar_datos, guardar_datos

from .componentes import PanelDesplazable, SeccionPlegable, TarjetaKPI
from .datos_academicos import ModeloDatosAcademicos
from .estilos import AZUL, EXITO, PANEL, PELIGRO, SECUNDARIO, TEXTO


CAMPOS = (
    ("nombre", "Nombre del escenario", "Escenario configurable"),
    ("descripcion", "Descripción", "Escenario académico creado desde la interfaz"),
    ("docentes", "Docentes", "8"), ("grupos", "Grupos", "4"),
    ("materias", "Materias distintas", "8"), ("salones", "Salones", "5"),
    ("sesiones_por_asignacion", "Sesiones por asignación", "2"),
    ("duracion_sesion", "Duración de sesión (bloques)", "1"),
    ("estudiantes_por_grupo", "Estudiantes por grupo", "30"),
    ("dias_lectivos", "Días lectivos", "5"),
    ("hora_inicio", "Primer bloque", "07:00"), ("hora_fin", "Fin de jornada", "17:00"),
    ("duracion_bloque_minutos", "Duración de bloque (min)", "60"),
    ("semilla", "Semilla del escenario", "42"),
)


class VistaConstructorEscenarios(ttk.Frame):
    def __init__(
        self, padre: tk.Misc, base: Path, modelo: ModeloDatosAcademicos,
        al_cambiar: Callable[[], None], abrir_editor: Callable[[], None],
        usar_escenario: Callable[[], None],
    ):
        super().__init__(padre, padding=8)
        self.base = Path(base)
        self.modelo = modelo
        self.al_cambiar = al_cambiar
        self.abrir_editor = abrir_editor
        self.usar_escenario = usar_escenario
        self.gestor = GestorEscenarios(self.base / "escenarios_usuario")
        self.variables: dict[str, tk.StringVar] = {}
        self.modo = tk.StringVar(value="semiautomatico")
        self.perfil = tk.StringVar(value="moderado")
        self.factibilidad = tk.BooleanVar(value=True)
        self.estres = tk.BooleanVar(value=False)
        self.porcentaje_disponible = tk.StringVar(value="0.80")
        self.proporcion_laboratorios = tk.StringVar(value="0.30")
        self.coincidencia = tk.StringVar(value="0.45")
        self.restricciones = tk.StringVar(value="2")
        self.estimacion = tk.StringVar(value="—")
        self.estado = tk.StringVar(value="Constructor listo")
        self.lote_cantidad = tk.StringVar(value="5")
        self.lote_variacion = tk.StringVar(value="0.0")
        self.lote_semilla = tk.StringVar(value="100")
        self.vista_previa = tk.StringVar(value="Carga por grupo")
        self.cancelacion_lote = threading.Event()
        self.cola_lote: queue.Queue[tuple[str, object]] = queue.Queue()
        self.hilo_lote: threading.Thread | None = None

        panel = ttk.Panedwindow(self, orient="horizontal")
        panel.pack(fill="both", expand=True)
        izquierda = ttk.Frame(panel, style="Panel.TFrame", padding=8, width=330)
        derecha = ttk.Frame(panel, style="Panel.TFrame", padding=(10, 8))
        panel.add(izquierda, weight=0)
        panel.add(derecha, weight=1)
        self._crear_configuracion(izquierda)
        self._crear_contenido(derecha)
        self.refrescar_desde_modelo()
        self._refrescar_lista()

    @property
    def generando_lote(self) -> bool:
        return bool(self.hilo_lote and self.hilo_lote.is_alive())

    def _entrada(self, padre: tk.Misc, clave: str, etiqueta: str, valor: str) -> None:
        fila = ttk.Frame(padre, style="Panel.TFrame")
        fila.pack(fill="x", pady=2)
        ttk.Label(fila, text=etiqueta, style="Campo.TLabel").pack(side="left")
        variable = tk.StringVar(value=valor)
        variable.trace_add("write", lambda *_a: self._actualizar_estimacion())
        self.variables[clave] = variable
        ttk.Entry(fila, textvariable=variable, width=13, justify="right").pack(side="right")

    def _crear_configuracion(self, padre: tk.Misc) -> None:
        ttk.Label(padre, text="Constructor de escenarios", style="PanelTitulo.TLabel").pack(anchor="w")
        ttk.Label(
            padre, text="Crear → editar → validar → guardar → utilizar",
            style="Ayuda.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        desplazable = PanelDesplazable(padre, ancho=310)
        desplazable.pack(fill="both", expand=True)
        general = SeccionPlegable(desplazable.interior, "1. Configuración general", True)
        general.pack(fill="x", pady=(0, 6))
        fila = ttk.Frame(general.contenido, style="Panel.TFrame")
        fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Modo").pack(side="left")
        ttk.Combobox(
            fila, textvariable=self.modo,
            values=("manual", "semiautomatico", "automatico"), state="readonly", width=16,
        ).pack(side="right")
        for clave, etiqueta, valor in CAMPOS:
            self._entrada(general.contenido, clave, etiqueta, valor)
        ttk.Label(
            general.contenido, textvariable=self.estimacion,
            style="Ayuda.TLabel", wraplength=280, justify="left",
        ).pack(fill="x", pady=(5, 0))

        dificultad = SeccionPlegable(desplazable.interior, "2. Dificultad y restricciones", False)
        dificultad.pack(fill="x", pady=(0, 6))
        fila = ttk.Frame(dificultad.contenido, style="Panel.TFrame")
        fila.pack(fill="x", pady=2)
        ttk.Label(fila, text="Perfil").pack(side="left")
        combo_perfil = ttk.Combobox(
            fila, textvariable=self.perfil,
            values=("facil", "moderado", "dificil", "personalizado"), state="readonly", width=16,
        )
        combo_perfil.pack(side="right")
        combo_perfil.bind("<<ComboboxSelected>>", self._aplicar_perfil)
        for etiqueta, variable in (
            ("Bloques disponibles (0–1)", self.porcentaje_disponible),
            ("Proporción laboratorios", self.proporcion_laboratorios),
            ("Coincidencia disponibilidades", self.coincidencia),
            ("Cantidad de restricciones", self.restricciones),
        ):
            fila = ttk.Frame(dificultad.contenido, style="Panel.TFrame")
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text=etiqueta).pack(side="left")
            ttk.Entry(fila, textvariable=variable, width=10, justify="right").pack(side="right")
        ttk.Checkbutton(
            dificultad.contenido, text="Generar con solución factible conocida",
            variable=self.factibilidad,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            dificultad.contenido, text="Escenario de estrés (sin garantía)", variable=self.estres,
        ).pack(anchor="w", pady=2)
        ttk.Label(
            dificultad.contenido,
            text="Los perfiles orientan la generación; no certifican dificultad matemática.",
            style="Ayuda.TLabel", wraplength=280,
        ).pack(fill="x", pady=(3, 0))

        acciones = SeccionPlegable(desplazable.interior, "3. Generación y edición", True)
        acciones.pack(fill="x", pady=(0, 6))
        ttk.Button(acciones.contenido, text="Crear escenario manual", command=self.crear_manual).pack(fill="x", pady=2)
        ttk.Button(acciones.contenido, text="Generar escenario", style="Accent.TButton", command=self.generar).pack(fill="x", pady=2)
        ttk.Button(acciones.contenido, text="Abrir editor académico detallado", command=self.abrir_editor).pack(fill="x", pady=2)
        ttk.Button(acciones.contenido, text="Validar escenario", command=self.validar).pack(fill="x", pady=2)
        ttk.Button(acciones.contenido, text="Utilizar en Optimización", command=self._utilizar).pack(fill="x", pady=2)

        lote = SeccionPlegable(desplazable.interior, "4. Generación por lotes", False)
        lote.pack(fill="x", pady=(0, 6))
        for etiqueta, variable in (
            ("Cantidad", self.lote_cantidad), ("Semilla inicial", self.lote_semilla),
            ("Variación (0–0.5)", self.lote_variacion),
        ):
            fila = ttk.Frame(lote.contenido, style="Panel.TFrame")
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text=etiqueta).pack(side="left")
            ttk.Entry(fila, textvariable=variable, width=10, justify="right").pack(side="right")
        ttk.Button(lote.contenido, text="Generar lote…", command=self.iniciar_lote).pack(fill="x", pady=2)
        ttk.Button(lote.contenido, text="Cancelar lote", command=self.cancelar_lote).pack(fill="x", pady=2)
        ttk.Label(lote.contenido, textvariable=self.estado, style="Ayuda.TLabel", wraplength=280).pack(fill="x", pady=3)

    def _crear_contenido(self, padre: tk.Misc) -> None:
        self.pestanas = ttk.Notebook(padre)
        self.pestanas.pack(fill="both", expand=True)
        previa = ttk.Frame(self.pestanas, style="Panel.TFrame", padding=8)
        validacion = ttk.Frame(self.pestanas, style="Panel.TFrame", padding=8)
        escenarios = ttk.Frame(self.pestanas, style="Panel.TFrame", padding=8)
        self.pestanas.add(previa, text="Vista previa")
        self.pestanas.add(validacion, text="Validación")
        self.pestanas.add(escenarios, text="Mis escenarios")
        self._crear_previa(previa)
        self._crear_validacion(validacion)
        self._crear_escenarios(escenarios)

    def _crear_previa(self, padre: tk.Misc) -> None:
        tarjetas = ttk.Frame(padre, style="Panel.TFrame")
        tarjetas.pack(fill="x")
        self.kpis: dict[str, TarjetaKPI] = {}
        for i, (clave, titulo) in enumerate((
            ("docentes", "Docentes"), ("grupos", "Grupos"), ("materias", "Materias"),
            ("sesiones", "Sesiones"), ("salones", "Salones"), ("demanda_bloques", "Demanda de bloques"),
        )):
            tarjeta = TarjetaKPI(tarjetas, titulo)
            tarjeta.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            tarjetas.columnconfigure(i % 3, weight=1, uniform="previa")
            self.kpis[clave] = tarjeta
        self.identidad = tk.StringVar()
        ttk.Label(padre, textvariable=self.identidad, style="Ayuda.TLabel").pack(fill="x", pady=5)
        cuerpo = ttk.Panedwindow(padre, orient="horizontal")
        cuerpo.pack(fill="both", expand=True)
        tabla_marco = ttk.Frame(cuerpo, style="Panel.TFrame")
        grafica_marco = ttk.Frame(cuerpo, style="Panel.TFrame")
        cuerpo.add(tabla_marco, weight=2)
        cuerpo.add(grafica_marco, weight=1)
        self.tabla_previa = ttk.Treeview(
            tabla_marco, columns=("entidad", "valor", "detalle"), show="headings",
        )
        for clave, texto, ancho in (("entidad", "Indicador", 180), ("valor", "Valor", 90), ("detalle", "Interpretación", 300)):
            self.tabla_previa.heading(clave, text=texto)
            self.tabla_previa.column(clave, width=ancho)
        self.tabla_previa.pack(fill="both", expand=True)
        cabecera = ttk.Frame(grafica_marco, style="Panel.TFrame")
        cabecera.pack(fill="x")
        self.titulo_grafica = ttk.Label(
            cabecera, text="Resumen académico", style="PanelTitulo.TLabel",
        )
        self.titulo_grafica.pack(side="left")
        selector = ttk.Combobox(
            cabecera, textvariable=self.vista_previa, state="readonly", width=24,
            values=(
                "Carga por grupo", "Sesiones por materia", "Demanda por tipo de salón",
                "Indisponibilidad docente", "Bloques institucionales",
            ),
        )
        selector.pack(side="right")
        selector.bind("<<ComboboxSelected>>", lambda _e: self._dibujar_carga())
        self.grafica = tk.Canvas(grafica_marco, bg=PANEL, highlightthickness=0, width=360)
        self.grafica.pack(fill="both", expand=True)
        self.grafica.bind("<Configure>", lambda _e: self._dibujar_carga())

    def _crear_validacion(self, padre: tk.Misc) -> None:
        ttk.Label(
            padre,
            text="Una estructura válida no demuestra factibilidad matemática.",
            style="Ayuda.TLabel",
        ).pack(fill="x", pady=(0, 5))
        self.tabla_validacion = ttk.Treeview(
            padre, columns=("nivel", "codigo", "mensaje"), show="headings",
        )
        for clave, texto, ancho in (("nivel", "Nivel", 100), ("codigo", "Código", 170), ("mensaje", "Detalle", 650)):
            self.tabla_validacion.heading(clave, text=texto)
            self.tabla_validacion.column(clave, width=ancho)
        self.tabla_validacion.pack(fill="both", expand=True)

    def _crear_escenarios(self, padre: tk.Misc) -> None:
        barra = ttk.Frame(padre, style="Panel.TFrame")
        barra.pack(fill="x", pady=(0, 5))
        for texto, comando in (
            ("Abrir", self.abrir_seleccionado), ("Guardar", self.guardar),
            ("Guardar como", self.guardar_como), ("Duplicar", self.duplicar),
            ("Renombrar", self.renombrar), ("Eliminar", self.eliminar),
            ("Importar JSON", self.importar), ("Exportar JSON", self.exportar),
            ("Restaurar ejemplo", self.restaurar),
        ):
            ttk.Button(barra, text=texto, command=comando).pack(side="left", padx=2)
        self.lista = ttk.Treeview(
            padre, columns=("archivo", "nombre", "sesiones", "huella"), show="headings", selectmode="browse",
        )
        for clave, texto, ancho in (("archivo", "Archivo", 220), ("nombre", "Escenario", 220), ("sesiones", "Sesiones", 80), ("huella", "SHA-256", 290)):
            self.lista.heading(clave, text=texto)
            self.lista.column(clave, width=ancho)
        self.lista.pack(fill="both", expand=True)
        self.lista.bind("<Double-1>", lambda _e: self.abrir_seleccionado())

    def _configuracion(self) -> ConfiguracionEscenario:
        try:
            return ConfiguracionEscenario(
                nombre=self.variables["nombre"].get().strip(), descripcion=self.variables["descripcion"].get().strip(),
                modo=self.modo.get(), perfil=self.perfil.get(),
                docentes=int(self.variables["docentes"].get()), grupos=int(self.variables["grupos"].get()),
                materias=int(self.variables["materias"].get()), salones=int(self.variables["salones"].get()),
                sesiones_por_asignacion=int(self.variables["sesiones_por_asignacion"].get()),
                duracion_sesion=int(self.variables["duracion_sesion"].get()),
                estudiantes_por_grupo=int(self.variables["estudiantes_por_grupo"].get()),
                dias_lectivos=int(self.variables["dias_lectivos"].get()),
                hora_inicio=self.variables["hora_inicio"].get(), hora_fin=self.variables["hora_fin"].get(),
                duracion_bloque_minutos=int(self.variables["duracion_bloque_minutos"].get()),
                semilla=int(self.variables["semilla"].get()),
                porcentaje_disponible=float(self.porcentaje_disponible.get()),
                proporcion_laboratorios=float(self.proporcion_laboratorios.get()),
                coincidencia_disponibilidades=float(self.coincidencia.get()),
                cantidad_restricciones=int(self.restricciones.get()),
                factibilidad_conocida=self.factibilidad.get(), estres=self.estres.get(),
            )
        except ValueError as exc:
            raise ValueError("Las cantidades y porcentajes deben contener números válidos") from exc

    def _aplicar_perfil(self, _evento: object | None = None) -> None:
        valores = PERFILES.get(self.perfil.get())
        if valores is None:
            return
        self.porcentaje_disponible.set(f"{valores['disponibilidad']:.2f}")
        self.proporcion_laboratorios.set(f"{valores['laboratorios']:.2f}")
        self.coincidencia.set(f"{valores['coincidencia']:.2f}")
        self._actualizar_estimacion()

    def _actualizar_estimacion(self) -> None:
        try:
            config = self._configuracion()
            self.estimacion.set(
                f"Estimación: {config.materias} materias distintas → "
                f"{config.asignaciones_estimadas} asignaciones → {config.sesiones_estimadas} sesiones/genes."
            )
        except (ValueError, KeyError):
            self.estimacion.set("Completa valores válidos para estimar sesiones.")

    def _confirmar_reemplazo(self) -> bool:
        return not self.modelo.modificado or messagebox.askyesno(
            "Cambios sin guardar", "El escenario actual tiene cambios sin guardar. ¿Deseas reemplazarlo?", parent=self,
        )

    def crear_manual(self) -> None:
        if not self._confirmar_reemplazo():
            return
        datos = crear_escenario_manual(self.variables["nombre"].get().strip() or "Nuevo escenario manual")
        self.modelo.adoptar(datos, modificado=True)
        self._cambio_compartido("Escenario manual creado; completa sus entidades en Datos académicos")

    def generar(self) -> None:
        if not self._confirmar_reemplazo():
            return
        try:
            config = self._configuracion()
            config.validar()
            datos = generar_escenario_configurable(config)
        except (ValueError, AssertionError) as exc:
            messagebox.showerror("No se pudo generar", str(exc), parent=self)
            return
        self.modelo.adoptar(datos, modificado=True)
        self._cambio_compartido(
            f"Escenario generado con semilla {config.semilla}; aún no está guardado"
        )

    def _cambio_compartido(self, texto: str) -> None:
        self.al_cambiar()
        self.refrescar_desde_modelo()
        self.estado.set(texto)

    def validar(self) -> None:
        resultado = validar_escenario_detallado(self.modelo.datos)
        self._mostrar_validacion(resultado)
        self.pestanas.select(1)
        if resultado.errores:
            messagebox.showerror("Escenario con errores", f"Se encontraron {len(resultado.errores)} errores.", parent=self)
        elif resultado.advertencias:
            messagebox.showwarning(
                "Escenario válido con advertencias",
                f"La estructura es válida; revisa {len(resultado.advertencias)} advertencias. No se certifica factibilidad.", parent=self,
            )
        else:
            messagebox.showinfo(
                "Validación correcta", "Los datos superan las validaciones implementadas. Esto no prueba optimalidad ni factibilidad matemática.", parent=self,
            )

    def _mostrar_validacion(self, resultado) -> None:
        self.tabla_validacion.delete(*self.tabla_validacion.get_children())
        for i, incidencia in enumerate(resultado.incidencias):
            self.tabla_validacion.insert("", "end", iid=str(i), values=(incidencia.nivel.upper(), incidencia.codigo, incidencia.mensaje))

    def refrescar_desde_modelo(self) -> None:
        try:
            resumen = resumen_escenario(self.modelo.datos)
            validacion = validar_escenario_detallado(self.modelo.datos)
        except (ValueError, KeyError, TypeError):
            return
        for clave, tarjeta in self.kpis.items():
            tarjeta.establecer(str(resumen[clave]), "Calculado del escenario activo")
        marca = " · cambios sin guardar" if self.modelo.modificado else ""
        self.identidad.set(
            f"{resumen['nombre']}{marca} · SHA-256 {resumen['huella'][:16]}… · "
            f"{resumen['dias']} días × {resumen['bloques_por_dia']} bloques"
        )
        self.tabla_previa.delete(*self.tabla_previa.get_children())
        filas = (
            ("Asignaciones materia–grupo", resumen["asignaciones"], "No equivale al número de sesiones"),
            ("Bloques institucionales disponibles", resumen["bloques_disponibles_institucionales"], "Por día y semana; sin descontar entidades"),
            ("Capacidad temporal aproximada", resumen["capacidad_temporal_aproximada"], "Bloques × salones; ignora compatibilidades"),
            ("Franjas no lectivas", resumen["franjas_no_lectivas"], "Restricción institucional dura"),
            ("Huella completa", resumen["huella"], "Identifica exactamente los datos"),
        )
        for i, fila in enumerate(filas):
            self.tabla_previa.insert("", "end", iid=str(i), values=fila)
        self._mostrar_validacion(validacion)
        self._dibujar_carga()

    def _dibujar_carga(self) -> None:
        if not hasattr(self, "grafica"):
            return
        self.grafica.delete("all")
        datos = self.modelo.datos
        vista = self.vista_previa.get()
        carga = Counter()
        if vista == "Carga por grupo":
            for clase in datos.get("clases", []):
                try:
                    carga[str(clase["grupo"])] += int(clase.get("sesiones_semana", 1)) * int(clase.get("duracion_bloques", 1))
                except (TypeError, ValueError, KeyError):
                    continue
        elif vista == "Sesiones por materia":
            for clase in datos.get("clases", []):
                try:
                    carga[str(clase.get("materia", "Sin materia"))] += int(clase.get("sesiones_semana", 1))
                except (TypeError, ValueError):
                    continue
        elif vista == "Demanda por tipo de salón":
            for clase in datos.get("clases", []):
                try:
                    carga[str(clase.get("tipo_salon", "aula"))] += int(clase.get("sesiones_semana", 1)) * int(clase.get("duracion_bloques", 1))
                except (TypeError, ValueError):
                    continue
        elif vista == "Indisponibilidad docente":
            for docente in datos.get("docentes", []):
                carga[str(docente.get("id", "?"))] = sum(
                    len(horas) for horas in docente.get("no_disponible", {}).values()
                )
        else:
            franjas = datos.get("restricciones", {}).get("franjas_no_lectivas", {})
            for dia in datos.get("dias", []):
                carga[str(dia)] = len(franjas.get(dia, []))
        self.titulo_grafica.configure(text=vista)
        ancho = max(240, self.grafica.winfo_width())
        alto = max(160, self.grafica.winfo_height())
        if not carga:
            self.grafica.create_text(ancho / 2, alto / 2, text="Sin datos calculables", fill=SECUNDARIO)
            return
        items = carga.most_common(12)
        maximo = max(v for _, v in items) or 1
        alto_barra = max(14, (alto - 24) / len(items) - 5)
        for i, (grupo, valor) in enumerate(items):
            y = 14 + i * (alto_barra + 5)
            self.grafica.create_text(5, y + alto_barra / 2, text=grupo, anchor="w", fill=TEXTO, font=("Segoe UI", 8))
            x0 = 80
            x1 = x0 + (ancho - 130) * valor / maximo
            self.grafica.create_rectangle(x0, y, x1, y + alto_barra, fill=AZUL, outline="")
            self.grafica.create_text(x1 + 5, y + alto_barra / 2, text=str(valor), anchor="w", fill=TEXTO, font=("Segoe UI", 8))

    def _utilizar(self) -> None:
        resultado = validar_escenario_detallado(self.modelo.datos)
        if resultado.errores:
            self._mostrar_validacion(resultado)
            self.pestanas.select(1)
            messagebox.showerror("No se puede utilizar", "Corrige los errores estructurales antes de ejecutar.", parent=self)
            return
        # Política explícita: Optimización usa una instantánea validada en memoria;
        # no obliga a guardar y el estado sucio permanece visible.
        self.usar_escenario()
        self.estado.set("Escenario activo: se ejecutará la instantánea validada actualmente en memoria")

    def _seleccion(self) -> Path | None:
        seleccion = self.lista.selection()
        if not seleccion:
            messagebox.showinfo("Selecciona un escenario", "Selecciona primero un archivo administrado.", parent=self)
            return None
        return Path(seleccion[0])

    def _refrescar_lista(self) -> None:
        self.lista.delete(*self.lista.get_children())
        for ruta in self.gestor.listar():
            try:
                datos = cargar_datos(ruta)
                resumen = resumen_escenario(datos)
                valores = (ruta.name, resumen["nombre"], resumen["sesiones"], resumen["huella"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                valores = (ruta.name, "No válido", "—", str(exc))
            self.lista.insert("", "end", iid=str(ruta), values=valores)

    def abrir_seleccionado(self) -> None:
        ruta = self._seleccion()
        if ruta is None or not self._confirmar_reemplazo():
            return
        try:
            self.modelo.cargar(ruta)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se pudo abrir", str(exc), parent=self)
            return
        self._cambio_compartido(f"Escenario abierto: {ruta.name}")

    def guardar(self) -> None:
        nombre = self.modelo.nombre_escenario
        ruta = self.modelo.ruta_actual.resolve()
        try:
            if ruta.parent == self.gestor.directorio:
                self.modelo.guardar(ruta)
            else:
                destino = self.gestor.guardar(nombre, self.modelo.datos)
                self.modelo.guardar(destino)
        except (OSError, ValueError, FileExistsError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self._refrescar_lista()
        self.refrescar_desde_modelo()
        self.estado.set("Escenario guardado")

    def guardar_como(self) -> None:
        nombre = simpledialog.askstring("Guardar como", "Nombre del nuevo escenario:", initialvalue=self.modelo.nombre_escenario, parent=self)
        if not nombre:
            return
        datos = deepcopy(self.modelo.datos)
        datos.setdefault("metadatos", {})["nombre"] = nombre
        try:
            destino = self.gestor.guardar(nombre, datos)
            self.modelo.adoptar(datos, ruta=destino, modificado=False)
        except (OSError, ValueError, FileExistsError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self._cambio_compartido(f"Escenario guardado como {destino.name}")
        self._refrescar_lista()

    def duplicar(self) -> None:
        ruta = self._seleccion()
        if ruta is None:
            return
        nombre = simpledialog.askstring("Duplicar", "Nombre de la copia:", initialvalue=ruta.stem + " copia", parent=self)
        if not nombre:
            return
        try:
            self.gestor.duplicar(ruta, nombre)
        except (OSError, ValueError, FileExistsError) as exc:
            messagebox.showerror("No se pudo duplicar", str(exc), parent=self)
        self._refrescar_lista()

    def renombrar(self) -> None:
        ruta = self._seleccion()
        if ruta is None:
            return
        nombre = simpledialog.askstring("Renombrar", "Nuevo nombre:", initialvalue=ruta.stem, parent=self)
        if not nombre:
            return
        try:
            destino = self.gestor.renombrar(ruta, nombre)
            if self.modelo.ruta_actual.resolve() == ruta.resolve():
                self.modelo.cargar(destino)
        except (OSError, ValueError, FileExistsError) as exc:
            messagebox.showerror("No se pudo renombrar", str(exc), parent=self)
        self._refrescar_lista()

    def eliminar(self) -> None:
        ruta = self._seleccion()
        if ruta is None or not messagebox.askyesno("Eliminar escenario", f"¿Eliminar definitivamente {ruta.name}?", parent=self):
            return
        try:
            self.gestor.eliminar(ruta)
        except (OSError, ValueError) as exc:
            messagebox.showerror("No se pudo eliminar", str(exc), parent=self)
        self._refrescar_lista()

    def importar(self) -> None:
        ruta = filedialog.askopenfilename(parent=self, title="Importar escenario JSON", filetypes=[("JSON", "*.json")])
        if not ruta or not self._confirmar_reemplazo():
            return
        try:
            datos = cargar_datos(ruta)
            # adoptar valida mediante el cargador seguro; nunca ejecuta contenido.
            self.modelo.adoptar(datos, ruta=ruta, modificado=False)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Importación no válida", str(exc), parent=self)
            return
        self._cambio_compartido(f"Escenario importado desde {Path(ruta).name}")
        self.modelo.modificado = False

    def exportar(self) -> None:
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar escenario", defaultextension=".json",
            initialfile=self.modelo.nombre_escenario + ".json", filetypes=[("JSON", "*.json")],
        )
        if ruta:
            try:
                guardar_datos(self.modelo.datos, ruta)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("No se pudo exportar", str(exc), parent=self)

    def restaurar(self) -> None:
        if not self._confirmar_reemplazo():
            return
        self.modelo.restaurar()
        self._cambio_compartido("Escenario de ejemplo restaurado")

    def iniciar_lote(self) -> None:
        if self.generando_lote:
            return
        try:
            config = self._configuracion()
            cantidad = int(self.lote_cantidad.get())
            semilla = int(self.lote_semilla.get())
            variacion = float(self.lote_variacion.get())
            config.validar()
        except ValueError as exc:
            messagebox.showerror("Lote no válido", str(exc), parent=self)
            return
        carpeta = filedialog.askdirectory(
            parent=self, title="Carpeta para el lote", initialdir=self.gestor.directorio,
        )
        if not carpeta:
            return
        self.cancelacion_lote.clear()
        self.estado.set(f"Generando 0 / {cantidad} escenarios…")

        def trabajador() -> None:
            try:
                registros = generar_lote(
                    config, cantidad, carpeta, semilla_inicial=semilla, variacion=variacion,
                    debe_cancelar=self.cancelacion_lote.is_set,
                    al_generar=lambda r: self.cola_lote.put(("progreso", (r, cantidad))),
                )
            except Exception as exc:
                self.cola_lote.put(("error", exc))
            else:
                self.cola_lote.put(("final", registros))

        self.hilo_lote = threading.Thread(target=trabajador, name="generador-escenarios", daemon=True)
        self.hilo_lote.start()
        self.after(60, self._procesar_lote)

    def cancelar_lote(self) -> None:
        if self.generando_lote:
            self.cancelacion_lote.set()
            self.estado.set("Cancelación solicitada; se conservarán los JSON ya terminados")

    def _procesar_lote(self) -> None:
        termino = False
        while True:
            try:
                tipo, contenido = self.cola_lote.get_nowait()
            except queue.Empty:
                break
            if tipo == "progreso":
                registro, total = contenido
                self.estado.set(f"Generado {registro.identificador} · semilla {registro.semilla} · hasta {total}")
            elif tipo == "error":
                termino = True
                messagebox.showerror("Error en generación por lotes", str(contenido), parent=self)
            else:
                termino = True
                self.estado.set(f"Lote finalizado: {len(contenido)} escenarios generados")
                self._refrescar_lista()
        if termino:
            self.hilo_lote = None
        elif self.generando_lote:
            self.after(60, self._procesar_lote)

