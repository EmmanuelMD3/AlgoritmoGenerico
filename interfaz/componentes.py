"""Componentes visuales reutilizables del dashboard académico."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .estilos import ADVERTENCIA, AZUL, EXITO, PANEL, PELIGRO, SECUNDARIO, TEXTO


TONOS = {
    "neutral": (AZUL, "#eaf2f8"),
    "success": (EXITO, "#e8f5ee"),
    "danger": (PELIGRO, "#fdecea"),
    "warning": (ADVERTENCIA, "#fff4d6"),
}


class SeccionPlegable(ttk.Frame):
    """Sección compacta con encabezado accesible y contenido plegable."""

    def __init__(self, padre: tk.Misc, titulo: str, expandida: bool = True):
        super().__init__(padre, style="Panel.TFrame")
        self.titulo = titulo
        self.expandida = expandida
        self.boton = tk.Button(
            self, command=self.alternar, anchor="w", relief="flat", borderwidth=0,
            padx=8, pady=6, bg="#edf2f7", fg=AZUL,
            activebackground="#e2e8f0", activeforeground=AZUL,
            font=("Segoe UI Semibold", 9), cursor="hand2",
        )
        self.boton.pack(fill="x")
        self.contenido = ttk.Frame(self, style="Panel.TFrame", padding=(8, 5, 8, 8))
        self._sincronizar()

    def alternar(self) -> None:
        self.expandida = not self.expandida
        self._sincronizar()

    def _sincronizar(self) -> None:
        self.boton.configure(text=f"{'▾' if self.expandida else '▸'}  {self.titulo}")
        if self.expandida:
            self.contenido.pack(fill="x")
        else:
            self.contenido.pack_forget()


class TarjetaKPI(tk.Frame):
    """Tarjeta KPI con valor principal, contexto y color semántico discreto."""

    def __init__(self, padre: tk.Misc, titulo: str):
        super().__init__(
            padre, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1,
            bd=0, padx=10, pady=8,
        )
        self.acento = tk.Frame(self, bg=AZUL, width=4)
        self.acento.pack(side="left", fill="y", padx=(0, 9))
        contenido = tk.Frame(self, bg=PANEL)
        contenido.pack(side="left", fill="both", expand=True)
        tk.Label(
            contenido, text=titulo, bg=PANEL, fg=SECUNDARIO,
            font=("Segoe UI", 8), anchor="w",
        ).pack(fill="x")
        self.valor = tk.Label(
            contenido, text="—", bg=PANEL, fg=TEXTO,
            font=("Segoe UI Semibold", 15), anchor="w",
        )
        self.valor.pack(fill="x", pady=(1, 0))
        self.detalle = tk.Label(
            contenido, text="Sin datos", bg=PANEL, fg=SECUNDARIO,
            font=("Segoe UI", 7), anchor="w", justify="left",
        )
        self.detalle.pack(fill="x")

    def establecer(self, valor: str, detalle: str, tono: str = "neutral") -> None:
        color, _fondo = TONOS.get(tono, TONOS["neutral"])
        self.acento.configure(bg=color)
        self.valor.configure(text=valor, fg=color if tono != "neutral" else TEXTO)
        self.detalle.configure(text=detalle)

    def limpiar(self) -> None:
        self.establecer("—", "Sin datos", "neutral")


class PanelDesplazable(ttk.Frame):
    """Canvas vertical que reajusta el ancho interior sin tocar otros paneles."""

    def __init__(self, padre: tk.Misc, ancho: int = 310):
        super().__init__(padre, style="Panel.TFrame")
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0, width=ancho)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interior = ttk.Frame(self.canvas, style="Panel.TFrame")
        self.ventana = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=barra.set)
        self.interior.bind(
            "<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self.ventana, width=e.width),
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
