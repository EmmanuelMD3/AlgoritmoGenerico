"""Exportaciones visuales seguras de registros evolutivos."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .evolucion import InstantaneaEvolutiva, RegistroEvolucion, resultado_desde_instantanea
from .modelo import Problema
from .reportes import exportar_horario_imagen


def exportar_instantanea_png(
    problema: Problema,
    configuracion,
    instantanea: InstantaneaEvolutiva,
    ruta: str | Path,
    modo: str = "grupo",
    identificador: str | None = None,
) -> Path:
    return exportar_horario_imagen(
        problema, resultado_desde_instantanea(instantanea, configuracion),
        ruta, modo, identificador,
    )


def exportar_comparacion_png(
    problema: Problema,
    configuracion,
    izquierda: InstantaneaEvolutiva,
    derecha: InstantaneaEvolutiva,
    ruta: str | Path,
    modo: str = "grupo",
    identificador: str | None = None,
) -> Path:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ImportError("Pillow es necesario para exportar comparaciones") from exc
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        a = exportar_instantanea_png(problema, configuracion, izquierda, Path(tmp) / "a.png", modo, identificador)
        b = exportar_instantanea_png(problema, configuracion, derecha, Path(tmp) / "b.png", modo, identificador)
        with Image.open(a) as img_a, Image.open(b) as img_b:
            img_a = img_a.convert("RGB")
            img_b = img_b.convert("RGB")
            margen, encabezado = 20, 92
            lienzo = Image.new(
                "RGB", (img_a.width + img_b.width + margen * 3, max(img_a.height, img_b.height) + encabezado + margen),
                "white",
            )
            lienzo.paste(img_a, (margen, encabezado))
            lienzo.paste(img_b, (img_a.width + margen * 2, encabezado))
            dibujo = ImageDraw.Draw(lienzo)
            dibujo.text((margen, 12), f"Generación {izquierda.generacion}: duras {izquierda.evaluacion_global.duras}, blanda {izquierda.evaluacion_global.penalizacion_blanda}, fitness {izquierda.evaluacion_global.fitness}", fill="#12344d")
            dibujo.text((img_a.width + margen * 2, 12), f"Generación {derecha.generacion}: duras {derecha.evaluacion_global.duras}, blanda {derecha.evaluacion_global.penalizacion_blanda}, fitness {derecha.evaluacion_global.fitness}", fill="#12344d")
            dibujo.text((margen, 46), "Comparación basada en cromosomas reales almacenados", fill="#5d6d7e")
            lienzo.save(destino, format="PNG")
    return destino


def exportar_secuencia_png(
    problema: Problema,
    registro: RegistroEvolucion,
    carpeta: str | Path,
    *,
    modo: str = "grupo",
    identificador: str | None = None,
    cada: int = 1,
    max_fotogramas: int = 300,
) -> tuple[Path, ...]:
    if cada < 1:
        raise ValueError("El intervalo de generaciones debe ser positivo")
    seleccion = registro.instantaneas[::cada]
    if len(seleccion) > max_fotogramas:
        raise ValueError(f"La secuencia produciría {len(seleccion)} imágenes; aumenta el intervalo")
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for instantanea in seleccion:
        ruta = destino / f"generacion_{instantanea.generacion:05d}.png"
        rutas.append(exportar_instantanea_png(
            problema, registro.configuracion, instantanea, ruta, modo, identificador,
        ))
    return tuple(rutas)


def exportar_gif(
    problema: Problema,
    registro: RegistroEvolucion,
    ruta: str | Path,
    *,
    modo: str = "grupo",
    identificador: str | None = None,
    cada: int = 1,
    duracion: float = .5,
    max_fotogramas: int = 200,
) -> Path:
    if duracion <= 0:
        raise ValueError("La duración por fotograma debe ser positiva")
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("Pillow es necesario para exportar GIF") from exc
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        rutas = exportar_secuencia_png(
            problema, registro, tmp, modo=modo, identificador=identificador,
            cada=cada, max_fotogramas=max_fotogramas,
        )
        if not rutas:
            raise ValueError("El registro no contiene fotogramas")
        imagenes = []
        for ruta_png in rutas:
            with Image.open(ruta_png) as imagen:
                imagenes.append(imagen.convert("P", palette=Image.Palette.ADAPTIVE).copy())
        imagenes[0].save(
            destino, save_all=True, append_images=imagenes[1:],
            duration=max(20, round(duracion * 1000)), loop=0, optimize=False,
        )
    return destino

