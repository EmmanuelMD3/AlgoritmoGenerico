"""Vista semanal de los horarios y utilidades independientes de Tk."""
from __future__ import annotations

import os
import tkinter as tk
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from horarios_ga.genetico import Resultado
from horarios_ga.fitness import indices_conflictivos
from horarios_ga.modelo import Problema, Sesion
from horarios_ga.reportes import (
    exportar_horario_csv, exportar_horario_imagen, exportar_horarios_html, hora_final,
)
from .estilos import AZUL, AZUL_CLARO, FONDO, PANEL, PELIGRO, SECUNDARIO


@dataclass(frozen=True)
class EntradaCelda:
    sesion: Sesion
    salon: str
    continuacion: bool
    conflicto: bool


def construir_matriz(
    problema: Problema,
    resultado: Resultado,
    modo: str,
    identificador: str,
) -> dict[tuple[int, int], tuple[EntradaCelda, ...]]:
    """Construye las celdas visibles y marca cualquier restricción dura afectada."""
    if modo not in {"grupo", "docente", "salon"}:
        raise ValueError("Modo de horario no reconocido")
    ocup_doc: Counter[tuple[str, int, int]] = Counter()
    ocup_grupo: Counter[tuple[str, int, int]] = Counter()
    ocup_salon: Counter[tuple[int, int, int]] = Counter()
    sesiones_conflictivas = indices_conflictivos(problema, resultado.cromosoma)
    for sesion, (dia, inicio, salon) in zip(problema.sesiones, resultado.cromosoma):
        for bloque in range(inicio, inicio + sesion.duracion):
            ocup_doc[(sesion.docente, dia, bloque)] += 1
            ocup_grupo[(sesion.grupo, dia, bloque)] += 1
            ocup_salon[(salon, dia, bloque)] += 1

    matriz: dict[tuple[int, int], list[EntradaCelda]] = defaultdict(list)
    for idx, (sesion, (dia, inicio, salon)) in enumerate(zip(problema.sesiones, resultado.cromosoma)):
        salon_id = problema.salones[salon].id
        coincide = (
            (modo == "grupo" and sesion.grupo == identificador)
            or (modo == "docente" and sesion.docente == identificador)
            or (modo == "salon" and salon_id == identificador)
        )
        if not coincide:
            continue
        for bloque in range(inicio, inicio + sesion.duracion):
            conflicto = (
                idx in sesiones_conflictivas
                or
                ocup_doc[(sesion.docente, dia, bloque)] > 1
                or ocup_grupo[(sesion.grupo, dia, bloque)] > 1
                or ocup_salon[(salon, dia, bloque)] > 1
                or (dia, bloque) in problema.docentes[sesion.docente].no_disponible
            )
            matriz[(bloque, dia)].append(EntradaCelda(
                sesion, salon_id, bloque != inicio, conflicto,
            ))
    return {clave: tuple(valor) for clave, valor in matriz.items()}


class VistaHorarios(ttk.Frame):
    def __init__(self, padre: tk.Misc, carpeta_resultados: Path):
        super().__init__(padre, padding=14)
        self.carpeta_resultados = carpeta_resultados
        self.problema: Problema | None = None
        self.resultado: Resultado | None = None
        self.modo = tk.StringVar(value="grupo")
        self.identificador = tk.StringVar()
        self.estado = tk.StringVar(value="Ejecuta el algoritmo para consultar el horario resultante.")

        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 10))
        ttk.Label(barra, text="Consultar por:").pack(side="left")
        selector_modo = ttk.Combobox(
            barra, textvariable=self.modo, values=("grupo", "docente", "salon"),
            state="readonly", width=12,
        )
        selector_modo.pack(side="left", padx=(6, 12))
        selector_modo.bind("<<ComboboxSelected>>", lambda _e: self._actualizar_opciones())
        self.selector = ttk.Combobox(barra, textvariable=self.identificador, state="readonly", width=26)
        self.selector.pack(side="left")
        self.selector.bind("<<ComboboxSelected>>", lambda _e: self.dibujar())
        ttk.Label(barra, textvariable=self.estado).pack(side="left", padx=16)

        acciones = ttk.Frame(self)
        acciones.pack(fill="x", pady=(0, 8))
        ttk.Button(acciones, text="Exportar CSV", command=self._csv).pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="Generar HTML", command=self._html).pack(side="left", padx=6)
        ttk.Button(acciones, text="Exportar imagen", command=self._imagen).pack(side="left", padx=6)
        ttk.Button(acciones, text="Abrir carpeta de resultados", command=self._abrir_carpeta).pack(side="left", padx=6)

        contenedor = ttk.Frame(self, style="Panel.TFrame")
        contenedor.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(contenedor, bg=PANEL, highlightthickness=0)
        sx = ttk.Scrollbar(contenedor, orient="horizontal", command=self.canvas.xview)
        sy = ttk.Scrollbar(contenedor, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        contenedor.rowconfigure(0, weight=1)
        contenedor.columnconfigure(0, weight=1)
        self.tabla = tk.Frame(self.canvas, bg=PANEL)
        self.ventana_tabla = self.canvas.create_window((0, 0), window=self.tabla, anchor="nw")
        self.tabla.bind("<Configure>", self._recalcular_scroll)
        self.canvas.bind("<Configure>", self._ajustar_ancho)

    def establecer_resultado(self, problema: Problema, resultado: Resultado) -> None:
        self.problema, self.resultado = problema, resultado
        self.estado.set(
            f"Horario factible · penalización blanda {resultado.evaluacion.penalizacion_blanda}"
            if resultado.evaluacion.factible
            else f"Horario con {resultado.evaluacion.duras} violación(es) dura(s)"
        )
        self._actualizar_opciones()

    def limpiar(self) -> None:
        self.problema = self.resultado = None
        self.identificador.set("")
        self.estado.set("Ejecuta el algoritmo para consultar el horario resultante.")
        for hijo in self.tabla.winfo_children():
            hijo.destroy()

    def _actualizar_opciones(self) -> None:
        if self.problema is None:
            self.selector["values"] = ()
            return
        if self.modo.get() == "grupo":
            opciones = list(self.problema.grupos)
        elif self.modo.get() == "docente":
            opciones = list(self.problema.docentes)
        else:
            opciones = [s.id for s in self.problema.salones]
        self.selector["values"] = opciones
        if self.identificador.get() not in opciones:
            self.identificador.set(opciones[0] if opciones else "")
        self.dibujar()

    def dibujar(self) -> None:
        for hijo in self.tabla.winfo_children():
            hijo.destroy()
        if not self.problema or not self.resultado or not self.identificador.get():
            return
        matriz = construir_matriz(
            self.problema, self.resultado, self.modo.get(), self.identificador.get(),
        )
        encabezados = ("Hora",) + self.problema.dias
        for col, texto in enumerate(encabezados):
            tk.Label(
                self.tabla, text=texto, bg=AZUL, fg="white", font=("Segoe UI Semibold", 9),
                padx=8, pady=8, borderwidth=1, relief="solid",
            ).grid(row=0, column=col, sticky="nsew")
            self.tabla.columnconfigure(col, minsize=108 if col else 100, weight=1)
        for bloque, hora in enumerate(self.problema.horas):
            fin = hora_final(self.problema, bloque, 1)
            tk.Label(
                self.tabla, text=f"{hora}\n{fin}", bg=FONDO, fg=AZUL,
                font=("Segoe UI Semibold", 8), padx=5, pady=8, relief="solid", borderwidth=1,
            ).grid(row=bloque + 1, column=0, sticky="nsew")
            for dia in range(len(self.problema.dias)):
                entradas = matriz.get((bloque, dia), ())
                textos = []
                for entrada in entradas:
                    sufijo = " · continuación" if entrada.continuacion else ""
                    textos.append(
                        f"{entrada.sesion.materia}\n"
                        f"{self.problema.docentes[entrada.sesion.docente].nombre}\n"
                        f"{entrada.salon}{sufijo}"
                    )
                hay_conflicto = any(e.conflicto for e in entradas)
                tk.Label(
                    self.tabla, text="\n————\n".join(textos), justify="left", anchor="nw",
                    bg="#fee4e2" if hay_conflicto else (AZUL_CLARO if entradas else PANEL),
                    fg=PELIGRO if hay_conflicto else "#17202a", padx=7, pady=7,
                    wraplength=150, relief="solid", borderwidth=1,
                ).grid(row=bloque + 1, column=dia + 1, sticky="nsew")
            self.tabla.rowconfigure(bloque + 1, minsize=72, weight=1)

    def _recalcular_scroll(self, _evento=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _ajustar_ancho(self, evento) -> None:
        requerido = self.tabla.winfo_reqwidth()
        self.canvas.itemconfigure(self.ventana_tabla, width=max(evento.width, requerido))

    def _comprobar(self) -> bool:
        if not self.problema or not self.resultado:
            messagebox.showinfo("Sin resultados", "Primero ejecuta el algoritmo.", parent=self)
            return False
        return True

    def _csv(self) -> None:
        if not self._comprobar():
            return
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar horario", defaultextension=".csv",
            initialdir=self.carpeta_resultados, initialfile="horario_sesiones.csv",
            filetypes=[("Archivo CSV", "*.csv")],
        )
        if ruta:
            exportar_horario_csv(self.problema, self.resultado, ruta)
            messagebox.showinfo("Exportación completa", f"Se guardó:\n{ruta}", parent=self)

    def _html(self) -> None:
        if not self._comprobar():
            return
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Generar HTML", defaultextension=".html",
            initialdir=self.carpeta_resultados, initialfile="horarios_por_grupo.html",
            filetypes=[("Página HTML", "*.html")],
        )
        if ruta:
            exportar_horarios_html(self.problema, self.resultado, ruta)
            messagebox.showinfo("Exportación completa", f"Se guardó:\n{ruta}", parent=self)

    def _imagen(self) -> None:
        if not self._comprobar():
            return
        nombre = f"horario_{self.modo.get()}_{self.identificador.get()}.png".replace(" ", "_")
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar imagen", defaultextension=".png",
            initialdir=self.carpeta_resultados, initialfile=nombre,
            filetypes=[("Imagen PNG", "*.png")],
        )
        if ruta:
            try:
                exportar_horario_imagen(
                    self.problema, self.resultado, ruta, self.modo.get(), self.identificador.get(),
                )
            except ImportError:
                messagebox.showerror("Matplotlib no disponible", "Instala las dependencias de requirements.txt.", parent=self)
                return
            messagebox.showinfo("Exportación completa", f"Se guardó:\n{ruta}", parent=self)

    def _abrir_carpeta(self) -> None:
        self.carpeta_resultados.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(self.carpeta_resultados)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("No se pudo abrir la carpeta", str(exc), parent=self)
