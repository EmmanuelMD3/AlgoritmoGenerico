"""Paleta y estilos ttk de la aplicación."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


AZUL = "#102a43"
AZUL_MEDIO = "#1f5a94"
AZUL_CLARO = "#dbeafe"
FONDO = "#f3f6fa"
PANEL = "#ffffff"
TEXTO = "#17202a"
SECUNDARIO = "#5d6d7e"
EXITO = "#18794e"
PELIGRO = "#b42318"
ADVERTENCIA = "#9a6700"


def configurar_estilos(raiz: tk.Misc) -> ttk.Style:
    # Respeta la densidad que Windows comunica a Tk, con límites prudentes para
    # evitar controles minúsculos o desproporcionados en configuraciones atípicas.
    try:
        escala = max(1.0, min(2.0, raiz.winfo_fpixels("1i") / 72.0))
        raiz.tk.call("tk", "scaling", escala)
    except tk.TclError:
        pass
    estilo = ttk.Style(raiz)
    disponibles = estilo.theme_names()
    estilo.theme_use("vista" if "vista" in disponibles else "clam")
    raiz.option_add("*Font", ("Segoe UI", 10))
    raiz.configure(bg=FONDO)

    estilo.configure("TFrame", background=FONDO)
    estilo.configure("Panel.TFrame", background=PANEL, relief="flat")
    estilo.configure("Header.TFrame", background=AZUL)
    estilo.configure("Header.TLabel", background=AZUL, foreground="white", font=("Segoe UI Semibold", 20))
    estilo.configure("Subheader.TLabel", background=AZUL, foreground="#c7d9ec", font=("Segoe UI", 10))
    estilo.configure("Titulo.TLabel", background=FONDO, foreground=AZUL, font=("Segoe UI Semibold", 14))
    estilo.configure("PanelTitulo.TLabel", background=PANEL, foreground=AZUL, font=("Segoe UI Semibold", 12))
    estilo.configure("Campo.TLabel", background=PANEL, foreground=TEXTO, font=("Segoe UI Semibold", 9))
    estilo.configure("Ayuda.TLabel", background=PANEL, foreground=SECUNDARIO, font=("Segoe UI", 8))
    estilo.configure("Valor.TLabel", background=PANEL, foreground=TEXTO, font=("Segoe UI Semibold", 11))
    estilo.configure("Exito.TLabel", background=PANEL, foreground=EXITO, font=("Segoe UI Semibold", 11))
    estilo.configure("Peligro.TLabel", background=PANEL, foreground=PELIGRO, font=("Segoe UI Semibold", 11))
    estilo.configure("TNotebook", background=FONDO, borderwidth=0)
    estilo.configure("TNotebook.Tab", padding=(15, 8), font=("Segoe UI Semibold", 9))
    estilo.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", AZUL)])
    # El tema nativo de Windows ignora el color de fondo de botones personalizados;
    # usar texto azul mantiene el contraste tanto en ``vista`` como en ``clam``.
    estilo.configure("Accent.TButton", background=AZUL_MEDIO, foreground=AZUL, padding=(12, 7), font=("Segoe UI Semibold", 9))
    estilo.map(
        "Accent.TButton",
        background=[("active", "#dbeafe"), ("disabled", "#e4e7eb")],
        foreground=[("disabled", "#829ab1")],
    )
    estilo.configure("Danger.TButton", foreground=PELIGRO, padding=(10, 7))
    estilo.configure("Treeview", rowheight=27, fieldbackground=PANEL, background=PANEL)
    estilo.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), foreground=AZUL)
    estilo.configure("Horizontal.TProgressbar", troughcolor="#dfe7ef", background=AZUL_MEDIO)
    estilo.configure("TRadiobutton", background=PANEL, foreground=TEXTO, font=("Segoe UI", 8))
    return estilo

