"""Lectura y comprobacion de los datos academicos en formato JSON."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .modelo import Docente, Grupo, Problema, Salon, Sesion


class ConflictoArchivoExterno(RuntimeError):
    """El JSON activo cambió en disco después de que la aplicación lo leyó."""


def huella_archivo(ruta: str | Path) -> str | None:
    """Devuelve la huella del contenido o ``None`` si el archivo no existe."""
    destino = Path(ruta)
    if not destino.exists():
        return None
    return hashlib.sha256(destino.read_bytes()).hexdigest()


def _bloques_desde_mapa(
    valor: Any,
    dias: tuple[str, ...],
    horas: tuple[str, ...],
    campo: str,
) -> frozenset[tuple[int, int]]:
    """Convierte ``{día: [horas]}`` a índices y genera errores comprensibles."""
    if not isinstance(valor, dict):
        raise ValueError(f"{campo} debe ser un objeto organizado por día")
    bloques: set[tuple[int, int]] = set()
    for dia, lista_horas in valor.items():
        if dia not in dias:
            raise ValueError(f"Día desconocido en {campo}: {dia}")
        if not isinstance(lista_horas, list):
            raise ValueError(f"Las horas de {campo} deben ser una lista")
        for hora in lista_horas:
            if hora not in horas:
                raise ValueError(f"Hora desconocida en {campo}: {hora}")
            bloques.add((dias.index(dia), horas.index(hora)))
    return frozenset(bloques)


def _limite_positivo(valor: Any, campo: str) -> int | None:
    if valor in (None, "", 0, "0"):
        return None
    try:
        limite = int(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{campo} debe ser un entero positivo o estar desactivado") from exc
    if limite < 1:
        raise ValueError(f"{campo} debe ser un entero positivo")
    return limite


def cargar_datos(ruta: str | Path) -> dict[str, Any]:
    """Carga un documento JSON sin convertirlo todavía al modelo académico."""
    ruta = Path(ruta)
    try:
        with ruta.open(encoding="utf-8") as f:
            datos = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"El archivo JSON no es válido (línea {exc.lineno}, columna {exc.colno})"
        ) from exc
    if not isinstance(datos, dict):
        raise ValueError("La raíz del archivo JSON debe ser un objeto")
    return datos


def guardar_datos(datos: dict[str, Any], ruta: str | Path) -> Path:
    """Valida y guarda datos compatibles con :func:`cargar_problema`."""
    validar_datos(datos)
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destino


def guardar_datos_atomico(
    datos: dict[str, Any],
    ruta: str | Path,
    *,
    huella_esperada: str | None = None,
    comprobar_cambio: bool = False,
) -> tuple[Path, str]:
    """Valida y reemplaza un JSON de forma atómica, detectando cambios externos.

    El temporal se crea en el mismo directorio para que ``os.replace`` no cruce
    sistemas de archivos. La comparación usa el contenido, no sólo la fecha.
    """
    validar_datos(datos)
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if comprobar_cambio and huella_archivo(destino) != huella_esperada:
        raise ConflictoArchivoExterno(
            "La configuración cambió fuera de la aplicación. "
            "Descarta y vuelve a cargar antes de guardar para no sobrescribirla."
        )
    contenido = (json.dumps(datos, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporal: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destino.parent, prefix=f".{destino.name}.",
            suffix=".tmp", delete=False,
        ) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()
    return destino, hashlib.sha256(contenido).hexdigest()


def validar_datos(datos: dict[str, Any]) -> Problema:
    """Comprueba un diccionario y devuelve el modelo resultante si es válido."""
    return problema_desde_datos(deepcopy(datos))


def cargar_problema(ruta: str | Path) -> Problema:
    return problema_desde_datos(cargar_datos(ruta))


def problema_desde_datos(datos: dict[str, Any]) -> Problema:
    """Construye el modelo desde la misma estructura usada por el archivo JSON."""
    requeridas = ("dias", "horas", "salones", "grupos", "docentes", "clases")
    faltantes = [clave for clave in requeridas if clave not in datos]
    if faltantes:
        raise ValueError(f"Faltan secciones obligatorias: {', '.join(faltantes)}")
    if any(not isinstance(datos[clave], list) for clave in requeridas):
        raise ValueError("Días, horas, salones, grupos, docentes y clases deben ser listas")

    dias = tuple(str(dia).strip() for dia in datos["dias"])
    horas = tuple(str(hora).strip() for hora in datos["horas"])
    if len(dias) < 1 or len(horas) < 1 or any(not dia for dia in dias) or len(set(dias)) != len(dias):
        raise ValueError("Los dias y las horas deben existir, y los dias no pueden repetirse")
    try:
        horas_dt = [datetime.strptime(h, "%H:%M") for h in horas]
    except ValueError as exc:
        raise ValueError("Las horas deben tener formato HH:MM") from exc
    metadatos = datos.get("metadatos", {})
    if metadatos is None:
        metadatos = {}
    if not isinstance(metadatos, dict):
        raise ValueError("La sección metadatos debe ser un objeto")
    try:
        duracion_bloque = int(metadatos.get("duracion_bloque_minutos", 60))
    except (TypeError, ValueError) as exc:
        raise ValueError("La duración del bloque debe ser un entero positivo") from exc
    if duracion_bloque < 15 or duracion_bloque > 180:
        raise ValueError("La duración del bloque debe estar entre 15 y 180 minutos")
    if len(set(horas)) != len(horas) or any(
        horas_dt[i + 1] - horas_dt[i] != timedelta(minutes=duracion_bloque)
        for i in range(len(horas_dt) - 1)
    ):
        raise ValueError(f"Las horas deben ser bloques consecutivos de {duracion_bloque} minutos")

    try:
        salones = tuple(
            Salon(str(s["id"]).strip(), int(s["capacidad"]), str(s.get("tipo", "aula")).strip())
            for s in datos["salones"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Cada salón debe contener campos válidos") from exc
    grupos: dict[str, Grupo] = {}
    try:
        for g in datos["grupos"]:
            grupo_id = str(g["id"]).strip()
            if grupo_id in grupos:
                raise ValueError(f"Grupo duplicado: {grupo_id}")
            grupos[grupo_id] = Grupo(
                grupo_id,
                int(g["alumnos"]),
                _bloques_desde_mapa(
                    g.get("no_disponible", {}), dias, horas,
                    f"indisponibilidad del grupo {grupo_id}",
                ),
                _limite_positivo(
                    g.get("max_horas_consecutivas"),
                    f"máximo consecutivo del grupo {grupo_id}",
                ),
            )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Cada grupo debe contener identificador y alumnos válidos") from exc
    if len(salones) != len({s.id for s in salones}) or not salones:
        raise ValueError("Debe haber salones y sus identificadores deben ser unicos")
    if len(grupos) != len(datos["grupos"]) or not grupos:
        raise ValueError("Debe haber grupos y sus identificadores deben ser unicos")
    if any(not s.id or not s.tipo for s in salones) or any(not g.id for g in grupos.values()):
        raise ValueError("Los identificadores y tipos de salón/grupo no pueden estar vacíos")
    if any(s.capacidad <= 0 for s in salones) or any(g.alumnos <= 0 for g in grupos.values()):
        raise ValueError("Las capacidades y cantidades de alumnos deben ser positivas")

    docentes: dict[str, Docente] = {}
    for doc in datos["docentes"]:
        try:
            doc_id = str(doc["id"]).strip()
            nombre = str(doc["nombre"]).strip()
        except (KeyError, TypeError) as exc:
            raise ValueError("Cada docente requiere identificador y nombre") from exc
        if not doc_id or not nombre:
            raise ValueError("El identificador y nombre de cada docente son obligatorios")
        if doc_id in docentes:
            raise ValueError(f"Docente duplicado: {doc_id}")
        disponibilidad = doc.get("no_disponible", {})
        no_disp = _bloques_desde_mapa(
            disponibilidad, dias, horas, f"indisponibilidad del docente {doc_id}",
        )
        preferidos = _bloques_desde_mapa(
            doc.get("preferidos", {}), dias, horas, f"horarios preferidos del docente {doc_id}",
        )
        docentes[doc_id] = Docente(
            doc_id, nombre, no_disp, preferidos,
            _limite_positivo(
                doc.get("max_horas_consecutivas"),
                f"máximo consecutivo del docente {doc_id}",
            ),
        )
    if not docentes:
        raise ValueError("Se necesita al menos un docente")

    sesiones: list[Sesion] = []
    salones_validos: list[tuple[int, ...]] = []
    ids_clases: set[str] = set()
    for clase in datos["clases"]:
        try:
            clase_id = str(clase["id"]).strip()
            materia = str(clase["materia"]).strip()
        except (KeyError, TypeError) as exc:
            raise ValueError("Cada clase requiere identificador y nombre de materia") from exc
        if not clase_id or not materia:
            raise ValueError("El identificador y la materia de cada clase son obligatorios")
        if clase_id in ids_clases:
            raise ValueError(f"Clase duplicada: {clase_id}")
        ids_clases.add(clase_id)
        try:
            grupo, docente = str(clase["grupo"]).strip(), str(clase["docente"]).strip()
        except KeyError as exc:
            raise ValueError(f"La clase {clase_id} requiere grupo y docente") from exc
        if grupo not in grupos or docente not in docentes:
            raise ValueError(f"Clase {clase_id} hace referencia a un grupo/docente inexistente")
        try:
            duracion = int(clase.get("duracion_bloques", 1))
            repeticiones = int(clase.get("sesiones_semana", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Duración o sesiones no numéricas: {clase_id}") from exc
        tipo = str(clase.get("tipo_salon", "aula")).strip()
        if duracion <= 0 or duracion > len(horas) or repeticiones <= 0:
            raise ValueError(f"Duracion o numero de sesiones no validos: {clase_id}")
        validos = tuple(
            i for i, salon in enumerate(salones)
            if salon.tipo == tipo and salon.capacidad >= grupos[grupo].alumnos
        )
        if not validos:
            raise ValueError(f"Sin salones de tipo/capacidad adecuada para {clase_id}")
        periodos = None
        if "periodos_permitidos" in clase and clase["periodos_permitidos"] is not None:
            periodos = _bloques_desde_mapa(
                clase["periodos_permitidos"], dias, horas,
                f"periodos permitidos de la clase {clase_id}",
            )
        for numero in range(1, repeticiones + 1):
            sesiones.append(Sesion(
                id=f"{clase_id}-S{numero}", materia=materia,
                grupo=grupo, docente=docente, duracion=duracion, tipo_salon=tipo,
                clase_id=clase_id, periodos_permitidos=periodos,
            ))
            salones_validos.append(validos)

    if not sesiones:
        raise ValueError("No se definio ninguna clase")
    restricciones = datos.get("restricciones", {})
    if not isinstance(restricciones, dict):
        raise ValueError("La sección restricciones debe ser un objeto")
    franjas_no_lectivas = _bloques_desde_mapa(
        restricciones.get("franjas_no_lectivas", {}), dias, horas,
        "franjas no lectivas",
    )
    max_grupo = _limite_positivo(
        restricciones.get("max_horas_consecutivas_grupo"),
        "máximo de horas consecutivas por grupo",
    )
    max_docente = _limite_positivo(
        restricciones.get("max_horas_consecutivas_docente"),
        "máximo de horas consecutivas por docente",
    )
    try:
        umbral_jornada = int(restricciones.get("umbral_jornada_larga", 6))
    except (TypeError, ValueError) as exc:
        raise ValueError("El umbral de jornada larga debe ser un entero positivo") from exc
    if umbral_jornada < 1:
        raise ValueError("El umbral de jornada larga debe ser un entero positivo")
    preferencias_activas = restricciones.get("preferencias_docentes_activas", True)
    if not isinstance(preferencias_activas, bool):
        raise ValueError("preferencias_docentes_activas debe ser verdadero o falso")

    return Problema(
        dias=dias, horas=horas, salones=salones, grupos=grupos, docentes=docentes,
        sesiones=tuple(sesiones), salones_validos=tuple(salones_validos),
        franjas_no_lectivas=franjas_no_lectivas,
        max_horas_consecutivas_grupo=max_grupo,
        max_horas_consecutivas_docente=max_docente,
        umbral_jornada_larga=umbral_jornada,
        duracion_bloque_minutos=duracion_bloque,
        preferencias_docentes_activas=preferencias_activas,
    )
