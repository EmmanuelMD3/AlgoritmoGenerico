"""Tabla y gráfica del historial evolutivo real."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from horarios_ga.genetico import Resultado
from horarios_ga.reportes import exportar_historial_csv
from .estilos import AZUL_MEDIO, PANEL, PELIGRO


class VistaHistorial(ttk.Frame):
    def __init__(self, padre: tk.Misc, carpeta_resultados: Path):
        super().__init__(padre, padding=14)
        self.carpeta_resultados = carpeta_resultados
        self.resultado: Resultado | None = None
        barra = ttk.Frame(self)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Historial evolutivo", style="Titulo.TLabel").pack(side="left")
        ttk.Button(barra, text="Exportar historial a CSV", command=self._exportar).pack(side="right")

        paneles = ttk.Panedwindow(self, orient="vertical")
        paneles.pack(fill="both", expand=True)
        superior = ttk.Frame(paneles, style="Panel.TFrame")
        inferior = ttk.Frame(paneles, style="Panel.TFrame")
        paneles.add(superior, weight=1)
        paneles.add(inferior, weight=1)

        columnas = ("generacion", "mejor", "promedio", "conflictos", "blandas", "huecos", "diversidad", "factible")
        self.tabla = ttk.Treeview(superior, columns=columnas, show="headings")
        cabeceras = (
            ("generacion", "Generación", 90), ("mejor", "Mejor fitness", 120),
            ("promedio", "Fitness promedio", 130), ("conflictos", "Conflictos críticos", 130),
            ("blandas", "Penalización blanda", 125), ("huecos", "Huecos", 75),
            ("diversidad", "Diversidad", 85), ("factible", "Factibilidad", 100),
        )
        for clave, texto, ancho in cabeceras:
            self.tabla.heading(clave, text=texto)
            self.tabla.column(clave, width=ancho, anchor="center", stretch=True)
        sy = ttk.Scrollbar(superior, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=sy.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.tabla.tag_configure("factible", foreground="#18794e")
        self.tabla.tag_configure("conflicto", foreground=PELIGRO)
        self._crear_grafica(inferior)

    def _crear_grafica(self, padre: tk.Misc) -> None:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            self.figura = self.canvas_grafica = None
            ttk.Label(padre, text="Instala Matplotlib para visualizar las gráficas.").pack()
            return
        self.figura = Figure(figsize=(8, 3), dpi=100, facecolor=PANEL)
        self.eje = self.figura.add_subplot(111)
        self.figura.subplots_adjust(left=.08, right=.96, bottom=.19, top=.86)
        self.canvas_grafica = FigureCanvasTkAgg(self.figura, master=padre)
        self.canvas_grafica.get_tk_widget().pack(fill="both", expand=True)
        self._dibujar()

    def establecer_resultado(self, resultado: Resultado) -> None:
        self.resultado = resultado
        self.tabla.delete(*self.tabla.get_children())
        for registro in resultado.historial:
            self.tabla.insert("", "end", values=(
                registro.generacion, registro.mejor_fitness, f"{registro.media_fitness:.2f}",
                registro.conflictos_duros, registro.penalizacion_blanda, registro.huecos,
                f"{registro.diversidad:.1%}", "Sí" if registro.factible else "No",
            ), tags=("factible" if registro.factible else "conflicto",))
        self._dibujar()

    def limpiar(self) -> None:
        self.resultado = None
        self.tabla.delete(*self.tabla.get_children())
        self._dibujar()

    def _dibujar(self) -> None:
        if self.figura is None:
            return
        self.eje.clear()
        if self.resultado:
            xs = [r.generacion for r in self.resultado.historial]
            self.eje.plot(xs, [r.mejor_fitness for r in self.resultado.historial], color=AZUL_MEDIO, label="Mejor fitness")
            self.eje.plot(xs, [r.media_fitness for r in self.resultado.historial], color="#7c8ea3", label="Fitness promedio")
            self.eje.legend(fontsize=8, loc="best")
        self.eje.set(title="Fitness por generación", xlabel="Generación", ylabel="Fitness")
        self.eje.grid(alpha=.22)
        self.canvas_grafica.draw_idle()

    def _exportar(self) -> None:
        if self.resultado is None:
            messagebox.showinfo("Sin historial", "Primero ejecuta el algoritmo.", parent=self)
            return
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar historial", defaultextension=".csv",
            initialdir=self.carpeta_resultados, initialfile="evolucion.csv",
            filetypes=[("Archivo CSV", "*.csv")],
        )
        if ruta:
            exportar_historial_csv(self.resultado, ruta)
            messagebox.showinfo("Historial exportado", f"Se guardó:\n{ruta}", parent=self)
