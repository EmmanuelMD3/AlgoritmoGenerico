"""Lectura segura y vista previa de escenarios académicos importables."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .constructor_escenarios import (
    ResultadoValidacionEscenario,
    validar_escenario_detallado,
)
from .datos import cargar_datos


LIMITE_IMPORTACION_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class VistaPreviaImportacion:
    ruta: Path
    datos: dict[str, Any]
    nombre: str
    docentes: int
    grupos: int
    materias: int
    sesiones: int
    salones: int
    dias: tuple[str, ...]
    rango_horario: str
    duracion_bloque_minutos: int
    validacion: ResultadoValidacionEscenario

    @property
    def importable(self) -> bool:
        return self.validacion.correcto


def _lista(datos: dict[str, Any], clave: str) -> list[Any]:
    valor = datos.get(clave, [])
    return valor if isinstance(valor, list) else []


def _sesiones_declaradas(clases: list[Any]) -> int:
    total = 0
    for clase in clases:
        if not isinstance(clase, dict):
            continue
        try:
            cantidad = int(clase.get("sesiones_semana", 1))
        except (TypeError, ValueError):
            continue
        if cantidad > 0:
            total += cantidad
    return total


def _rango_horario(datos: dict[str, Any], duracion: int) -> str:
    horas = _lista(datos, "horas")
    if not horas:
        return "Sin bloques"
    inicio = str(horas[0])
    try:
        fin = (
            datetime.strptime(str(horas[-1]), "%H:%M")
            + timedelta(minutes=duracion)
        ).strftime("%H:%M")
    except (TypeError, ValueError):
        fin = str(horas[-1])
    return f"{inicio} – {fin}"


def preparar_importacion(
    ruta: str | Path, *, limite_bytes: int = LIMITE_IMPORTACION_BYTES,
) -> VistaPreviaImportacion:
    """Lee un JSON sin ejecutarlo y construye una vista previa validada.

    Los documentos anteriores sin duración explícita conservan el contrato
    histórico de bloques de 60 minutos. No se completan referencias ni se
    inventan entidades ausentes.
    """
    origen = Path(ruta)
    if not origen.exists():
        raise FileNotFoundError(f"El archivo seleccionado no existe: {origen}")
    if not origen.is_file():
        raise ValueError("Selecciona un archivo JSON, no una carpeta")
    if origen.suffix.lower() != ".json":
        raise ValueError("El archivo seleccionado debe tener extensión .json")
    try:
        tamano = origen.stat().st_size
    except OSError as exc:
        raise OSError(f"No se pudo consultar el archivo: {exc}") from exc
    if tamano > limite_bytes:
        raise ValueError(
            f"El archivo ocupa {tamano / (1024 * 1024):.1f} MiB; "
            f"el límite de importación es {limite_bytes / (1024 * 1024):.0f} MiB"
        )
    try:
        datos = cargar_datos(origen)
    except UnicodeError as exc:
        raise ValueError("El archivo debe estar codificado en UTF-8") from exc
    except OSError as exc:
        raise OSError(f"No se pudo leer el archivo seleccionado: {exc}") from exc

    validacion = validar_escenario_detallado(datos)
    metadatos = datos.get("metadatos", {})
    if not isinstance(metadatos, dict):
        metadatos = {}
    try:
        duracion = int(metadatos.get("duracion_bloque_minutos", 60))
    except (TypeError, ValueError):
        duracion = 60
    clases = _lista(datos, "clases")
    materias = {
        str(clase.get("materia_id", clase.get("materia", "")))
        for clase in clases if isinstance(clase, dict)
        if str(clase.get("materia_id", clase.get("materia", ""))).strip()
    }
    resumen = validacion.resumen
    nombre = str(
        metadatos.get("nombre")
        or datos.get("descripcion")
        or origen.stem
    )
    return VistaPreviaImportacion(
        ruta=origen,
        datos=datos,
        nombre=nombre,
        docentes=int(resumen.get("docentes", len(_lista(datos, "docentes")))),
        grupos=int(resumen.get("grupos", len(_lista(datos, "grupos")))),
        materias=int(resumen.get("materias", len(materias))),
        sesiones=int(resumen.get("sesiones", _sesiones_declaradas(clases))),
        salones=int(resumen.get("salones", len(_lista(datos, "salones")))),
        dias=tuple(str(dia) for dia in _lista(datos, "dias")),
        rango_horario=_rango_horario(datos, duracion),
        duracion_bloque_minutos=duracion,
        validacion=validacion,
    )
