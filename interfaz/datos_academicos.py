"""Modelo canónico y editor visual de la configuración académica activa."""
from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from horarios_ga.constructor_escenarios import (
    DIAS_BASE, generar_horas, validar_escenario_detallado,
)
from horarios_ga.datos import (
    ConflictoArchivoExterno, cargar_datos, guardar_datos_atomico, huella_archivo,
    problema_desde_datos,
)
from horarios_ga.importacion import VistaPreviaImportacion, preparar_importacion
from .estilos import AZUL, EXITO, PANEL, PELIGRO, SECUNDARIO, TEXTO


RUTA_CANONICA_NOMBRE = "configuracion_academica.json"
CATEGORIAS = (
    ("general", "General"), ("docentes", "Docentes"), ("grupos", "Grupos"),
    ("clases", "Materias y sesiones"), ("salones", "Salones"),
    ("disponibilidad", "Disponibilidad"),
    ("resumen", "Resumen y validación"),
)


def contar_preferencias_docentes(datos: dict[str, Any]) -> int:
    """Cuenta bloques preferidos heredados sin alterar el documento."""
    total = 0
    for docente in datos.get("docentes", []):
        mapa = docente.get("preferidos", {})
        if isinstance(mapa, dict):
            total += sum(len(horas) for horas in mapa.values() if isinstance(horas, list))
    return total


def desactivar_preferencias_docentes(datos: dict[str, Any]) -> dict[str, Any]:
    """Desactiva su efecto futuro conservando íntegros los mapas históricos."""
    nuevos = deepcopy(datos)
    nuevos.setdefault("restricciones", {})["preferencias_docentes_activas"] = False
    return nuevos


def aplicar_disponibilidad_entidad(
    datos: dict[str, Any], ambito: str, identificador: str,
    no_disponible: dict[str, list[str]],
) -> dict[str, Any]:
    """Devuelve una copia modificando sólo ``no_disponible`` de una entidad."""
    seccion = {"Docente": "docentes", "Grupo": "grupos"}.get(ambito)
    if seccion is None:
        raise ValueError("La disponibilidad individual sólo admite Docente o Grupo")
    nuevos = deepcopy(datos)
    registro = next(
        (x for x in nuevos[seccion] if str(x.get("id")) == str(identificador)),
        None,
    )
    if registro is None:
        raise ValueError(f"No existe {ambito.lower()} con identificador {identificador}")
    registro["no_disponible"] = deepcopy(no_disponible)
    return nuevos


def calcular_horas_disponibles(
    estado: "EstadoCuadriculaSemanal", duracion_bloque_minutos: int,
) -> float:
    """Convierte los bloques disponibles a horas reales, incluso con 30 minutos."""
    bloques = sum(valor == "disponible" for valor in estado.estados.values())
    return bloques * int(duracion_bloque_minutos) / 60


def fusionar_cambios_pendientes(base: Any, local: Any, externo: Any) -> Any:
    """Fusión de tres vías: conserva cambios externos y borradores locales.

    Cuando ambos lados cambian exactamente el mismo valor, el borrador local se
    mantiene sólo en memoria y continúa marcado como pendiente. Las listas de
    entidades se concilian por ``id`` para no perder altas ajenas.
    """
    if local == base:
        return deepcopy(externo)
    if externo == base:
        return deepcopy(local)
    if isinstance(base, dict) and isinstance(local, dict) and isinstance(externo, dict):
        resultado: dict[str, Any] = {}
        for clave in base.keys() | local.keys() | externo.keys():
            if clave not in local:
                if clave in externo:
                    resultado[clave] = deepcopy(externo[clave])
                continue
            if clave not in externo:
                resultado[clave] = deepcopy(local[clave])
                continue
            resultado[clave] = fusionar_cambios_pendientes(
                base.get(clave), local[clave], externo[clave],
            )
        return resultado
    if (
        isinstance(base, list) and isinstance(local, list) and isinstance(externo, list)
        and all(isinstance(x, dict) and "id" in x for x in base + local + externo)
    ):
        por_base = {str(x["id"]): x for x in base}
        por_local = {str(x["id"]): x for x in local}
        por_externo = {str(x["id"]): x for x in externo}
        orden = [str(x["id"]) for x in externo]
        orden.extend(str(x["id"]) for x in local if str(x["id"]) not in por_externo)
        return [
            fusionar_cambios_pendientes(
                por_base.get(identificador), por_local[identificador], por_externo[identificador],
            )
            if identificador in por_local and identificador in por_externo
            else deepcopy(
                por_local[identificador]
                if identificador in por_local else por_externo[identificador]
            )
            for identificador in orden
            if identificador in por_local or identificador in por_externo
        ]
    return deepcopy(local)


class ModeloDatosAcademicos:
    """Única instantánea editable compartida por todas las vistas.

    Con ``ruta_canonica`` sólo se carga y guarda ese archivo. Si aún no existe,
    el ejemplo sirve exclusivamente como plantilla pendiente de guardar. El modo
    sin ruta canónica se mantiene para pruebas y compatibilidad interna.
    """

    def __init__(self, ruta_ejemplo: Path, ruta_canonica: Path | None = None):
        self.ruta_ejemplo = Path(ruta_ejemplo)
        self._estricto = ruta_canonica is not None
        self.ruta_canonica = Path(ruta_canonica or ruta_ejemplo)
        self.ruta_actual = self.ruta_canonica
        self._huella_disco: str | None = None
        self._datos_guardados: dict[str, Any] = {}
        self.migracion_preferencias_pendiente = 0
        self.creado_desde_plantilla = False
        if self.ruta_canonica.exists():
            self._cargar_desde(self.ruta_canonica, modificado=False)
        else:
            self.datos = cargar_datos(self.ruta_ejemplo)
            problema_desde_datos(self.datos)
            self._datos_guardados = deepcopy(self.datos)
            self.modificado = True
            self.creado_desde_plantilla = True

    @property
    def huella_disco(self) -> str | None:
        return self._huella_disco

    @property
    def estado_guardado(self) -> str:
        if not self.ruta_canonica.exists():
            return "Configuración nueva · pendiente de guardar"
        return "Cambios pendientes" if self.modificado else "Guardado"

    def _cargar_desde(self, ruta: Path, *, modificado: bool) -> None:
        nuevos = cargar_datos(ruta)
        problema_desde_datos(nuevos)
        self.datos = nuevos
        self._datos_guardados = deepcopy(nuevos)
        self.ruta_actual = self.ruta_canonica if self._estricto else ruta
        self._huella_disco = huella_archivo(ruta)
        self.modificado = modificado
        self.migracion_preferencias_pendiente = 0
        self.creado_desde_plantilla = False

    def cargar(self, ruta: str | Path) -> None:
        destino = Path(ruta)
        if self._estricto and destino.resolve() != self.ruta_canonica.resolve():
            raise ValueError(f"La aplicación sólo utiliza {self.ruta_canonica.name}")
        self._cargar_desde(destino, modificado=False)

    def descartar(self) -> None:
        if self.ruta_canonica.exists():
            self._cargar_desde(self.ruta_canonica, modificado=False)
        else:
            self.datos = cargar_datos(self.ruta_ejemplo)
            problema_desde_datos(self.datos)
            self._datos_guardados = deepcopy(self.datos)
            self._huella_disco = None
            self.modificado = True
            self.creado_desde_plantilla = True

    def restaurar(self) -> None:
        self.descartar() if self._estricto else self.cargar(self.ruta_ejemplo)

    def guardar(self, ruta: str | Path | None = None) -> Path:
        destino = Path(ruta) if ruta is not None else self.ruta_canonica
        if self._estricto and destino.resolve() != self.ruta_canonica.resolve():
            raise ValueError(f"Sólo se puede guardar en {self.ruta_canonica}")
        destino, huella = guardar_datos_atomico(
            self.datos, destino, huella_esperada=self._huella_disco,
            comprobar_cambio=self._estricto,
        )
        self.ruta_actual = destino
        if self._estricto or destino.resolve() == self.ruta_canonica.resolve():
            self._huella_disco = huella
        self._datos_guardados = deepcopy(self.datos)
        self.modificado = False
        self.creado_desde_plantilla = False
        self.migracion_preferencias_pendiente = 0
        return destino

    def preparar_disponibilidad_binaria(self) -> int:
        """Desactiva en memoria preferencias activas que ya no edita la UI 7.2.

        Los mapas originales permanecen en ``docentes[].preferidos``. El cambio
        sólo se persiste al usar uno de los botones de guardado.
        """
        cantidad = contar_preferencias_docentes(self.datos)
        activas = self.datos.get("restricciones", {}).get(
            "preferencias_docentes_activas", True,
        )
        if cantidad and activas:
            self.datos = desactivar_preferencias_docentes(self.datos)
            self.migracion_preferencias_pendiente = cantidad
            self.modificado = True
        return self.migracion_preferencias_pendiente

    def guardar_disponibilidad(
        self, ambito: str, identificador: str,
        no_disponible: dict[str, list[str]], *, resolver_conflicto: bool = False,
    ) -> Path:
        """Persiste una sola disponibilidad sin guardar otros borradores.

        Si se solicita resolver un conflicto, se parte de la versión externa
        más reciente y sólo se sustituye el campo de la entidad confirmada.
        """
        base_anterior = deepcopy(self._datos_guardados)
        if not self._estricto:
            base_disco = deepcopy(self._datos_guardados)
            huella_esperada = self._huella_disco
        elif resolver_conflicto and self.ruta_canonica.exists():
            base_disco = cargar_datos(self.ruta_canonica)
            huella_esperada = huella_archivo(self.ruta_canonica)
        else:
            base_disco = deepcopy(self._datos_guardados)
            huella_esperada = self._huella_disco

        candidato = aplicar_disponibilidad_entidad(
            base_disco, ambito, identificador, no_disponible,
        )
        if self.migracion_preferencias_pendiente:
            candidato = desactivar_preferencias_docentes(candidato)
        problema_desde_datos(candidato)
        destino, huella = guardar_datos_atomico(
            candidato, self.ruta_canonica,
            huella_esperada=huella_esperada,
            comprobar_cambio=self._estricto,
        )

        memoria = fusionar_cambios_pendientes(
            base_anterior, self.datos, candidato,
        )
        memoria = aplicar_disponibilidad_entidad(
            memoria, ambito, identificador, no_disponible,
        )
        if self.migracion_preferencias_pendiente:
            memoria = desactivar_preferencias_docentes(memoria)
        self.datos = memoria
        self._datos_guardados = deepcopy(candidato)
        self._huella_disco = huella
        self.ruta_actual = destino
        self.creado_desde_plantilla = False
        self.migracion_preferencias_pendiente = 0
        self.modificado = self.datos != self._datos_guardados
        return destino

    def importar_configuracion(
        self, nuevos: dict[str, Any], *, resolver_conflicto: bool = False,
    ) -> Path:
        """Reemplaza transaccionalmente el único JSON activo y después la memoria."""
        candidato = deepcopy(nuevos)
        if (
            contar_preferencias_docentes(candidato)
            and candidato.get("restricciones", {}).get(
                "preferencias_docentes_activas", True,
            )
        ):
            candidato = desactivar_preferencias_docentes(candidato)
        problema_desde_datos(candidato)
        huella_esperada = (
            huella_archivo(self.ruta_canonica)
            if resolver_conflicto else self._huella_disco
        )
        destino, huella = guardar_datos_atomico(
            candidato, self.ruta_canonica,
            huella_esperada=huella_esperada,
            comprobar_cambio=self._estricto,
        )
        # La memoria sólo cambia después de que el reemplazo terminó.
        self.datos = deepcopy(candidato)
        self._datos_guardados = deepcopy(candidato)
        self._huella_disco = huella
        self.ruta_actual = destino
        self.modificado = False
        self.creado_desde_plantilla = False
        self.migracion_preferencias_pendiente = 0
        return destino

    def validar(self):
        return problema_desde_datos(self.datos)

    def instantanea(self) -> dict[str, Any]:
        """Copia validada para una ejecución; nunca cambia con ediciones posteriores."""
        self.validar()
        return deepcopy(self.datos)

    def reemplazar(self, nuevos: dict[str, Any]) -> None:
        problema_desde_datos(nuevos)
        self.datos = deepcopy(nuevos)
        self.modificado = self.datos != self._datos_guardados

    def adoptar(
        self, nuevos: dict[str, Any], *, ruta: str | Path | None = None,
        modificado: bool = True,
    ) -> None:
        problema_desde_datos(nuevos)
        if self._estricto and ruta is not None and Path(ruta).resolve() != self.ruta_canonica.resolve():
            raise ValueError("No se puede adoptar otra ruta en el modelo canónico")
        self.datos = deepcopy(nuevos)
        self.ruta_actual = self.ruta_canonica if self._estricto else Path(ruta or self.ruta_ejemplo)
        if not modificado:
            self._datos_guardados = deepcopy(self.datos)
        self.modificado = modificado

    @property
    def nombre_escenario(self) -> str:
        return str(self.datos.get("metadatos", {}).get("nombre") or self.datos.get("descripcion") or self.ruta_actual.stem)

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
            if any(str(c.get("tipo_salon", "aula")) == tipo for c in nuevos["clases"]) and not any(str(s.get("tipo", "aula")) == tipo for s in restantes):
                raise ValueError("No se puede eliminar el último salón compatible con clases de este tipo")
        del nuevos[seccion][indice]
        self.reemplazar(nuevos)


@dataclass(frozen=True)
class AfectacionTemporal:
    bloques_eliminados: int
    referencias_eliminadas: int
    mapas_afectados: int


def migrar_estructura_temporal(
    datos: dict[str, Any], dias: list[str], horas: list[str], duracion_bloque: int,
) -> tuple[dict[str, Any], AfectacionTemporal]:
    """Adapta los mapas semanales al calendario y cuantifica el impacto."""
    if not dias:
        raise ValueError("Selecciona al menos un día lectivo")
    if any(int(c.get("duracion_bloques", 1)) > len(horas) for c in datos["clases"]):
        raise ValueError("Una sesión multibloque no cabe en la nueva jornada")
    nuevos = deepcopy(datos)
    anteriores = {(d, h) for d in datos["dias"] for h in datos["horas"]}
    posteriores = {(d, h) for d in dias for h in horas}
    referencias = 0
    mapas = 0

    def podar(mapa: Any) -> dict[str, list[str]]:
        nonlocal referencias, mapas
        resultado: dict[str, list[str]] = {}
        removidas = 0
        for dia, lista in mapa.items() if isinstance(mapa, dict) else ():
            for hora in lista if isinstance(lista, list) else ():
                if (dia, hora) in posteriores:
                    resultado.setdefault(dia, []).append(hora)
                else:
                    removidas += 1
        if removidas:
            mapas += 1
            referencias += removidas
        return resultado

    for docente in nuevos["docentes"]:
        for clave in ("no_disponible", "preferidos"):
            if clave in docente:
                docente[clave] = podar(docente[clave])
    for grupo in nuevos["grupos"]:
        if "no_disponible" in grupo:
            grupo["no_disponible"] = podar(grupo["no_disponible"])
    for clase in nuevos["clases"]:
        if "periodos_permitidos" in clase and clase["periodos_permitidos"] is not None:
            clase["periodos_permitidos"] = podar(clase["periodos_permitidos"])
    restricciones = nuevos.setdefault("restricciones", {})
    restricciones["franjas_no_lectivas"] = podar(restricciones.get("franjas_no_lectivas", {}))
    nuevos["dias"] = list(dias)
    nuevos["horas"] = list(horas)
    nuevos.setdefault("metadatos", {})["duracion_bloque_minutos"] = duracion_bloque
    return nuevos, AfectacionTemporal(len(anteriores - posteriores), referencias, mapas)


class EstadoCuadriculaSemanal:
    """Estado binario reusable y testeable de una cuadrícula semanal."""

    ESTADOS = {"disponible", "no_disponible"}

    def __init__(self, dias: list[str], horas: list[str], permite_preferidos: bool = True):
        self.dias = list(dias)
        self.horas = list(horas)
        # El argumento se conserva para no romper importaciones de Fase 7.1,
        # pero la cuadrícula 7.2 es deliberadamente binaria en todos los casos.
        self.permite_preferidos = False
        self.estados = {(d, h): "disponible" for d in self.dias for h in self.horas}
        self.seleccion: set[tuple[str, str]] = set()

    def cargar(self, no_disponible=None, preferidos=None) -> None:
        self.marcar_todo("disponible")
        for dia, lista in (no_disponible or {}).items():
            for hora in lista:
                if (dia, hora) in self.estados:
                    self.estados[(dia, hora)] = "no_disponible"
        # ``preferidos`` se acepta sólo al leer documentos anteriores. Nunca se
        # convierte en un tercer estado ni altera lo que ve el usuario.
        self.seleccion.clear()

    def cargar_periodos_permitidos(self, mapa: dict[str, list[str]] | None) -> None:
        self.marcar_todo("disponible" if mapa is None else "no_disponible")
        for dia, lista in (mapa or {}).items():
            for hora in lista:
                if (dia, hora) in self.estados:
                    self.estados[(dia, hora)] = "disponible"
        self.seleccion.clear()

    def alternar_seleccion(self, dia: str, hora: str) -> None:
        clave = (dia, hora)
        if clave in self.seleccion:
            self.seleccion.remove(clave)
        elif clave in self.estados:
            self.seleccion.add(clave)

    def seleccionar_dia(self, dia: str) -> None:
        self.seleccion = {(dia, h) for h in self.horas}

    def seleccionar_rango(self, inicio: str, fin: str) -> None:
        a, b = self.horas.index(inicio), self.horas.index(fin)
        if a > b:
            a, b = b, a
        self.seleccion = {(d, h) for d in self.dias for h in self.horas[a:b + 1]}

    def marcar(self, estado: str) -> None:
        if estado not in self.ESTADOS:
            raise ValueError("Estado semanal no permitido")
        for clave in self.seleccion:
            self.estados[clave] = estado

    def marcar_todo(self, estado: str) -> None:
        if estado not in self.ESTADOS:
            raise ValueError("Estado semanal no permitido")
        for clave in self.estados:
            self.estados[clave] = estado

    def alternar_disponibilidad(self, dia: str, hora: str) -> None:
        clave = (dia, hora)
        if clave not in self.estados:
            raise ValueError("Bloque semanal desconocido")
        self.estados[clave] = (
            "no_disponible" if self.estados[clave] == "disponible" else "disponible"
        )

    def marcar_dia(self, dia: str, estado: str) -> None:
        if estado not in self.ESTADOS or dia not in self.dias:
            raise ValueError("Día o estado semanal no permitido")
        for hora in self.horas:
            self.estados[(dia, hora)] = estado

    def alternar_dia(self, dia: str) -> None:
        nuevo = (
            "no_disponible"
            if all(self.estados[(dia, hora)] == "disponible" for hora in self.horas)
            else "disponible"
        )
        self.marcar_dia(dia, nuevo)

    def copiar_dia(self, origen: str, destino: str) -> None:
        for hora in self.horas:
            self.estados[(destino, hora)] = self.estados[(origen, hora)]

    def exportar(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        no_disponible: dict[str, list[str]] = {}
        for (dia, hora), estado in self.estados.items():
            if estado == "no_disponible":
                no_disponible.setdefault(dia, []).append(hora)
        return no_disponible, {}

    def exportar_no_disponible(self) -> dict[str, list[str]]:
        return self.exportar()[0]

    def periodos_permitidos(self) -> dict[str, list[str]] | None:
        permitidos: dict[str, list[str]] = {}
        for (dia, hora), estado in self.estados.items():
            if estado != "no_disponible":
                permitidos.setdefault(dia, []).append(hora)
        return None if sum(map(len, permitidos.values())) == len(self.estados) else permitidos


class EditorSemanal(ttk.Frame):
    COLORES = {
        "disponible": ("✓", "#dcfce7", "#166534"),
        "no_disponible": ("", "#f1f5f9", "#64748b"),
    }

    def __init__(self, padre: tk.Misc, al_cambiar: Callable[[], None] | None = None):
        super().__init__(padre, style="Panel.TFrame")
        self.estado: EstadoCuadriculaSemanal | None = None
        self.botones: dict[tuple[str, str], tk.Button] = {}
        self.al_cambiar = al_cambiar
        controles = ttk.Frame(self, style="Panel.TFrame")
        controles.pack(fill="x", pady=(0, 10))
        ttk.Label(
            controles, text="✓ Disponible", style="Exito.TLabel",
        ).pack(side="left")
        ttk.Label(
            controles, text="   No disponible", style="Ayuda.TLabel",
        ).pack(side="left", padx=(12, 0))
        self.boton_acciones = ttk.Menubutton(controles, text="Acciones  ▾")
        menu = tk.Menu(self.boton_acciones, tearoff=False)
        menu.add_command(label="Marcar todo disponible", command=lambda: self._marcar_todo("disponible"))
        menu.add_command(label="Marcar todo no disponible", command=lambda: self._marcar_todo("no_disponible"))
        self.boton_acciones.configure(menu=menu)
        self.boton_acciones.pack(side="right")
        area = ttk.Frame(self, style="Panel.TFrame")
        area.pack(fill="both", expand=True)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas_matriz = tk.Canvas(
            area, bg=PANEL, highlightthickness=0, borderwidth=0,
        )
        scroll_vertical = ttk.Scrollbar(
            area, orient="vertical", command=self.canvas_matriz.yview,
        )
        scroll_horizontal = ttk.Scrollbar(
            area, orient="horizontal", command=self.canvas_matriz.xview,
        )
        self.canvas_matriz.configure(
            yscrollcommand=scroll_vertical.set,
            xscrollcommand=scroll_horizontal.set,
        )
        self.canvas_matriz.grid(row=0, column=0, sticky="nsew")
        scroll_vertical.grid(row=0, column=1, sticky="ns")
        scroll_horizontal.grid(row=1, column=0, sticky="ew")
        self.matriz = ttk.Frame(self.canvas_matriz, style="Panel.TFrame")
        self.ventana_matriz = self.canvas_matriz.create_window(
            (0, 0), window=self.matriz, anchor="nw",
        )
        self.matriz.bind(
            "<Configure>",
            lambda _e: self.canvas_matriz.configure(
                scrollregion=self.canvas_matriz.bbox("all"),
            ),
        )
        self.canvas_matriz.bind("<Configure>", self._ajustar_ancho_matriz)

    def _ajustar_ancho_matriz(self, evento) -> None:
        """Usa todo el ancho disponible sin impedir el desplazamiento horizontal."""
        self.canvas_matriz.itemconfigure(
            self.ventana_matriz,
            width=max(evento.width, self.matriz.winfo_reqwidth()),
        )

    def cargar(self, estado: EstadoCuadriculaSemanal) -> None:
        self.estado = estado
        for widget in self.matriz.winfo_children():
            widget.destroy()
        self.botones.clear()
        dias, horas = estado.dias, estado.horas
        ttk.Label(self.matriz, text="Bloque", style="Campo.TLabel").grid(row=0, column=0, padx=8, pady=6)
        for columna, dia in enumerate(dias, 1):
            ttk.Button(
                self.matriz, text=f"{dia}\nTodo", command=lambda d=dia: self._alternar_dia(d),
            ).grid(row=0, column=columna, sticky="ew", padx=3, pady=(0, 4))
            self.matriz.columnconfigure(columna, weight=1, minsize=100)
        for fila, hora in enumerate(horas, 1):
            ttk.Label(self.matriz, text=hora, style="Campo.TLabel").grid(row=fila, column=0, padx=8, pady=3)
            for columna, dia in enumerate(dias, 1):
                boton = tk.Button(
                    self.matriz, relief="flat", borderwidth=0, height=2,
                    font=("Segoe UI Semibold", 13), cursor="hand2",
                    command=lambda d=dia, h=hora: self._alternar(d, h),
                )
                boton.grid(row=fila, column=columna, sticky="nsew", padx=3, pady=3)
                self.botones[(dia, hora)] = boton
        self._repintar()

    def _repintar(self) -> None:
        if self.estado is None: return
        for clave, boton in self.botones.items():
            texto, fondo, frente = self.COLORES[self.estado.estados[clave]]
            boton.configure(
                text=texto, bg=fondo, fg=frente, activebackground=fondo,
                activeforeground=frente,
            )

    def _notificar(self) -> None:
        self._repintar()
        if self.al_cambiar is not None:
            self.al_cambiar()

    def _alternar(self, dia, hora):
        self.estado.alternar_disponibilidad(dia, hora)
        self._notificar()

    def _alternar_dia(self, dia):
        self.estado.alternar_dia(dia)
        self._notificar()

    def _marcar_todo(self, estado):
        self.estado.marcar_todo(estado)
        self._notificar()


class DialogoMapaSemanal(tk.Toplevel):
    """Editor semanal enfocado para restricciones fuera de Disponibilidad."""

    def __init__(
        self, padre: tk.Misc, titulo: str, explicacion: str,
        estado: EstadoCuadriculaSemanal,
    ):
        super().__init__(padre)
        self.title(titulo)
        self.geometry("920x620")
        self.minsize(720, 480)
        self.transient(padre.winfo_toplevel())
        self.resultado: EstadoCuadriculaSemanal | None = None
        contenedor = ttk.Frame(self, padding=16)
        contenedor.pack(fill="both", expand=True)
        ttk.Label(contenedor, text=titulo, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            contenedor, text=explicacion, style="Ayuda.TLabel", wraplength=820,
        ).pack(anchor="w", pady=(3, 12))
        self.editor = EditorSemanal(contenedor)
        self.editor.pack(fill="both", expand=True)
        self.editor.cargar(estado)
        acciones = ttk.Frame(contenedor)
        acciones.pack(fill="x", pady=(12, 0))
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            acciones, text="Aplicar", style="Primary.TButton", command=self._aceptar,
        ).pack(side="right", padx=(0, 7))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _aceptar(self) -> None:
        self.resultado = self.editor.estado
        self.destroy()


class DialogoVistaPreviaImportacion(tk.Toplevel):
    """Confirmación explícita de una importación ya leída y validada."""

    def __init__(self, padre: tk.Misc, previa: VistaPreviaImportacion):
        super().__init__(padre)
        self.title("Vista previa del escenario JSON")
        # El pie debe seguir visible con el escalado de texto habitual de Windows.
        self.geometry("780x680")
        self.minsize(680, 620)
        self.transient(padre.winfo_toplevel())
        self.confirmado = False
        contenedor = ttk.Frame(self, padding=18)
        contenedor.pack(fill="both", expand=True)
        ttk.Label(
            contenedor, text="Vista previa del escenario", style="Titulo.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            contenedor, text=previa.ruta.name, style="Ayuda.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        datos = tk.Frame(
            contenedor, bg=PANEL, highlightbackground="#d9e2ec",
            highlightthickness=1, padx=12, pady=10,
        )
        datos.pack(fill="x")
        filas = (
            ("Escenario", previa.nombre),
            ("Docentes / grupos", f"{previa.docentes} / {previa.grupos}"),
            ("Materias / sesiones", f"{previa.materias} / {previa.sesiones}"),
            ("Salones", str(previa.salones)),
            ("Días lectivos", ", ".join(previa.dias) or "Sin días"),
            ("Horario", previa.rango_horario),
            ("Duración del bloque", f"{previa.duracion_bloque_minutos} minutos"),
        )
        for fila, (etiqueta, valor) in enumerate(filas):
            tk.Label(
                datos, text=etiqueta, bg=PANEL, fg=SECUNDARIO,
                font=("Segoe UI Semibold", 9), anchor="w",
            ).grid(row=fila, column=0, sticky="nw", padx=(0, 20), pady=3)
            tk.Label(
                datos, text=valor, bg=PANEL, fg=TEXTO,
                font=("Segoe UI", 9), anchor="w", justify="left", wraplength=500,
            ).grid(row=fila, column=1, sticky="w", pady=3)
        datos.columnconfigure(1, weight=1)

        errores = len(previa.validacion.errores)
        advertencias = len(previa.validacion.advertencias)
        ttk.Label(
            contenedor,
            text=f"Validación · {errores} errores · {advertencias} advertencias",
            style="PanelTitulo.TLabel",
        ).pack(anchor="w", pady=(14, 5))
        tabla = ttk.Treeview(
            contenedor, columns=("nivel", "detalle"), show="headings", height=5,
        )
        tabla.heading("nivel", text="Nivel")
        tabla.heading("detalle", text="Detalle")
        tabla.column("nivel", width=100, minwidth=80)
        tabla.column("detalle", width=570, minwidth=300)
        tabla.tag_configure("error", foreground=PELIGRO)
        tabla.tag_configure("advertencia", foreground="#9a6700")
        tabla.tag_configure("correcto", foreground=EXITO)
        for indice, incidencia in enumerate(previa.validacion.incidencias):
            tabla.insert(
                "", "end", iid=str(indice),
                values=(incidencia.nivel.capitalize(), incidencia.mensaje),
                tags=(incidencia.nivel,),
            )
        tabla.pack(fill="both", expand=True)
        ttk.Label(
            contenedor,
            text=(
                "Una estructura válida permite ejecutar el motor, pero no garantiza "
                "que exista o se encuentre un horario factible."
            ),
            style="Ayuda.TLabel", wraplength=700,
        ).pack(anchor="w", pady=(8, 0))
        acciones = ttk.Frame(contenedor)
        acciones.pack(fill="x", pady=(14, 0))
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(side="right")
        self.boton_importar = ttk.Button(
            acciones, text="Importar y utilizar", style="Primary.TButton",
            command=self._confirmar,
            state="normal" if previa.importable else "disabled",
        )
        self.boton_importar.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _confirmar(self) -> None:
        self.confirmado = True
        self.destroy()


class VistaDatosAcademicos(ttk.Frame):
    """Panel maestro–detalle para la configuración académica activa."""

    CAMPOS = {
        "docentes": (("id", "Identificador", "texto"), ("nombre", "Nombre completo", "texto"), ("max_horas_consecutivas", "Máximo consecutivo", "numero_opcional")),
        "grupos": (("id", "Identificador", "texto"), ("nombre", "Nombre", "texto"), ("alumnos", "Estudiantes", "numero"), ("max_horas_consecutivas", "Máximo consecutivo", "numero_opcional"), ("materias_asignadas", "Materias asignadas", "solo_lectura")),
        "clases": (("id", "Identificador", "texto"), ("materia", "Materia", "texto"), ("grupo", "Grupo", "grupo"), ("docente", "Docente", "docente"), ("sesiones_semana", "Sesiones por semana", "numero"), ("duracion_bloques", "Duración (bloques)", "numero"), ("tipo_salon", "Tipo de salón", "tipo")),
        "salones": (("id", "Identificador", "texto"), ("nombre", "Nombre", "texto"), ("capacidad", "Capacidad", "numero"), ("tipo", "Tipo de salón", "tipo")),
    }

    def __init__(self, padre, modelo, al_cambiar, al_ejecutar=None):
        super().__init__(padre, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.modelo: ModeloDatosAcademicos = modelo
        self.preferencias_migradas = self.modelo.preparar_disponibilidad_binaria()
        self.al_cambiar: Callable[[], None] = al_cambiar
        self.al_ejecutar: Callable[[], None] | None = al_ejecutar
        self.paginas, self.arboles, self.formularios = {}, {}, {}
        self.indice_edicion = {s: None for s in self.CAMPOS}
        self.estado_archivo, self.ruta_texto, self.validacion_texto = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.estado_importacion = tk.StringVar(value="")
        self.kpis: dict[str, tk.StringVar] = {}
        self._categoria_actual = "general"
        self._clave_disponibilidad: tuple[str, str] | None = None
        self._borrador_disponibilidad_original: dict[str, list[str]] = {}
        self._borrador_disponibilidad_sucio = False
        self._cambiando_selector = False
        self._crear_encabezado()
        navegacion = ttk.Frame(self, style="Panel.TFrame", padding=(8, 6))
        navegacion.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.botones_categorias: dict[str, tk.Button] = {}
        for clave, etiqueta in CATEGORIAS:
            boton = tk.Button(
                navegacion, text=etiqueta, relief="flat", borderwidth=0,
                padx=12, pady=7, cursor="hand2", font=("Segoe UI Semibold", 9),
                command=lambda c=clave: self._cambiar_categoria(c),
            )
            boton.pack(side="left", padx=2)
            self.botones_categorias[clave] = boton
        self.contenedor = ttk.Frame(self, style="Panel.TFrame", padding=12)
        self.contenedor.grid(row=2, column=0, sticky="nsew", pady=(7, 8))
        self.contenedor.grid_propagate(False)
        self._crear_general()
        for seccion in ("docentes", "grupos", "clases", "salones"): self._crear_entidades(seccion)
        self._crear_disponibilidad(); self._crear_resumen(); self._crear_barra_acciones(); self.refrescar()

    def _crear_encabezado(self):
        cabecera = ttk.Frame(self); cabecera.grid(row=0, column=0, sticky="ew")
        textos = ttk.Frame(cabecera); textos.pack(side="left", fill="x", expand=True)
        ttk.Label(textos, text="Datos académicos", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(textos, text="Configuración institucional única compartida por optimización, experimentos y evolución", style="Ayuda.TLabel").pack(anchor="w")
        importacion = ttk.Frame(textos)
        importacion.pack(anchor="w", pady=(7, 0))
        ttk.Button(
            importacion, text="Importar escenario JSON", style="Accent.TButton",
            command=self._importar_escenario_json,
        ).pack(side="left")
        ttk.Label(
            importacion, textvariable=self.estado_importacion, style="Ayuda.TLabel",
        ).pack(side="left", padx=(9, 0))
        tarjetas = ttk.Frame(cabecera); tarjetas.pack(side="right")
        for clave, etiqueta in (("docentes", "Docentes"), ("grupos", "Grupos"), ("materias", "Materias"), ("sesiones", "Sesiones"), ("salones", "Salones")):
            marco = tk.Frame(tarjetas, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1, padx=10, pady=5); marco.pack(side="left", padx=3)
            valor = tk.StringVar(value="0"); self.kpis[clave] = valor
            tk.Label(marco, textvariable=valor, bg=PANEL, fg=AZUL, font=("Segoe UI Semibold", 13)).pack()
            tk.Label(marco, text=etiqueta, bg=PANEL, fg=SECUNDARIO, font=("Segoe UI", 8)).pack()

    def _pagina(self, clave):
        pagina = ttk.Frame(self.contenedor, style="Panel.TFrame"); self.paginas[clave] = pagina; return pagina

    def _crear_general(self):
        p = self._pagina("general")
        ttk.Label(p, text="Configuración general", style="PanelTitulo.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(p, text="Los bloques se generan desde inicio, fin y duración; no se capturan listas manuales.", style="Ayuda.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.general = {}
        ttk.Label(p, text="Días lectivos", style="Campo.TLabel").grid(row=2, column=0, sticky="nw", pady=4)
        dias_frame = ttk.Frame(p, style="Panel.TFrame"); dias_frame.grid(row=2, column=1, columnspan=3, sticky="w")
        self.dias_vars = {}
        for dia in DIAS_BASE:
            var = tk.BooleanVar(); self.dias_vars[dia] = var; ttk.Checkbutton(dias_frame, text=dia, variable=var).pack(side="left", padx=(0, 8))
        horas_posibles, actual, limite = [], datetime.strptime("06:00", "%H:%M"), datetime.strptime("23:45", "%H:%M")
        while actual <= limite: horas_posibles.append(actual.strftime("%H:%M")); actual += timedelta(minutes=15)
        for fila, (clave, etiqueta, valores) in enumerate((("hora_inicio", "Inicio de jornada", horas_posibles), ("hora_fin", "Fin de jornada", horas_posibles), ("duracion", "Duración del bloque", ("15", "30", "45", "60", "90", "120"))), 3):
            ttk.Label(p, text=etiqueta, style="Campo.TLabel").grid(row=fila, column=0, sticky="w", pady=5)
            var = tk.StringVar(); self.general[clave] = var; ttk.Combobox(p, textvariable=var, values=valores, state="readonly", width=16).grid(row=fila, column=1, sticky="w", padx=(8, 25))
        self.bloques_calculados = tk.StringVar(); ttk.Label(p, textvariable=self.bloques_calculados, style="Ayuda.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 10))
        for var in (self.general["hora_inicio"], self.general["hora_fin"], self.general["duracion"]): var.trace_add("write", lambda *_: self._calcular_bloques())
        for fila, (clave, etiqueta) in enumerate((("nombre", "Nombre de la configuración"), ("descripcion", "Descripción"), ("max_grupo", "Máximo consecutivo por grupo"), ("max_docente", "Máximo consecutivo por docente"), ("umbral", "Umbral de jornada larga")), 3):
            ttk.Label(p, text=etiqueta, style="Campo.TLabel").grid(row=fila, column=2, sticky="w", pady=5)
            var = tk.StringVar(); self.general[clave] = var
            if clave in {"max_grupo", "max_docente", "umbral"}:
                control = ttk.Spinbox(
                    p, textvariable=var, from_=0 if clave != "umbral" else 1,
                    to=100, increment=1, width=26,
                )
            else:
                control = ttk.Entry(p, textvariable=var, width=28)
            control.grid(row=fila, column=3, sticky="ew", padx=(8, 0))
        acciones_general = ttk.Frame(p, style="Panel.TFrame")
        acciones_general.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(14, 8))
        ttk.Button(
            acciones_general, text="Previsualizar y aplicar calendario",
            style="Primary.TButton", command=self._aplicar_general,
        ).pack(side="left")
        ttk.Button(
            acciones_general, text="Franjas institucionales no lectivas",
            command=self._editar_franjas_no_lectivas,
        ).pack(side="left", padx=7)
        self.resumen_franjas = tk.StringVar(value="0 bloques no lectivos")
        ttk.Label(
            acciones_general, textvariable=self.resumen_franjas, style="Ayuda.TLabel",
        ).pack(side="left", padx=5)
        ttk.Label(p, text="Bloques calculados", style="Campo.TLabel").grid(row=10, column=0, columnspan=4, sticky="w")
        self.tabla_bloques = ttk.Treeview(p, columns=("numero", "inicio", "fin"), show="headings", height=7)
        for clave, etiqueta, ancho in (("numero", "Bloque", 80), ("inicio", "Inicio", 130), ("fin", "Fin", 130)):
            self.tabla_bloques.heading(clave, text=etiqueta)
            self.tabla_bloques.column(clave, width=ancho, anchor="center")
        scroll_bloques = ttk.Scrollbar(p, orient="vertical", command=self.tabla_bloques.yview)
        self.tabla_bloques.configure(yscrollcommand=scroll_bloques.set)
        self.tabla_bloques.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=(4, 0))
        scroll_bloques.grid(row=11, column=4, sticky="ns", pady=(4, 0))
        p.columnconfigure(3, weight=1); p.rowconfigure(11, weight=1)

    def _crear_entidades(self, seccion):
        p = self._pagina(seccion); titulos = {"docentes":"Docentes", "grupos":"Grupos", "clases":"Materias y sesiones", "salones":"Salones"}
        ttk.Label(p, text=titulos[seccion], style="PanelTitulo.TLabel").pack(anchor="w")
        ttk.Label(p, text="Selecciona un registro para editarlo en el panel derecho.", style="Ayuda.TLabel").pack(anchor="w", pady=(0, 8))
        panel = ttk.Panedwindow(p, orient="horizontal"); panel.pack(fill="both", expand=True)
        lista, formulario = ttk.Frame(panel, style="Panel.TFrame"), ttk.Frame(panel, style="Panel.TFrame", padding=(12, 4)); panel.add(lista, weight=2); panel.add(formulario, weight=1)
        columnas = tuple(c for c, _e, _t in self.CAMPOS[seccion]); arbol = ttk.Treeview(lista, columns=columnas, show="headings", selectmode="browse")
        for clave, etiqueta, _tipo in self.CAMPOS[seccion]: arbol.heading(clave, text=etiqueta); arbol.column(clave, width=110, minwidth=70)
        scroll = ttk.Scrollbar(lista, orient="vertical", command=arbol.yview)
        scroll_horizontal = ttk.Scrollbar(lista, orient="horizontal", command=arbol.xview)
        arbol.configure(yscrollcommand=scroll.set, xscrollcommand=scroll_horizontal.set)
        lista.rowconfigure(0, weight=1); lista.columnconfigure(0, weight=1)
        arbol.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        scroll_horizontal.grid(row=1, column=0, sticky="ew")
        arbol.bind("<<TreeviewSelect>>", lambda _e, s=seccion: self._cargar_formulario(s)); self.arboles[seccion] = arbol
        ttk.Label(formulario, text="Editor", style="PanelTitulo.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        variables = {}; self.formularios[seccion] = variables; self.controles_formulario = getattr(self, "controles_formulario", {}); self.controles_formulario[seccion] = {}
        for fila, (clave, etiqueta, tipo) in enumerate(self.CAMPOS[seccion], 1):
            ttk.Label(formulario, text=etiqueta, style="Campo.TLabel").grid(row=fila, column=0, sticky="w", pady=4); var = tk.StringVar(); variables[clave] = var
            if tipo in {"grupo", "docente", "tipo"}:
                control = ttk.Combobox(formulario, textvariable=var, state="readonly")
            elif tipo in {"numero", "numero_opcional"}:
                control = ttk.Spinbox(
                    formulario, textvariable=var,
                    from_=0 if tipo == "numero_opcional" else 1,
                    to=10000, increment=1,
                )
            else:
                control = ttk.Entry(
                    formulario, textvariable=var,
                    state="readonly" if tipo == "solo_lectura" else "normal",
                )
            control.grid(row=fila, column=1, sticky="ew", padx=(8, 0), pady=4); self.controles_formulario[seccion][clave] = control
        acciones = ttk.Frame(formulario, style="Panel.TFrame"); acciones.grid(row=len(self.CAMPOS[seccion])+1, column=0, columnspan=2, sticky="ew", pady=(12,0))
        ttk.Button(acciones, text="Nuevo", command=lambda s=seccion:self._nuevo(s)).pack(side="left", padx=2)
        ttk.Button(acciones, text="Aplicar", style="Accent.TButton", command=lambda s=seccion:self._aplicar_entidad(s)).pack(side="left", padx=2)
        ttk.Button(acciones, text="Duplicar", command=lambda s=seccion:self._duplicar(s)).pack(side="left", padx=2)
        ttk.Button(acciones, text="Eliminar", style="Danger.TButton", command=lambda s=seccion:self._eliminar(s)).pack(side="left", padx=2)
        if seccion == "clases":
            ttk.Button(
                acciones, text="Periodos permitidos",
                command=self._editar_periodos_clase,
            ).pack(side="left", padx=(10, 2))
        formulario.columnconfigure(1, weight=1)

    def _crear_disponibilidad(self):
        p = self._pagina("disponibilidad")
        cabecera = ttk.Frame(p, style="Panel.TFrame")
        cabecera.pack(fill="x")
        textos = ttk.Frame(cabecera, style="Panel.TFrame")
        textos.pack(side="left", fill="x", expand=True)
        ttk.Label(textos, text="Disponibilidad semanal", style="PanelTitulo.TLabel").pack(anchor="w")
        ttk.Label(
            textos,
            text="Haz clic en una celda para alternarla. Los encabezados activan o desactivan un día completo.",
            style="Ayuda.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        self.boton_guardar_disponibilidad = ttk.Button(
            cabecera, text="Guardar disponibilidad", style="Primary.TButton",
            command=self._guardar_disponibilidad,
        )
        self.boton_guardar_disponibilidad.pack(side="right", padx=(12, 0))

        self.aviso_preferencias = tk.StringVar()
        if self.preferencias_migradas:
            self.aviso_preferencias.set(
                f"Se encontraron {self.preferencias_migradas} bloques preferidos históricos. "
                "Ya no afectan al fitness; al guardar se conservarán como historial y se registrará su desactivación."
            )
        self.panel_aviso_preferencias = tk.Label(
            p, textvariable=self.aviso_preferencias, bg="#fff7d6", fg="#7a5200",
            anchor="w", justify="left", padx=10, pady=7, wraplength=900,
            font=("Segoe UI", 9),
        )
        if self.preferencias_migradas:
            self.panel_aviso_preferencias.pack(fill="x", pady=(10, 0))

        selector = tk.Frame(
            p, bg="#f8fafc", highlightbackground="#d9e2ec",
            highlightthickness=1, padx=12, pady=10,
        )
        selector.pack(fill="x", pady=(10, 8))
        self.tipo_disponibilidad = tk.StringVar(value="Docente")
        self.entidad_disponibilidad = tk.StringVar()
        tk.Label(selector, text="Tipo", bg="#f8fafc", fg=TEXTO, font=("Segoe UI Semibold", 9)).pack(side="left")
        self.combo_ambito = ttk.Combobox(
            selector, textvariable=self.tipo_disponibilidad,
            values=("Docente", "Grupo"), state="readonly", width=14,
        )
        self.combo_ambito.pack(side="left", padx=(7, 18))
        tk.Label(selector, text="Persona o grupo", bg="#f8fafc", fg=TEXTO, font=("Segoe UI Semibold", 9)).pack(side="left")
        self.combo_entidad = ttk.Combobox(
            selector, textvariable=self.entidad_disponibilidad,
            state="readonly", width=34,
        )
        self.combo_entidad.pack(side="left", padx=7)
        self.combo_ambito.bind("<<ComboboxSelected>>", self._seleccion_disponibilidad_cambio)
        self.combo_entidad.bind("<<ComboboxSelected>>", self._seleccion_disponibilidad_cambio)

        indicadores = ttk.Frame(p, style="Panel.TFrame")
        indicadores.pack(fill="x", pady=(0, 8))
        self.disponibilidad_nombre = tk.StringVar(value="—")
        self.disponibilidad_horas = tk.StringVar(value="0 horas semanales")
        self.disponibilidad_estado = tk.StringVar(value="Guardado")
        for titulo, variable in (
            ("Entidad", self.disponibilidad_nombre),
            ("Horas disponibles", self.disponibilidad_horas),
            ("Estado", self.disponibilidad_estado),
        ):
            tarjeta = tk.Frame(
                indicadores, bg=PANEL, highlightbackground="#d9e2ec",
                highlightthickness=1, padx=12, pady=7,
            )
            tarjeta.pack(side="left", fill="x", expand=True, padx=(0, 7))
            tk.Label(tarjeta, text=titulo, bg=PANEL, fg=SECUNDARIO, font=("Segoe UI", 8), anchor="w").pack(fill="x")
            tk.Label(tarjeta, textvariable=variable, bg=PANEL, fg=AZUL, font=("Segoe UI Semibold", 11), anchor="w").pack(fill="x", pady=(2, 0))

        self.editor_semanal = EditorSemanal(p, self._disponibilidad_editada)
        self.editor_semanal.pack(fill="both", expand=True)

    def _crear_resumen(self):
        p = self._pagina("resumen"); ttk.Label(p, text="Resumen y validación", style="PanelTitulo.TLabel").pack(anchor="w"); ttk.Label(p, textvariable=self.validacion_texto, style="Ayuda.TLabel").pack(anchor="w", pady=(2,8))
        self.tabla_validacion = ttk.Treeview(p, columns=("nivel","codigo","mensaje"), show="headings")
        for clave,titulo,ancho in (("nivel","Nivel",100),("codigo","Código",170),("mensaje","Detalle",650)): self.tabla_validacion.heading(clave,text=titulo); self.tabla_validacion.column(clave,width=ancho,minwidth=80)
        for tag,color in (("error",PELIGRO),("advertencia","#9a6700"),("correcto",EXITO)): self.tabla_validacion.tag_configure(tag, foreground=color)
        self.tabla_validacion.pack(fill="both", expand=True); ttk.Button(p,text="Validar ahora",style="Accent.TButton",command=lambda:self._validar(mostrar=True)).pack(anchor="e",pady=(7,0))

    def _crear_barra_acciones(self):
        barra = tk.Frame(
            self, bg=PANEL, highlightbackground="#d9e2ec", highlightthickness=1,
            padx=10, pady=7,
        )
        barra.grid(row=3, column=0, sticky="ew")
        acciones = tk.Frame(barra, bg=PANEL)
        acciones.pack(side="right", padx=(8, 0))
        ttk.Button(
            acciones, text="Guardar todos los cambios", style="Primary.TButton",
            command=self._guardar,
        ).pack(side="left", padx=3)
        ttk.Button(acciones, text="Descartar", command=self._descartar).pack(side="left", padx=3)
        ttk.Button(
            acciones, text="Validar", command=lambda:self._validar(mostrar=True),
        ).pack(side="left", padx=3)
        ttk.Button(acciones, text="Ejecutar", command=self._ejecutar).pack(side="left", padx=3)
        izq = tk.Frame(barra, bg=PANEL)
        izq.pack(side="left", fill="x", expand=True)
        tk.Label(izq,textvariable=self.estado_archivo,bg=PANEL,fg=AZUL,font=("Segoe UI Semibold",9),anchor="w").pack(fill="x"); tk.Label(izq,textvariable=self.ruta_texto,bg=PANEL,fg=SECUNDARIO,font=("Segoe UI",8),anchor="w").pack(fill="x")
        self.etiqueta_validacion_barra = tk.Label(
            izq, textvariable=self.validacion_texto, bg=PANEL, fg=SECUNDARIO,
            font=("Segoe UI", 8), anchor="w",
        )
        self.etiqueta_validacion_barra.pack(fill="x")

    def _cambiar_categoria(self, clave="general"):
        if clave not in self.paginas:
            return
        for p in self.paginas.values():p.pack_forget()
        self.paginas[clave].pack(fill="both",expand=True)
        self._categoria_actual = clave
        for codigo, boton in self.botones_categorias.items():
            activo = codigo == clave
            boton.configure(
                bg="#dcefe6" if activo else PANEL,
                fg=EXITO if activo else SECUNDARIO,
                activebackground="#e8f5ee", activeforeground=EXITO,
            )
        if clave=="resumen":self._validar(mostrar=False)

    def refrescar(self):
        datos=self.modelo.datos; problema=self.modelo.validar(); self.kpis["docentes"].set(str(len(datos["docentes"]))); self.kpis["grupos"].set(str(len(datos["grupos"]))); self.kpis["materias"].set(str(len({str(c["materia"]) for c in datos["clases"]}))); self.kpis["sesiones"].set(str(len(problema.sesiones))); self.kpis["salones"].set(str(len(datos["salones"])))
        self.estado_archivo.set(self.modelo.estado_guardado); self.ruta_texto.set(f"Archivo activo único: {self.modelo.ruta_canonica}"); self._refrescar_general(); self._refrescar_entidades(); self._actualizar_entidades_disponibles()
        self._validar(mostrar=False)
        if not any(p.winfo_ismapped() for p in self.paginas.values()):
            self._cambiar_categoria(self._categoria_actual)

    def _refrescar_general(self):
        d=self.modelo.datos; seleccionados=set(d["dias"])
        for dia,var in self.dias_vars.items():var.set(dia in seleccionados)
        dur=int(d.get("metadatos",{}).get("duracion_bloque_minutos",60)); fin=(datetime.strptime(d["horas"][-1],"%H:%M")+timedelta(minutes=dur)).strftime("%H:%M")
        self.general["hora_inicio"].set(d["horas"][0]);self.general["hora_fin"].set(fin);self.general["duracion"].set(str(dur));self.general["nombre"].set(str(d.get("metadatos",{}).get("nombre","Configuración académica")));self.general["descripcion"].set(str(d.get("descripcion","")))
        r=d.get("restricciones",{});self.general["max_grupo"].set(str(r.get("max_horas_consecutivas_grupo") or ""));self.general["max_docente"].set(str(r.get("max_horas_consecutivas_docente") or ""));self.general["umbral"].set(str(r.get("umbral_jornada_larga",6)));self._calcular_bloques()
        franjas = r.get("franjas_no_lectivas", {})
        cantidad = sum(len(horas) for horas in franjas.values()) if isinstance(franjas, dict) else 0
        self.resumen_franjas.set(f"{cantidad} bloques no lectivos")

    def _editar_franjas_no_lectivas(self):
        estado = EstadoCuadriculaSemanal(
            self.modelo.datos["dias"], self.modelo.datos["horas"], False,
        )
        estado.cargar(
            self.modelo.datos.get("restricciones", {}).get("franjas_no_lectivas", {}),
        )
        dialogo = DialogoMapaSemanal(
            self, "Franjas institucionales no lectivas",
            "Las celdas con ✓ son lectivas. Desactiva los bloques en los que la "
            "institución no permite programar ninguna clase.", estado,
        )
        self.wait_window(dialogo)
        if dialogo.resultado is None:
            return
        nuevos = deepcopy(self.modelo.datos)
        nuevos.setdefault("restricciones", {})["franjas_no_lectivas"] = (
            dialogo.resultado.exportar_no_disponible()
        )
        self._reemplazar(nuevos)

    def _calcular_bloques(self):
        self.tabla_bloques.delete(*self.tabla_bloques.get_children())
        try:
            duracion=int(self.general["duracion"].get());horas=generar_horas(self.general["hora_inicio"].get(),self.general["hora_fin"].get(),duracion);self.bloques_calculados.set(f"{len(horas)} bloques: {horas[0]} – {horas[-1]}")
            for numero,inicio in enumerate(horas,1):
                fin=(datetime.strptime(inicio,"%H:%M")+timedelta(minutes=duracion)).strftime("%H:%M")
                self.tabla_bloques.insert("","end",values=(numero,inicio,fin))
        except (ValueError,IndexError):self.bloques_calculados.set("Selecciona un intervalo divisible y válido")

    def _aplicar_general(self):
        try:
            dias=[d for d in DIAS_BASE if self.dias_vars[d].get()];dur=int(self.general["duracion"].get());horas=generar_horas(self.general["hora_inicio"].get(),self.general["hora_fin"].get(),dur);n,impacto=migrar_estructura_temporal(self.modelo.datos,dias,horas,dur)
            n.setdefault("metadatos",{})["nombre"]=self.general["nombre"].get().strip() or "Configuración académica";n["descripcion"]=self.general["descripcion"].get().strip();r=n.setdefault("restricciones",{})
            for clave,var in (("max_horas_consecutivas_grupo",self.general["max_grupo"]),("max_horas_consecutivas_docente",self.general["max_docente"])):
                valor=var.get().strip()
                if valor:r[clave]=int(valor)
                else:r.pop(clave,None)
            r["umbral_jornada_larga"]=int(self.general["umbral"].get());problema_desde_datos(n)
        except (ValueError,KeyError,TypeError) as exc:messagebox.showerror("Configuración no válida",str(exc),parent=self);return
        detalle=f"Nuevo calendario: {len(dias)} días × {len(horas)} bloques.\nBloques anteriores que desaparecen: {impacto.bloques_eliminados}.\nReferencias semanales que se retirarán: {impacto.referencias_eliminadas} en {impacto.mapas_afectados} mapas.\n\n¿Aplicar estos cambios en memoria?"
        if messagebox.askyesno("Impacto del cambio temporal",detalle,parent=self):self._reemplazar(n)

    def _refrescar_entidades(self):
        d=self.modelo.datos
        for s,a in self.arboles.items():
            a.delete(*a.get_children())
            for i,r in enumerate(d[s]):
                valores=tuple(self._valor_entidad(s,r,k) for k,_e,_t in self.CAMPOS[s])
                a.insert("","end",iid=str(i),values=valores)
        for s,controles in self.controles_formulario.items():
            tipos={k:t for k,_e,t in self.CAMPOS[s]}
            for k,c in controles.items():
                if isinstance(c,ttk.Combobox):
                    valores=tuple(g["id"] for g in d["grupos"]) if tipos[k]=="grupo" else tuple(x["id"] for x in d["docentes"]) if tipos[k]=="docente" else tuple(sorted({"aula","laboratorio","auditorio","taller","cómputo"}|{str(x.get("tipo","aula")) for x in d["salones"]}));c.configure(values=valores)

    def _valor_entidad(self,s,r,k):
        if s=="grupos" and k=="materias_asignadas":
            materias=sorted({str(c["materia"]) for c in self.modelo.datos["clases"] if str(c["grupo"])==str(r["id"])})
            return ", ".join(materias) if materias else "Sin materias"
        return r.get(k,"")

    def _cargar_formulario(self,s):
        sel=self.arboles[s].selection()
        if not sel:return
        i=int(sel[0]);self.indice_edicion[s]=i;r=self.modelo.datos[s][i]
        for k,v in self.formularios[s].items():v.set(str(self._valor_entidad(s,r,k)))

    def _nuevo(self,s):
        self.indice_edicion[s]=None;d=self.modelo.datos;defaults={"docentes":{"id":"D_NUEVO","nombre":""},"grupos":{"id":"G_NUEVO","nombre":"","alumnos":"30"},"clases":{"id":"C_NUEVA","materia":"","grupo":d["grupos"][0]["id"],"docente":d["docentes"][0]["id"],"sesiones_semana":"1","duracion_bloques":"1","tipo_salon":d["salones"][0].get("tipo","aula")},"salones":{"id":"S_NUEVO","nombre":"","capacidad":"30","tipo":"aula"}}[s]
        for k,v in self.formularios[s].items():v.set(str(defaults.get(k,"")))
        self.arboles[s].selection_remove(self.arboles[s].selection())

    def _aplicar_entidad(self,s):
        v={k:x.get().strip() for k,x in self.formularios[s].items()}
        try:
            if not v["id"]:raise ValueError("El identificador es obligatorio")
            if s=="docentes":r={"id":v["id"],"nombre":v["nombre"],"no_disponible":{}}
            elif s=="grupos":r={"id":v["id"],"nombre":v["nombre"] or v["id"],"alumnos":int(v["alumnos"]),"no_disponible":{}}
            elif s=="clases":r={"id":v["id"],"materia":v["materia"],"grupo":v["grupo"],"docente":v["docente"],"sesiones_semana":int(v["sesiones_semana"]),"duracion_bloques":int(v["duracion_bloques"]),"tipo_salon":v["tipo_salon"]}
            else:r={"id":v["id"],"nombre":v["nombre"] or v["id"],"capacidad":int(v["capacidad"]),"tipo":v["tipo"]}
            n=deepcopy(self.modelo.datos);i=self.indice_edicion[s]
            if i is None:n[s].append(r)
            else:
                ant=n[s][i]
                if s in {"docentes","grupos"}:r["no_disponible"]=deepcopy(ant.get("no_disponible",{}));r.update({"preferidos":deepcopy(ant.get("preferidos",{}))} if s=="docentes" else {})
                if s=="clases" and "periodos_permitidos" in ant:r["periodos_permitidos"]=deepcopy(ant["periodos_permitidos"])
                n[s][i]=r
            if s in {"docentes","grupos"} and v.get("max_horas_consecutivas") not in {"", "0"}:r["max_horas_consecutivas"]=int(v["max_horas_consecutivas"])
            problema_desde_datos(n)
        except (ValueError,KeyError,TypeError) as exc:messagebox.showerror("Registro no válido",str(exc),parent=self);return
        self._reemplazar(n)

    def _editar_periodos_clase(self):
        indice = self._indice("clases")
        if indice is None:
            return
        clase = self.modelo.datos["clases"][indice]
        estado = EstadoCuadriculaSemanal(
            self.modelo.datos["dias"], self.modelo.datos["horas"], False,
        )
        estado.cargar_periodos_permitidos(
            clase.get("periodos_permitidos")
            if "periodos_permitidos" in clase else None,
        )
        dialogo = DialogoMapaSemanal(
            self, f"Periodos permitidos · {clase['id']}",
            "Las celdas con ✓ son periodos en los que esta materia puede ocupar "
            "bloques. Esta restricción permanece ligada a la sesión académica.",
            estado,
        )
        self.wait_window(dialogo)
        if dialogo.resultado is None:
            return
        nuevos = deepcopy(self.modelo.datos)
        destino = nuevos["clases"][indice]
        periodos = dialogo.resultado.periodos_permitidos()
        if periodos is None:
            destino.pop("periodos_permitidos", None)
        else:
            destino["periodos_permitidos"] = periodos
        self._reemplazar(nuevos)

    def _indice(self,s):
        sel=self.arboles[s].selection()
        if not sel:messagebox.showinfo("Selecciona un registro","Selecciona primero un registro de la tabla.",parent=self);return None
        return int(sel[0])

    def _duplicar(self,s):
        i=self._indice(s)
        if i is None:return
        n=deepcopy(self.modelo.datos);c=deepcopy(n[s][i]);base=str(c["id"])+"_COPIA";cand=base;num=2;ids={str(r["id"]) for r in n[s]}
        while cand in ids:cand=f"{base}{num}";num+=1
        c["id"]=cand
        if "nombre" in c:c["nombre"]=str(c["nombre"])+" (copia)"
        n[s].append(c);self._reemplazar(n)

    def _eliminar(self,s):
        i=self._indice(s)
        if i is None or not messagebox.askyesno("Eliminar registro","¿Eliminar el registro seleccionado?",parent=self):return
        try:self.modelo.eliminar(s,i)
        except (ValueError,KeyError,TypeError) as exc:messagebox.showerror("No se puede eliminar",str(exc),parent=self);return
        self.refrescar();self.al_cambiar()

    def _actualizar_entidades_disponibles(self):
        ambito = self.tipo_disponibilidad.get()
        if ambito not in {"Docente", "Grupo"}:
            ambito = "Docente"
            self.tipo_disponibilidad.set(ambito)
        seccion = "docentes" if ambito == "Docente" else "grupos"
        registros = self.modelo.datos[seccion]
        self._entidades_por_etiqueta = {}
        self._etiquetas_por_entidad = {}
        for registro in registros:
            identificador = str(registro["id"])
            nombre = str(registro.get("nombre") or identificador)
            etiqueta = f"{nombre} ({identificador})"
            self._entidades_por_etiqueta[etiqueta] = identificador
            self._etiquetas_por_entidad[identificador] = etiqueta
        valores = tuple(self._entidades_por_etiqueta)
        self.combo_entidad.configure(values=valores)
        actual = (
            self._clave_disponibilidad[1]
            if self._clave_disponibilidad and self._clave_disponibilidad[0] == ambito
            else None
        )
        identificador = actual if actual in self._etiquetas_por_entidad else (
            self._entidades_por_etiqueta[valores[0]] if valores else ""
        )
        self._cambiando_selector = True
        self.entidad_disponibilidad.set(self._etiquetas_por_entidad.get(identificador, ""))
        self._cambiando_selector = False
        if identificador and self._clave_disponibilidad is None:
            self._cargar_disponibilidad_entidad(ambito, identificador)

    def _registro_disponibilidad(self, ambito: str, identificador: str):
        seccion = "docentes" if ambito == "Docente" else "grupos"
        registro = next(
            (x for x in self.modelo.datos[seccion] if str(x["id"]) == identificador),
            None,
        )
        if registro is None:
            raise ValueError("Selecciona una entidad válida")
        return registro

    def _restaurar_selectores_disponibilidad(self) -> None:
        if self._clave_disponibilidad is None:
            return
        ambito, identificador = self._clave_disponibilidad
        self._cambiando_selector = True
        self.tipo_disponibilidad.set(ambito)
        self._actualizar_entidades_disponibles()
        self.entidad_disponibilidad.set(
            self._etiquetas_por_entidad.get(identificador, identificador),
        )
        self._cambiando_selector = False

    def _seleccion_disponibilidad_cambio(self, _evento=None):
        if self._cambiando_selector:
            return
        ambito = self.tipo_disponibilidad.get()
        if ambito not in {"Docente", "Grupo"}:
            return
        # Al cambiar de ámbito primero reconstruimos la lista legible.
        seccion = "docentes" if ambito == "Docente" else "grupos"
        registros = self.modelo.datos[seccion]
        etiquetas = {
            f"{str(x.get('nombre') or x['id'])} ({x['id']})": str(x["id"])
            for x in registros
        }
        etiqueta = self.entidad_disponibilidad.get()
        if etiqueta not in etiquetas:
            self._entidades_por_etiqueta = etiquetas
            self._etiquetas_por_entidad = {v: k for k, v in etiquetas.items()}
            self._cambiando_selector = True
            self.combo_entidad.configure(values=tuple(etiquetas))
            etiqueta = next(iter(etiquetas), "")
            self.entidad_disponibilidad.set(etiqueta)
            self._cambiando_selector = False
        identificador = etiquetas.get(etiqueta)
        if not identificador:
            return
        destino = (ambito, identificador)
        if destino == self._clave_disponibilidad:
            return
        if self._borrador_disponibilidad_sucio:
            decision = messagebox.askyesnocancel(
                "Disponibilidad sin guardar",
                "La entidad actual tiene cambios pendientes.\n\n"
                "Sí: Guardar disponibilidad\n"
                "No: Descartar cambios de esta entidad\n"
                "Cancelar: Permanecer en la entidad actual",
                parent=self,
            )
            if decision is None:
                self._restaurar_selectores_disponibilidad()
                return
            if decision and not self._guardar_disponibilidad():
                self._restaurar_selectores_disponibilidad()
                return
            if decision is False:
                self._descartar_borrador_disponibilidad()
        self._cargar_disponibilidad_entidad(*destino)

    def _cargar_disponibilidad_entidad(self, ambito: str, identificador: str) -> None:
        registro = self._registro_disponibilidad(ambito, identificador)
        estado = EstadoCuadriculaSemanal(
            self.modelo.datos["dias"], self.modelo.datos["horas"], False,
        )
        estado.cargar(registro.get("no_disponible", {}))
        self._clave_disponibilidad = (ambito, identificador)
        self._borrador_disponibilidad_original = deepcopy(estado.exportar_no_disponible())
        self._borrador_disponibilidad_sucio = False
        self._cambiando_selector = True
        self.tipo_disponibilidad.set(ambito)
        self._actualizar_entidades_disponibles()
        self.entidad_disponibilidad.set(
            self._etiquetas_por_entidad.get(identificador, identificador),
        )
        self._cambiando_selector = False
        self.editor_semanal.cargar(estado)
        self.disponibilidad_nombre.set(
            f"{registro.get('nombre') or identificador} · {identificador}",
        )
        self._actualizar_indicadores_disponibilidad()

    def _disponibilidad_editada(self) -> None:
        if self.editor_semanal.estado is None:
            return
        actual = self.editor_semanal.estado.exportar_no_disponible()
        self._borrador_disponibilidad_sucio = actual != self._borrador_disponibilidad_original
        if self._clave_disponibilidad is not None:
            try:
                self.modelo.reemplazar(
                    aplicar_disponibilidad_entidad(
                        self.modelo.datos, *self._clave_disponibilidad, actual,
                    ),
                )
            except (ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("Disponibilidad no válida", str(exc), parent=self)
                return
        if self._borrador_disponibilidad_sucio:
            self.estado_archivo.set("Cambios pendientes")
        else:
            self.estado_archivo.set(self.modelo.estado_guardado)
        self._actualizar_indicadores_disponibilidad()
        self.al_cambiar()

    def _descartar_borrador_disponibilidad(self) -> None:
        if self._clave_disponibilidad is None:
            return
        self.modelo.reemplazar(
            aplicar_disponibilidad_entidad(
                self.modelo.datos, *self._clave_disponibilidad,
                self._borrador_disponibilidad_original,
            ),
        )
        self._borrador_disponibilidad_sucio = False
        self.al_cambiar()

    def _actualizar_indicadores_disponibilidad(self) -> None:
        estado = self.editor_semanal.estado
        if estado is None:
            return
        duracion = int(
            self.modelo.datos.get("metadatos", {}).get("duracion_bloque_minutos", 60),
        )
        horas = calcular_horas_disponibles(estado, duracion)
        numero = f"{horas:g}"
        self.disponibilidad_horas.set(f"{numero} horas semanales")
        self.disponibilidad_estado.set(
            "Cambios pendientes" if self._borrador_disponibilidad_sucio else "Guardado"
        )

    def _guardar_disponibilidad(self) -> bool:
        if self._clave_disponibilidad is None or self.editor_semanal.estado is None:
            return False
        if self.modelo.migracion_preferencias_pendiente:
            if not messagebox.askokcancel(
                "Migración de preferencias anteriores",
                "Al guardar se desactivará la penalización por horarios preferidos. "
                "Los mapas anteriores permanecerán en el JSON como datos históricos, "
                "pero ya no afectarán al fitness.\n\n¿Continuar?",
                parent=self,
            ):
                return False
        ambito, identificador = self._clave_disponibilidad
        mapa = self.editor_semanal.estado.exportar_no_disponible()
        self.disponibilidad_estado.set("Guardando…")
        self.update_idletasks()
        try:
            destino = self.modelo.guardar_disponibilidad(ambito, identificador, mapa)
        except ConflictoArchivoExterno as exc:
            resolver = messagebox.askyesno(
                "Cambio externo detectado",
                f"{exc}\n\n¿Reintentar sobre la versión más reciente? "
                "Se preservarán todos sus demás datos y sólo se reemplazará la "
                "disponibilidad de esta entidad.",
                parent=self,
            )
            if not resolver:
                self.disponibilidad_estado.set("Cambios pendientes")
                return False
            try:
                destino = self.modelo.guardar_disponibilidad(
                    ambito, identificador, mapa, resolver_conflicto=True,
                )
            except (OSError, ValueError, KeyError, TypeError, ConflictoArchivoExterno) as segundo:
                messagebox.showerror("No se pudo guardar", str(segundo), parent=self)
                self.disponibilidad_estado.set("Error al guardar")
                return False
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
            self.disponibilidad_estado.set("Error al guardar")
            return False
        self._borrador_disponibilidad_original = deepcopy(mapa)
        self._borrador_disponibilidad_sucio = False
        self.preferencias_migradas = 0
        self.aviso_preferencias.set("")
        self.panel_aviso_preferencias.pack_forget()
        self.estado_archivo.set(self.modelo.estado_guardado)
        self.disponibilidad_estado.set("Guardado")
        self._validar(mostrar=False)
        self.al_cambiar()
        messagebox.showinfo(
            "Disponibilidad guardada",
            f"Se actualizó únicamente {ambito.lower()} {identificador} en:\n{destino}",
            parent=self,
        )
        return True

    def _integrar_borrador_disponibilidad(self, datos: dict[str, Any]) -> dict[str, Any]:
        if (
            not self._borrador_disponibilidad_sucio
            or self._clave_disponibilidad is None
            or self.editor_semanal.estado is None
        ):
            return datos
        return aplicar_disponibilidad_entidad(
            datos, *self._clave_disponibilidad,
            self.editor_semanal.estado.exportar_no_disponible(),
        )

    def _resolver_cambios_para_importar(self) -> bool:
        """Obtiene una decisión explícita antes de sustituir borradores locales."""
        if not (self.modelo.modificado or self._borrador_disponibilidad_sucio):
            return True
        decision = messagebox.askyesnocancel(
            "Cambios actuales pendientes",
            "La configuración activa tiene cambios sin guardar.\n\n"
            "Sí: Guardar la configuración actual y continuar\n"
            "No: Descartar esos cambios al completar la importación\n"
            "Cancelar: No importar",
            parent=self,
        )
        if decision is None:
            return False
        if decision:
            return bool(self._guardar())
        # El borrador se conserva hasta que la escritura importada tenga éxito.
        # Así, un error de permisos o un conflicto nunca provoca pérdida silenciosa.
        return True

    def _aplicar_importacion(self, previa: VistaPreviaImportacion) -> bool:
        """Confirma y persiste una vista previa válida en el archivo canónico."""
        if not previa.importable:
            self.estado_importacion.set("Error de validación")
            return False
        if not self._resolver_cambios_para_importar():
            self.estado_importacion.set("Importación cancelada")
            return False
        self.estado_importacion.set("Importando…")
        self.update_idletasks()
        try:
            destino = self.modelo.importar_configuracion(previa.datos)
        except ConflictoArchivoExterno as exc:
            reemplazar = messagebox.askyesno(
                "Cambio externo detectado",
                f"{exc}\n\nEl archivo activo cambió desde que se abrió la aplicación. "
                "¿Reemplazarlo por el escenario importado? Esta acción requiere "
                "confirmación expresa.",
                parent=self,
            )
            if not reemplazar:
                self.estado_importacion.set("Importación cancelada por conflicto")
                return False
            try:
                destino = self.modelo.importar_configuracion(
                    previa.datos, resolver_conflicto=True,
                )
            except (OSError, ValueError, KeyError, TypeError, ConflictoArchivoExterno) as segundo:
                messagebox.showerror(
                    "No se pudo importar", str(segundo), parent=self,
                )
                self.estado_importacion.set("Error de importación")
                return False
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("No se pudo importar", str(exc), parent=self)
            self.estado_importacion.set("Error de importación")
            return False

        self.preferencias_migradas = 0
        self.aviso_preferencias.set("")
        self.panel_aviso_preferencias.pack_forget()
        self._clave_disponibilidad = None
        self._borrador_disponibilidad_original = {}
        self._borrador_disponibilidad_sucio = False
        for seccion in self.indice_edicion:
            self.indice_edicion[seccion] = None
        self.refrescar()
        # La aplicación propaga esta instantánea a optimización, experimentos y
        # evolución; los resultados anteriores conservan su huella histórica.
        self.al_cambiar()
        self.estado_importacion.set("Importación completada")
        messagebox.showinfo(
            "Escenario importado",
            f"Se activó «{previa.nombre}» en el archivo único:\n{destino}\n\n"
            f"{previa.docentes} docentes · {previa.grupos} grupos · "
            f"{previa.materias} materias · {previa.sesiones} sesiones · "
            f"{previa.salones} salones",
            parent=self,
        )
        return True

    def _importar_escenario_json(self) -> bool:
        """Selecciona, valida, previsualiza y activa un escenario externo."""
        self.estado_importacion.set("Seleccionando archivo…")
        self.update_idletasks()
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Importar escenario académico JSON",
            filetypes=(("Escenarios JSON", "*.json"), ("Todos los archivos", "*.*")),
        )
        if not ruta:
            self.estado_importacion.set("Importación cancelada")
            return False
        try:
            if Path(ruta).resolve() == self.modelo.ruta_canonica.resolve():
                messagebox.showinfo(
                    "Escenario ya activo",
                    "El archivo seleccionado ya es la configuración académica activa; "
                    "no es necesario importarlo.",
                    parent=self,
                )
                self.estado_importacion.set("El escenario ya está activo")
                return False
        except OSError:
            # La lectura posterior producirá el diagnóstico específico de ruta.
            pass

        self.estado_importacion.set("Validando…")
        self.update_idletasks()
        try:
            previa = preparar_importacion(ruta)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror(
                "No se pudo validar el escenario", str(exc), parent=self,
            )
            self.estado_importacion.set("Error de validación")
            return False

        self.estado_importacion.set(
            "Listo para importar" if previa.importable else "Error de validación"
        )
        dialogo = DialogoVistaPreviaImportacion(self, previa)
        self.wait_window(dialogo)
        if not dialogo.confirmado:
            if previa.importable:
                self.estado_importacion.set("Importación cancelada")
            return False
        return self._aplicar_importacion(previa)

    def _reemplazar(self,n):
        n = self._integrar_borrador_disponibilidad(n)
        try:self.modelo.reemplazar(n)
        except (ValueError,KeyError,TypeError) as exc:messagebox.showerror("Cambio no válido",str(exc),parent=self);return
        self.refrescar();self.al_cambiar()

    def _validar(self,*,mostrar):
        r=validar_escenario_detallado(self.modelo.datos);self.tabla_validacion.delete(*self.tabla_validacion.get_children())
        for i,x in enumerate(r.incidencias):self.tabla_validacion.insert("","end",iid=str(i),values=(x.nivel.capitalize(),x.codigo,x.mensaje),tags=(x.nivel,))
        self.validacion_texto.set(f"{len(r.errores)} errores · {len(r.advertencias)} advertencias · estructura {'válida' if r.correcto else 'no válida'}")
        self.etiqueta_validacion_barra.configure(fg=EXITO if r.correcto and not r.advertencias else "#9a6700" if r.correcto else PELIGRO)
        if mostrar:
            if r.correcto:messagebox.showinfo("Validación completada","La configuración es interpretable por el motor."+(f" Revisa {len(r.advertencias)} advertencias; no demuestran imposibilidad matemática." if r.advertencias else ""),parent=self)
            else:messagebox.showerror("Configuración no válida",r.errores[0].mensaje,parent=self)
        return r.correcto

    def _guardar(self):
        if self._borrador_disponibilidad_sucio:
            try:
                self.modelo.reemplazar(
                    self._integrar_borrador_disponibilidad(self.modelo.datos),
                )
            except (ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("Disponibilidad no válida", str(exc), parent=self)
                return False
        if not self._validar(mostrar=False):messagebox.showerror("No se puede guardar","Corrige los errores indicados en Resumen y validación.",parent=self);return False
        self.estado_archivo.set("Guardando…")
        self.update_idletasks()
        try:destino=self.modelo.guardar()
        except ConflictoArchivoExterno as exc:messagebox.showerror("Cambio externo detectado",str(exc),parent=self);return False
        except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror("No se pudo guardar",str(exc),parent=self);return False
        if self.editor_semanal.estado is not None:
            self._borrador_disponibilidad_original = deepcopy(
                self.editor_semanal.estado.exportar_no_disponible(),
            )
        self._borrador_disponibilidad_sucio = False
        self.preferencias_migradas = 0
        self.aviso_preferencias.set("")
        self.panel_aviso_preferencias.pack_forget()
        self.refrescar();self.al_cambiar();messagebox.showinfo("Configuración guardada",f"Se reemplazó de forma segura el archivo activo:\n{destino}",parent=self);return True

    def _descartar(self):
        if not (self.modelo.modificado or self._borrador_disponibilidad_sucio) or not messagebox.askyesno("Descartar cambios","¿Descartar los cambios en memoria y recargar el archivo activo?",parent=self):return
        try:self.modelo.descartar()
        except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror("No se pudo recargar",str(exc),parent=self);return
        self.preferencias_migradas = self.modelo.preparar_disponibilidad_binaria()
        self.aviso_preferencias.set(
            f"Se encontraron {self.preferencias_migradas} bloques preferidos históricos. "
            "Ya no afectan al fitness; al guardar se conservarán como historial y se registrará su desactivación."
            if self.preferencias_migradas else ""
        )
        if self.preferencias_migradas:
            self.panel_aviso_preferencias.pack(fill="x", pady=(10, 0), after=self.panel_aviso_preferencias.master.winfo_children()[0])
        else:
            self.panel_aviso_preferencias.pack_forget()
        self._clave_disponibilidad = None
        self._borrador_disponibilidad_sucio = False
        self.refrescar();self.al_cambiar()

    def _ejecutar(self):
        if self.al_ejecutar is None:return
        if self._borrador_disponibilidad_sucio:
            try:
                self.modelo.reemplazar(
                    self._integrar_borrador_disponibilidad(self.modelo.datos),
                )
            except (ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("Disponibilidad no válida", str(exc), parent=self)
                return
        if not self._validar(mostrar=False):messagebox.showerror("No se puede ejecutar","Corrige primero los errores de validación.",parent=self);return
        if self.modelo.modificado:
            decision=messagebox.askyesnocancel("Cambios sin guardar","Se recomienda guardar antes de ejecutar.\n\n¿Guardar ahora?",parent=self)
            if decision is None:return
            if decision and not self._guardar():return
        self.al_ejecutar()


# Compatibilidad de importación; el flujo actual usa el editor embebido.
DialogoDisponibilidad = EditorSemanal
