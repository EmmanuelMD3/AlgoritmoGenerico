"""Administración visual de los datos académicos compatibles con el JSON original."""
from __future__ import annotations

import json
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from horarios_ga.datos import cargar_datos, guardar_datos, problema_desde_datos


SECCIONES = ("clases", "docentes", "grupos", "salones", "configuracion")
CONFIG_FILAS = (
    ("dias", "Días lectivos"),
    ("horas", "Bloques horarios"),
    ("duracion_bloque_minutos", "Duración de bloque (minutos)"),
    ("franjas_no_lectivas", "Franjas no lectivas"),
    ("max_horas_consecutivas_grupo", "Máximo consecutivo global por grupo"),
    ("max_horas_consecutivas_docente", "Máximo consecutivo global por docente"),
    ("umbral_jornada_larga", "Umbral de jornada larga"),
)


class ModeloDatosAcademicos:
    """Estado editable y validado, separado de los widgets para poder probarlo."""

    def __init__(self, ruta_ejemplo: Path):
        self.ruta_ejemplo = Path(ruta_ejemplo)
        self.ruta_actual = self.ruta_ejemplo
        self.datos = cargar_datos(self.ruta_ejemplo)
        problema_desde_datos(self.datos)
        self.modificado = False

    def cargar(self, ruta: str | Path) -> None:
        nuevos = cargar_datos(ruta)
        problema_desde_datos(nuevos)
        self.datos = nuevos
        self.ruta_actual = Path(ruta)
        self.modificado = False

    def restaurar(self) -> None:
        self.cargar(self.ruta_ejemplo)

    def guardar(self, ruta: str | Path) -> Path:
        destino = guardar_datos(self.datos, ruta)
        self.ruta_actual = destino
        self.modificado = False
        return destino

    def validar(self):
        return problema_desde_datos(self.datos)

    def reemplazar(self, nuevos: dict[str, Any]) -> None:
        problema_desde_datos(nuevos)
        self.datos = deepcopy(nuevos)
        self.modificado = True

    def adoptar(
        self, nuevos: dict[str, Any], *, ruta: str | Path | None = None,
        modificado: bool = True,
    ) -> None:
        """Sustituye el escenario compartido conservando una política explícita de ruta."""
        problema_desde_datos(nuevos)
        self.datos = deepcopy(nuevos)
        self.ruta_actual = Path(ruta) if ruta is not None else self.ruta_ejemplo
        self.modificado = modificado

    @property
    def nombre_escenario(self) -> str:
        return str(
            self.datos.get("metadatos", {}).get("nombre")
            or self.datos.get("descripcion")
            or self.ruta_actual.stem
        )

    def eliminar(self, seccion: str, indice: int) -> None:
        if seccion not in {"clases", "docentes", "grupos", "salones"}:
            raise ValueError("Esta sección no admite eliminación")
        nuevos = deepcopy(self.datos)
        registro = nuevos[seccion][indice]
        identificador = str(registro["id"])
        if seccion == "docentes" and any(str(c["docente"]) == identificador for c in nuevos["clases"]):
            raise ValueError("No se puede eliminar: hay clases asignadas a este docente")
        if seccion == "grupos" and any(str(c["grupo"]) == identificador for c in nuevos["clases"]):
            raise ValueError("No se puede eliminar: hay clases asignadas a este grupo")
        if seccion == "salones":
            tipo = str(registro.get("tipo", "aula"))
            restantes = nuevos["salones"][:indice] + nuevos["salones"][indice + 1:]
            clases_tipo = [c for c in nuevos["clases"] if str(c.get("tipo_salon", "aula")) == tipo]
            if clases_tipo and not any(str(s.get("tipo", "aula")) == tipo for s in restantes):
                raise ValueError("No se puede eliminar el último salón compatible con clases de este tipo")
        del nuevos[seccion][indice]
        self.reemplazar(nuevos)


def _texto_disponibilidad(valor: dict[str, list[str]] | None) -> str:
    if not valor:
        return ""
    return "; ".join(f"{dia}={','.join(horas)}" for dia, horas in valor.items())


def _parsear_disponibilidad(texto: str) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    if not texto.strip():
        return resultado
    for segmento in texto.split(";"):
        if "=" not in segmento:
            raise ValueError("Usa el formato Día=07:00,08:00; Otro día=13:00")
        dia, horas = segmento.split("=", 1)
        dia = dia.strip()
        if not dia:
            raise ValueError("Falta el nombre de un día en la indisponibilidad")
        resultado[dia] = [hora.strip() for hora in horas.split(",") if hora.strip()]
    return resultado


class DialogoRegistro(tk.Toplevel):
    def __init__(
        self,
        padre: tk.Misc,
        titulo: str,
        campos: list[tuple[str, str, str, tuple[str, ...] | None]],
        inicial: dict[str, Any] | None = None,
    ):
        super().__init__(padre)
        self.title(titulo)
        self.resizable(False, False)
        self.transient(padre)
        self.grab_set()
        self.resultado: dict[str, str] | None = None
        self.variables: dict[str, tk.StringVar] = {}
        marco = ttk.Frame(self, padding=18)
        marco.pack(fill="both", expand=True)
        for fila, (clave, etiqueta, ayuda, opciones) in enumerate(campos):
            ttk.Label(marco, text=etiqueta).grid(row=fila * 2, column=0, sticky="w", pady=(4, 0))
            valor = "" if inicial is None else str(inicial.get(clave, ""))
            var = tk.StringVar(value=valor)
            self.variables[clave] = var
            if opciones is not None:
                control = ttk.Combobox(marco, textvariable=var, values=opciones, width=42)
            else:
                control = ttk.Entry(marco, textvariable=var, width=45)
            control.grid(row=fila * 2, column=1, sticky="ew", padx=(12, 0), pady=(4, 0))
            ttk.Label(marco, text=ayuda, style="Ayuda.TLabel").grid(
                row=fila * 2 + 1, column=1, sticky="w", padx=(12, 0), pady=(0, 3),
            )
        botones = ttk.Frame(marco)
        botones.grid(row=len(campos) * 2, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left", padx=5)
        ttk.Button(botones, text="Aceptar", style="Accent.TButton", command=self._aceptar).pack(side="left", padx=5)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._aceptar())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        x = padre.winfo_rootx() + max(0, (padre.winfo_width() - self.winfo_reqwidth()) // 2)
        y = padre.winfo_rooty() + max(0, (padre.winfo_height() - self.winfo_reqheight()) // 2)
        self.geometry(f"+{x}+{y}")

    def _aceptar(self) -> None:
        self.resultado = {clave: var.get().strip() for clave, var in self.variables.items()}
        self.destroy()


class DialogoDisponibilidad(tk.Toplevel):
    """Cuadrícula accesible para disponibilidad y preferencias semanales."""

    COLORES = {
        "disponible": ("Disponible", "#e8f5ee", "#1f7a4d"),
        "no_disponible": ("No disponible", "#fdecea", "#a93226"),
        "preferido": ("Preferido", "#eaf2f8", "#1f6f8b"),
    }

    def __init__(
        self, padre: tk.Misc, dias: list[str], horas: list[str],
        no_disponible: dict[str, list[str]] | None = None,
        preferidos: dict[str, list[str]] | None = None,
        *, permite_preferidos: bool = True,
        fuentes: dict[str, tuple[dict[str, list[str]], dict[str, list[str]]]] | None = None,
    ):
        super().__init__(padre)
        self.title("Disponibilidad semanal")
        self.transient(padre)
        self.grab_set()
        self.resultado: tuple[dict[str, list[str]], dict[str, list[str]]] | None = None
        self.dias, self.horas = list(dias), list(horas)
        self.permite_preferidos = permite_preferidos
        no_disp = {(d, h) for d, lista in (no_disponible or {}).items() for h in lista}
        prefer = {(d, h) for d, lista in (preferidos or {}).items() for h in lista}
        self.estados: dict[tuple[str, str], str] = {}
        self.botones: dict[tuple[str, str], tk.Button] = {}
        marco = ttk.Frame(self, padding=12)
        marco.pack(fill="both", expand=True)
        ttk.Label(
            marco, text="Selecciona cada bloque: Disponible · No disponible · Preferido",
            style="Ayuda.TLabel",
        ).grid(row=0, column=0, columnspan=len(self.dias) + 1, sticky="w", pady=(0, 8))
        ttk.Label(marco, text="Hora", style="Campo.TLabel").grid(row=1, column=0, padx=2, pady=2)
        for columna, dia in enumerate(self.dias, start=1):
            ttk.Label(marco, text=dia, style="Campo.TLabel").grid(row=1, column=columna, padx=2, pady=2)
        for fila, hora in enumerate(self.horas, start=2):
            ttk.Label(marco, text=hora).grid(row=fila, column=0, sticky="e", padx=4)
            for columna, dia in enumerate(self.dias, start=1):
                estado = "no_disponible" if (dia, hora) in no_disp else ("preferido" if (dia, hora) in prefer else "disponible")
                self.estados[(dia, hora)] = estado
                boton = tk.Button(
                    marco, width=13, relief="solid", borderwidth=1,
                    command=lambda d=dia, h=hora: self._alternar(d, h),
                )
                boton.grid(row=fila, column=columna, sticky="nsew", padx=1, pady=1)
                self.botones[(dia, hora)] = boton
                self._pintar(dia, hora)
        acciones = ttk.Frame(marco)
        acciones.grid(row=len(self.horas) + 2, column=0, columnspan=len(self.dias) + 1, sticky="ew", pady=(9, 0))
        ttk.Button(acciones, text="Disponible todo", command=lambda: self._todos("disponible")).pack(side="left", padx=2)
        ttk.Button(acciones, text="No disponible todo", command=lambda: self._todos("no_disponible")).pack(side="left", padx=2)
        ttk.Button(acciones, text="Copiar primer día a todos", command=self._copiar_primer_dia).pack(side="left", padx=2)
        if fuentes:
            self.fuentes = fuentes
            self.fuente = tk.StringVar(value=next(iter(fuentes)))
            ttk.Combobox(acciones, textvariable=self.fuente, values=tuple(fuentes), state="readonly", width=16).pack(side="left", padx=(10, 2))
            ttk.Button(acciones, text="Copiar de entidad", command=self._copiar_fuente).pack(side="left", padx=2)
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(side="right", padx=3)
        ttk.Button(acciones, text="Guardar cambios", style="Accent.TButton", command=self._guardar).pack(side="right", padx=3)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.resizable(True, True)

    def _alternar(self, dia: str, hora: str) -> None:
        orden = ("disponible", "no_disponible", "preferido") if self.permite_preferidos else ("disponible", "no_disponible")
        actual = self.estados[(dia, hora)]
        self.estados[(dia, hora)] = orden[(orden.index(actual) + 1) % len(orden)]
        self._pintar(dia, hora)

    def _pintar(self, dia: str, hora: str) -> None:
        texto, fondo, frente = self.COLORES[self.estados[(dia, hora)]]
        self.botones[(dia, hora)].configure(text=texto, bg=fondo, fg=frente, activebackground=fondo)

    def _todos(self, estado: str) -> None:
        for clave in self.estados:
            self.estados[clave] = estado
            self._pintar(*clave)

    def _copiar_primer_dia(self) -> None:
        origen = self.dias[0]
        for dia in self.dias[1:]:
            for hora in self.horas:
                self.estados[(dia, hora)] = self.estados[(origen, hora)]
                self._pintar(dia, hora)

    def _copiar_fuente(self) -> None:
        no_disp, preferidos = self.fuentes[self.fuente.get()]
        conjunto_no = {(d, h) for d, lista in no_disp.items() for h in lista}
        conjunto_pref = {(d, h) for d, lista in preferidos.items() for h in lista}
        for dia, hora in self.estados:
            self.estados[(dia, hora)] = "no_disponible" if (dia, hora) in conjunto_no else ("preferido" if self.permite_preferidos and (dia, hora) in conjunto_pref else "disponible")
            self._pintar(dia, hora)

    def _guardar(self) -> None:
        no_disp: dict[str, list[str]] = {}
        preferidos: dict[str, list[str]] = {}
        for (dia, hora), estado in self.estados.items():
            if estado == "no_disponible":
                no_disp.setdefault(dia, []).append(hora)
            elif estado == "preferido":
                preferidos.setdefault(dia, []).append(hora)
        self.resultado = (no_disp, preferidos)
        self.destroy()


class VistaDatosAcademicos(ttk.Frame):
    def __init__(
        self,
        padre: tk.Misc,
        modelo: ModeloDatosAcademicos,
        al_cambiar: Callable[[], None],
    ):
        super().__init__(padre, padding=14)
        self.modelo = modelo
        self.al_cambiar = al_cambiar
        self.ruta = tk.StringVar()
        self.resumen = tk.StringVar()
        self.arboles: dict[str, ttk.Treeview] = {}

        superior = ttk.Frame(self)
        superior.pack(fill="x", pady=(0, 10))
        ttk.Button(superior, text="Cargar archivo JSON", command=self._cargar).pack(side="left", padx=(0, 6))
        ttk.Button(superior, text="Guardar datos en JSON", command=self._guardar).pack(side="left", padx=6)
        ttk.Button(superior, text="Restaurar datos de ejemplo", command=self._restaurar).pack(side="left", padx=6)
        ttk.Button(superior, text="Validar conjunto de datos", style="Accent.TButton", command=self._validar).pack(side="left", padx=6)
        ttk.Label(superior, textvariable=self.resumen).pack(side="right")
        ttk.Label(self, textvariable=self.ruta, style="Ayuda.TLabel").pack(fill="x", pady=(0, 8))

        self.subtabs = ttk.Notebook(self)
        self.subtabs.pack(fill="both", expand=True)
        definiciones = {
            "clases": (("id", "ID", 85), ("materia", "Materia", 170), ("grupo", "Grupo", 95),
                        ("docente", "Docente", 90), ("sesiones_semana", "Sesiones", 75),
                        ("duracion_bloques", "Duración", 75), ("tipo_salon", "Tipo de salón", 105),
                        ("periodos_permitidos", "Periodos permitidos", 260)),
            "docentes": (("id", "ID", 75), ("nombre", "Nombre", 160), ("materias", "Materias relacionadas", 190),
                          ("no_disponible", "No disponible", 260), ("preferidos", "Horarios preferidos", 260),
                          ("max_horas_consecutivas", "Máx. consecutivas", 110)),
            "grupos": (("id", "ID", 100), ("nombre", "Nombre", 140), ("materias", "Materias asignadas", 190), ("alumnos", "Estudiantes", 100),
                       ("no_disponible", "No disponible", 300), ("max_horas_consecutivas", "Máx. consecutivas", 120)),
            "salones": (("id", "ID", 110), ("nombre", "Nombre", 160), ("capacidad", "Capacidad", 120), ("tipo", "Tipo de salón", 180)),
            "configuracion": (("elemento", "Elemento", 200), ("valor", "Valor", 600)),
        }
        etiquetas = {
            "clases": "Materias y clases", "docentes": "Docentes", "grupos": "Grupos",
            "salones": "Salones", "configuracion": "Configuración académica",
        }
        for seccion in SECCIONES:
            pagina = ttk.Frame(self.subtabs, padding=8)
            self.subtabs.add(pagina, text=etiquetas[seccion])
            columnas = [c[0] for c in definiciones[seccion]]
            arbol = ttk.Treeview(pagina, columns=columnas, show="headings", selectmode="browse")
            for clave, etiqueta, ancho in definiciones[seccion]:
                arbol.heading(clave, text=etiqueta)
                arbol.column(clave, width=ancho, minwidth=70, stretch=True)
            sy = ttk.Scrollbar(pagina, orient="vertical", command=arbol.yview)
            sx = ttk.Scrollbar(pagina, orient="horizontal", command=arbol.xview)
            arbol.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
            arbol.grid(row=0, column=0, sticky="nsew")
            sy.grid(row=0, column=1, sticky="ns")
            sx.grid(row=1, column=0, sticky="ew")
            pagina.rowconfigure(0, weight=1)
            pagina.columnconfigure(0, weight=1)
            arbol.bind("<Double-1>", lambda _e: self._editar())
            self.arboles[seccion] = arbol

        inferior = ttk.Frame(self)
        inferior.pack(fill="x", pady=(9, 0))
        ttk.Button(inferior, text="Crear registro", command=self._crear).pack(side="left", padx=(0, 6))
        ttk.Button(inferior, text="Editar seleccionado", command=self._editar).pack(side="left", padx=6)
        ttk.Button(inferior, text="Duplicar", command=self._duplicar).pack(side="left", padx=6)
        ttk.Button(inferior, text="Disponibilidad visual", command=self._disponibilidad_visual).pack(side="left", padx=6)
        ttk.Button(inferior, text="Eliminar seleccionado", style="Danger.TButton", command=self._eliminar).pack(side="left", padx=6)
        ttk.Label(
            inferior,
            text="Los cambios se validan antes de aplicarse; las referencias nunca se modifican automáticamente.",
            style="Ayuda.TLabel",
        ).pack(side="right")
        self.refrescar()

    def _seccion(self) -> str:
        return SECCIONES[self.subtabs.index("current")]

    def refrescar(self) -> None:
        datos = self.modelo.datos
        for seccion, arbol in self.arboles.items():
            arbol.delete(*arbol.get_children())
            if seccion == "clases":
                for i, c in enumerate(datos[seccion]):
                    arbol.insert("", "end", iid=str(i), values=(
                        c["id"], c["materia"], c["grupo"], c["docente"],
                        c.get("sesiones_semana", 1), c.get("duracion_bloques", 1), c.get("tipo_salon", "aula"),
                        _texto_disponibilidad(c.get("periodos_permitidos", {})),
                    ))
            elif seccion == "docentes":
                for i, d in enumerate(datos[seccion]):
                    materias = sorted({c["materia"] for c in datos["clases"] if c["docente"] == d["id"]})
                    arbol.insert("", "end", iid=str(i), values=(
                        d["id"], d["nombre"], ", ".join(materias), _texto_disponibilidad(d.get("no_disponible", {})),
                        _texto_disponibilidad(d.get("preferidos", {})), d.get("max_horas_consecutivas", ""),
                    ))
            elif seccion == "grupos":
                for i, g in enumerate(datos[seccion]):
                    materias = sorted({c["materia"] for c in datos["clases"] if c["grupo"] == g["id"]})
                    arbol.insert("", "end", iid=str(i), values=(
                        g["id"], g.get("nombre", g["id"]), ", ".join(materias), g["alumnos"], _texto_disponibilidad(g.get("no_disponible", {})),
                        g.get("max_horas_consecutivas", ""),
                    ))
            elif seccion == "salones":
                for i, s in enumerate(datos[seccion]):
                    arbol.insert("", "end", iid=str(i), values=(s["id"], s.get("nombre", s["id"]), s["capacidad"], s.get("tipo", "aula")))
            else:
                restricciones = datos.get("restricciones", {})
                valores = {
                    "dias": ", ".join(datos["dias"]),
                    "horas": ", ".join(datos["horas"]),
                    "duracion_bloque_minutos": datos.get("metadatos", {}).get("duracion_bloque_minutos", 60),
                    "franjas_no_lectivas": _texto_disponibilidad(restricciones.get("franjas_no_lectivas", {})),
                    "max_horas_consecutivas_grupo": restricciones.get("max_horas_consecutivas_grupo") or "",
                    "max_horas_consecutivas_docente": restricciones.get("max_horas_consecutivas_docente") or "",
                    "umbral_jornada_larga": restricciones.get("umbral_jornada_larga", 6),
                }
                for i, (clave, etiqueta) in enumerate(CONFIG_FILAS):
                    arbol.insert("", "end", iid=str(i), values=(etiqueta, valores[clave]))
        marca = " · cambios sin guardar" if self.modelo.modificado else ""
        self.ruta.set(f"Archivo actual: {self.modelo.ruta_actual}{marca}")
        self.resumen.set(
            f"{len(datos['clases'])} clases · {len(datos['docentes'])} docentes · "
            f"{len(datos['grupos'])} grupos · {len(datos['salones'])} salones"
        )

    def _cargar(self) -> None:
        ruta = filedialog.askopenfilename(
            parent=self, title="Cargar datos académicos", filetypes=[("Archivos JSON", "*.json"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        if self.modelo.modificado and not messagebox.askyesno(
            "Descartar cambios", "Hay cambios sin guardar. ¿Deseas descartarlos?", parent=self,
        ):
            return
        try:
            self.modelo.cargar(ruta)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Datos no válidos", str(exc), parent=self)
            return
        self.refrescar()
        self.al_cambiar()

    def _guardar(self) -> None:
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Guardar datos académicos", defaultextension=".json",
            initialdir=self.modelo.ruta_actual.parent, initialfile=self.modelo.ruta_actual.name,
            filetypes=[("Archivos JSON", "*.json")],
        )
        if not ruta:
            return
        try:
            self.modelo.guardar(ruta)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            return
        self.refrescar()
        messagebox.showinfo("Datos guardados", f"El archivo se guardó correctamente:\n{ruta}", parent=self)

    def _restaurar(self) -> None:
        if not messagebox.askyesno(
            "Restaurar ejemplo", "Se reemplazarán los datos editados por el conjunto de ejemplo. ¿Continuar?", parent=self,
        ):
            return
        try:
            self.modelo.restaurar()
        except (OSError, ValueError) as exc:
            messagebox.showerror("No se pudo restaurar", str(exc), parent=self)
            return
        self.refrescar()
        self.al_cambiar()

    def _validar(self) -> None:
        try:
            problema = self.modelo.validar()
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Conjunto no válido", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Datos válidos",
            f"El conjunto es consistente.\n\n"
            f"Sesiones generadas: {len(problema.sesiones)}\n"
            f"Cada clase dispone de al menos un salón compatible.",
            parent=self,
        )

    def _campos(self, seccion: str):
        datos = self.modelo.datos
        if seccion == "clases":
            return [
                ("id", "Identificador", "Debe ser único.", None),
                ("materia", "Nombre de la materia", "Nombre mostrado en el horario.", None),
                ("grupo", "Grupo", "Debe existir en la pestaña Grupos.", tuple(g["id"] for g in datos["grupos"])),
                ("docente", "Docente", "Debe existir en la pestaña Docentes.", tuple(d["id"] for d in datos["docentes"])),
                ("sesiones_semana", "Sesiones por semana", "Número entero positivo.", None),
                ("duracion_bloques", "Duración en bloques", "Número entero positivo.", None),
                ("tipo_salon", "Tipo de salón", "Debe coincidir con al menos un salón compatible.", tuple(sorted({s.get("tipo", "aula") for s in datos["salones"]}))),
                ("periodos_permitidos", "Periodos permitidos", "Opcional. Ejemplo: Lunes=07:00,08:00; Martes=10:00", None),
            ]
        if seccion == "docentes":
            return [
                ("id", "Identificador", "Debe ser único.", None),
                ("nombre", "Nombre", "Nombre completo del docente.", None),
                ("no_disponible", "No disponible", "Ejemplo: Lunes=07:00,08:00; Viernes=13:00", None),
                ("preferidos", "Horarios preferidos", "Opcional; salir de estas franjas recibe penalización blanda.", None),
                ("max_horas_consecutivas", "Máximo de horas consecutivas", "Opcional; vacío desactiva el límite individual.", None),
            ]
        if seccion == "grupos":
            return [
                ("id", "Identificador", "Debe ser único.", None),
                ("nombre", "Nombre", "Nombre descriptivo opcional.", None),
                ("alumnos", "Número de estudiantes", "Número entero positivo.", None),
                ("no_disponible", "No disponible", "Opcional. Ejemplo: Lunes=07:00,08:00", None),
                ("max_horas_consecutivas", "Máximo de horas consecutivas", "Opcional; vacío usa el límite global.", None),
            ]
        if seccion == "salones":
            return [
                ("id", "Identificador", "Debe ser único.", None),
                ("nombre", "Nombre", "Nombre descriptivo del espacio.", None),
                ("capacidad", "Capacidad", "Número entero positivo.", None),
                ("tipo", "Tipo de salón", "Ejemplo: aula o laboratorio.", None),
            ]
        return []

    def _crear(self) -> None:
        seccion = self._seccion()
        if seccion == "configuracion":
            messagebox.showinfo("Configuración académica", "Selecciona una restricción y pulsa Editar.", parent=self)
            return
        dialogo = DialogoRegistro(self, "Crear registro", self._campos(seccion))
        self.wait_window(dialogo)
        if dialogo.resultado is not None:
            self._aplicar_registro(seccion, None, dialogo.resultado)

    def _indice_seleccionado(self, seccion: str) -> int | None:
        seleccion = self.arboles[seccion].selection()
        if not seleccion:
            messagebox.showinfo("Selecciona un registro", "Selecciona primero el registro que deseas usar.", parent=self)
            return None
        return int(seleccion[0])

    def _editar(self) -> None:
        seccion = self._seccion()
        indice = self._indice_seleccionado(seccion)
        if indice is None:
            return
        if seccion == "configuracion":
            clave = CONFIG_FILAS[indice][0]
            restricciones = self.modelo.datos.get("restricciones", {})
            if clave in {"dias", "horas"}:
                valor_inicial = ", ".join(self.modelo.datos[clave])
                ayuda = "Valores separados por comas. Las horas deben ser bloques HH:MM consecutivos."
            elif clave == "franjas_no_lectivas":
                valor_inicial = _texto_disponibilidad(restricciones.get(clave, {}))
                ayuda = "Formato Día=hora,hora; otro día=hora. Vacío desactiva las franjas."
            elif clave == "duracion_bloque_minutos":
                valor_inicial = str(self.modelo.datos.get("metadatos", {}).get(clave, 60))
                ayuda = "Duración real entre inicios consecutivos; debe coincidir con la lista de horas."
            else:
                bruto = restricciones.get(clave, "")
                valor_inicial = "" if bruto is None else str(bruto)
                ayuda = "Entero positivo. Usa vacío para desactivar un máximo global."
            inicial = {"valor": valor_inicial}
            dialogo = DialogoRegistro(
                self, "Editar configuración académica",
                [("valor", CONFIG_FILAS[indice][1], ayuda, None)],
                inicial,
            )
            self.wait_window(dialogo)
            if dialogo.resultado is not None:
                try:
                    nuevos = deepcopy(self.modelo.datos)
                    valor = dialogo.resultado["valor"].strip()
                    if clave in {"dias", "horas"}:
                        nuevos[clave] = [v.strip() for v in valor.split(",") if v.strip()]
                    elif clave == "duracion_bloque_minutos":
                        nuevos.setdefault("metadatos", {})[clave] = int(valor)
                    else:
                        nuevos.setdefault("restricciones", {})
                        if clave == "franjas_no_lectivas":
                            nuevos["restricciones"][clave] = _parsear_disponibilidad(valor)
                        elif clave == "umbral_jornada_larga":
                            nuevos["restricciones"][clave] = int(valor)
                        elif valor:
                            nuevos["restricciones"][clave] = int(valor)
                        else:
                            nuevos["restricciones"].pop(clave, None)
                except ValueError as exc:
                    messagebox.showerror("Valor no válido", str(exc), parent=self)
                    return
                self._reemplazar_seguro(nuevos)
            return
        registro = deepcopy(self.modelo.datos[seccion][indice])
        if seccion == "docentes":
            registro["no_disponible"] = _texto_disponibilidad(registro.get("no_disponible", {}))
            registro["preferidos"] = _texto_disponibilidad(registro.get("preferidos", {}))
            registro["max_horas_consecutivas"] = registro.get("max_horas_consecutivas") or ""
        elif seccion == "grupos":
            registro["no_disponible"] = _texto_disponibilidad(registro.get("no_disponible", {}))
            registro["max_horas_consecutivas"] = registro.get("max_horas_consecutivas") or ""
        elif seccion == "clases":
            registro["periodos_permitidos"] = _texto_disponibilidad(registro.get("periodos_permitidos", {}))
        dialogo = DialogoRegistro(self, "Editar registro", self._campos(seccion), registro)
        self.wait_window(dialogo)
        if dialogo.resultado is not None:
            self._aplicar_registro(seccion, indice, dialogo.resultado)

    def _aplicar_registro(self, seccion: str, indice: int | None, valores: dict[str, str]) -> None:
        try:
            if seccion == "clases":
                registro = {
                    "id": valores["id"], "materia": valores["materia"], "grupo": valores["grupo"],
                    "docente": valores["docente"], "sesiones_semana": int(valores["sesiones_semana"]),
                    "duracion_bloques": int(valores["duracion_bloques"]), "tipo_salon": valores["tipo_salon"],
                }
                if valores["periodos_permitidos"]:
                    registro["periodos_permitidos"] = _parsear_disponibilidad(valores["periodos_permitidos"])
            elif seccion == "docentes":
                registro = {
                    "id": valores["id"], "nombre": valores["nombre"],
                    "no_disponible": _parsear_disponibilidad(valores["no_disponible"]),
                    "preferidos": _parsear_disponibilidad(valores["preferidos"]),
                }
                if valores["max_horas_consecutivas"]:
                    registro["max_horas_consecutivas"] = int(valores["max_horas_consecutivas"])
            elif seccion == "grupos":
                registro = {
                    "id": valores["id"], "nombre": valores.get("nombre") or valores["id"], "alumnos": int(valores["alumnos"]),
                    "no_disponible": _parsear_disponibilidad(valores["no_disponible"]),
                }
                if valores["max_horas_consecutivas"]:
                    registro["max_horas_consecutivas"] = int(valores["max_horas_consecutivas"])
            else:
                registro = {"id": valores["id"], "nombre": valores.get("nombre") or valores["id"], "capacidad": int(valores["capacidad"]), "tipo": valores["tipo"]}
        except ValueError as exc:
            messagebox.showerror("Valores no válidos", str(exc), parent=self)
            return
        nuevos = deepcopy(self.modelo.datos)
        if indice is None:
            nuevos[seccion].append(registro)
        else:
            anterior = str(nuevos[seccion][indice]["id"])
            if registro["id"] != anterior and seccion in {"docentes", "grupos"}:
                referencia = "docente" if seccion == "docentes" else "grupo"
                if any(str(c[referencia]) == anterior for c in nuevos["clases"]):
                    messagebox.showerror(
                        "Identificador en uso",
                        "No se puede cambiar este identificador mientras haya clases que lo referencien. "
                        "Edita primero esas clases.", parent=self,
                    )
                    return
            nuevos[seccion][indice] = registro
        self._reemplazar_seguro(nuevos)

    def _reemplazar_seguro(self, nuevos: dict[str, Any]) -> None:
        try:
            self.modelo.reemplazar(nuevos)
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Cambio no válido", str(exc), parent=self)
            return
        self.refrescar()
        self.al_cambiar()

    def _duplicar(self) -> None:
        seccion = self._seccion()
        if seccion == "configuracion":
            messagebox.showinfo("Duplicación", "La configuración institucional no se duplica.", parent=self)
            return
        indice = self._indice_seleccionado(seccion)
        if indice is None:
            return
        nuevos = deepcopy(self.modelo.datos)
        copia = deepcopy(nuevos[seccion][indice])
        base = str(copia["id"]) + "_COPIA"
        existentes = {str(r["id"]) for r in nuevos[seccion]}
        candidato, numero = base, 2
        while candidato in existentes:
            candidato, numero = f"{base}{numero}", numero + 1
        copia["id"] = candidato
        if "nombre" in copia:
            copia["nombre"] = str(copia["nombre"]) + " (copia)"
        nuevos[seccion].append(copia)
        self._reemplazar_seguro(nuevos)

    def _disponibilidad_visual(self) -> None:
        seccion = self._seccion()
        indice = self._indice_seleccionado(seccion)
        if indice is None:
            return
        datos = self.modelo.datos
        if seccion == "configuracion":
            clave = CONFIG_FILAS[indice][0]
            if clave != "franjas_no_lectivas":
                messagebox.showinfo(
                    "Cuadrícula no aplicable",
                    "Selecciona la fila Franjas no lectivas para editarla visualmente.", parent=self,
                )
                return
            actual = datos.get("restricciones", {}).get("franjas_no_lectivas", {})
            dialogo = DialogoDisponibilidad(
                self, datos["dias"], datos["horas"], actual, permite_preferidos=False,
            )
            self.wait_window(dialogo)
            if dialogo.resultado is not None:
                nuevos = deepcopy(datos)
                nuevos.setdefault("restricciones", {})["franjas_no_lectivas"] = dialogo.resultado[0]
                self._reemplazar_seguro(nuevos)
            return
        if seccion not in {"docentes", "grupos"}:
            messagebox.showinfo(
                "Cuadrícula no aplicable",
                "La disponibilidad visual corresponde a docentes, grupos y franjas no lectivas.", parent=self,
            )
            return
        registro = datos[seccion][indice]
        fuentes = {
            str(otro["id"]): (
                deepcopy(otro.get("no_disponible", {})),
                deepcopy(otro.get("preferidos", {})),
            )
            for otro in datos[seccion] if otro is not registro
        }
        dialogo = DialogoDisponibilidad(
            self, datos["dias"], datos["horas"],
            registro.get("no_disponible", {}), registro.get("preferidos", {}),
            permite_preferidos=seccion == "docentes", fuentes=fuentes or None,
        )
        self.wait_window(dialogo)
        if dialogo.resultado is None:
            return
        nuevos = deepcopy(datos)
        nuevos[seccion][indice]["no_disponible"] = dialogo.resultado[0]
        if seccion == "docentes":
            nuevos[seccion][indice]["preferidos"] = dialogo.resultado[1]
        self._reemplazar_seguro(nuevos)

    def _eliminar(self) -> None:
        seccion = self._seccion()
        if seccion == "configuracion":
            messagebox.showinfo("Operación no disponible", "Los días y bloques pueden editarse, pero no eliminarse como sección.", parent=self)
            return
        indice = self._indice_seleccionado(seccion)
        if indice is None or not messagebox.askyesno(
            "Eliminar registro", "¿Deseas eliminar el registro seleccionado?", parent=self,
        ):
            return
        try:
            self.modelo.eliminar(seccion, indice)
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se puede eliminar", str(exc), parent=self)
            return
        self.refrescar()
        self.al_cambiar()
