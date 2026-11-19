"""Escenarios académicos reproducibles para experimentación científica."""
from __future__ import annotations

import hashlib
import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .datos import cargar_datos, problema_desde_datos, validar_datos
from .fitness import evaluar


ESPECIFICACIONES = {
    "pequeno": {"etiqueta": "Pequeño", "grupos": 3, "docentes": 7, "salones": 4},
    "mediano": {"etiqueta": "Mediano", "grupos": 10, "docentes": 25, "salones": 12},
    "grande": {"etiqueta": "Grande", "grupos": 25, "docentes": 60, "salones": 30},
}


def huella_escenario(datos: dict[str, Any]) -> str:
    """Devuelve SHA-256 sobre una representación JSON canónica del escenario."""
    canonico = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _mapa_bloques(
    bloques: set[tuple[int, int]], dias: list[str], horas: list[str],
) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for dia, hora in sorted(bloques):
        resultado.setdefault(dias[dia], []).append(horas[hora])
    return resultado


def generar_escenario_sintetico(
    tamano: str,
    semilla: int = 42,
    *,
    estres: bool = False,
) -> dict[str, Any]:
    """Genera un escenario mediano o grande con referencias válidas.

    En modo normal se construye internamente un horario testigo, se valida con la
    función fitness real y se descarta antes de devolver los datos. El testigo no
    se entrega al algoritmo. El modo de estrés agrega restricciones que pueden
    invalidarlo y, por tanto, no promete factibilidad.
    """
    clave = tamano.lower().strip()
    if clave not in {"mediano", "grande"}:
        raise ValueError("El generador sintético admite los tamaños mediano y grande")
    especificacion = ESPECIFICACIONES[clave]
    rng = random.Random(semilla)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
    horas = [f"{hora:02d}:00" for hora in range(7, 17)]
    cantidad_grupos = especificacion["grupos"]
    cantidad_docentes = especificacion["docentes"]
    cantidad_salones = especificacion["salones"]

    grupos = [
        {"id": f"G{indice + 1:02d}", "alumnos": 24 + (indice * 7) % 22}
        for indice in range(cantidad_grupos)
    ]
    salones: list[dict[str, Any]] = []
    for indice in range(cantidad_salones):
        tipo = "laboratorio" if indice % 3 == 0 else "aula"
        salones.append({
            "id": f"{'L' if tipo == 'laboratorio' else 'A'}{indice + 1:02d}",
            "capacidad": 55 + (indice % 3) * 10,
            "tipo": tipo,
        })
    docentes = [
        {"id": f"D{indice + 1:02d}", "nombre": f"Docente sintético {indice + 1:02d}"}
        for indice in range(cantidad_docentes)
    ]

    ocupacion_grupo: set[tuple[str, int, int]] = set()
    ocupacion_docente: set[tuple[str, int, int]] = set()
    ocupacion_salon: set[tuple[str, int, int]] = set()
    testigo: list[tuple[int, int, int]] = []
    clases: list[dict[str, Any]] = []
    indice_salon = {salon["id"]: i for i, salon in enumerate(salones)}
    clases_por_grupo = 5 if clave == "mediano" else 4
    bloque_institucional = (2, 5)  # Miércoles a las 12:00.

    for numero_grupo, grupo in enumerate(grupos):
        for numero_clase in range(clases_por_grupo):
            clase_numero = numero_grupo * clases_por_grupo + numero_clase
            clase_id = f"C{clase_numero + 1:03d}"
            docente = docentes[clase_numero % cantidad_docentes]
            tipo = "laboratorio" if numero_clase % 4 == 0 else "aula"
            duracion = 2 if numero_clase == 0 else 1
            compatibles = [s for s in salones if s["tipo"] == tipo]
            usados_clase: list[tuple[int, int]] = []
            for repeticion in range(2):
                candidatos = [
                    (dia, inicio, salon)
                    for dia in range(len(dias))
                    for inicio in range(len(horas) - duracion + 1)
                    for salon in compatibles
                    if dia not in {d for d, _ in usados_clase}
                ]
                rng.shuffle(candidatos)
                elegido = None
                for dia, inicio, salon in candidatos:
                    bloques = range(inicio, inicio + duracion)
                    if bloque_institucional in {(dia, b) for b in bloques}:
                        continue
                    if any((grupo["id"], dia, b) in ocupacion_grupo for b in bloques):
                        continue
                    if any((docente["id"], dia, b) in ocupacion_docente for b in bloques):
                        continue
                    if any((salon["id"], dia, b) in ocupacion_salon for b in bloques):
                        continue
                    elegido = (dia, inicio, salon)
                    break
                if elegido is None:
                    raise RuntimeError(f"No se pudo construir el testigo para {clase_id}")
                dia, inicio, salon = elegido
                for bloque in range(inicio, inicio + duracion):
                    ocupacion_grupo.add((grupo["id"], dia, bloque))
                    ocupacion_docente.add((docente["id"], dia, bloque))
                    ocupacion_salon.add((salon["id"], dia, bloque))
                usados_clase.append((dia, inicio))
                testigo.append((dia, inicio, indice_salon[salon["id"]]))
            clase: dict[str, Any] = {
                "id": clase_id,
                "materia": f"Unidad de aprendizaje {clase_numero + 1:03d}",
                "grupo": grupo["id"],
                "docente": docente["id"],
                "sesiones_semana": 2,
                "duracion_bloques": duracion,
                "tipo_salon": tipo,
            }
            # Periodo amplio y compatible: expresa una política, no revela el testigo.
            if clase_numero % 5 == 0:
                permitidos = {
                    (d, h) for d in range(len(dias)) for h in range(len(horas))
                    if (d, h) != bloque_institucional
                }
                clase["periodos_permitidos"] = _mapa_bloques(permitidos, dias, horas)
            clases.append(clase)

    universo = {(d, h) for d in range(len(dias)) for h in range(len(horas))}
    for grupo in grupos:
        ocupados = {(d, h) for g, d, h in ocupacion_grupo if g == grupo["id"]}
        libres = sorted(universo - ocupados - {bloque_institucional})
        rng.shuffle(libres)
        grupo["no_disponible"] = _mapa_bloques(set(libres[:2]), dias, horas)
    for docente in docentes:
        ocupados = {(d, h) for doc, d, h in ocupacion_docente if doc == docente["id"]}
        libres = sorted(universo - ocupados - {bloque_institucional})
        rng.shuffle(libres)
        no_disponibles = set(libres[:2])
        if estres:
            # Puede contradecir el testigo deliberadamente; no se infiere imposibilidad.
            no_disponibles.update(sorted(ocupados)[:1])
        docente["no_disponible"] = _mapa_bloques(no_disponibles, dias, horas)
        docente["preferidos"] = _mapa_bloques(ocupados, dias, horas)

    datos: dict[str, Any] = {
        "dias": dias,
        "horas": horas,
        "salones": salones,
        "grupos": grupos,
        "docentes": docentes,
        "clases": clases,
        "restricciones": {
            "franjas_no_lectivas": _mapa_bloques({bloque_institucional}, dias, horas),
            "umbral_jornada_larga": 7,
        },
        "metadatos": {
            "nombre": especificacion["etiqueta"],
            "tipo": "sintetico_estres" if estres else "sintetico_con_testigo",
            "semilla": semilla,
            "generador": "HorariosGeneticos-Fase4-v1",
            "factibilidad_testigo_validada": not estres,
        },
    }
    problema = problema_desde_datos(deepcopy(datos))
    if not estres:
        evaluacion = evaluar(problema, tuple(testigo))
        if not evaluacion.factible:
            raise AssertionError(
                "El generador produjo un testigo inválido: "
                + "; ".join(evaluacion.razones_no_factible())
            )
    return datos


def cargar_escenario(
    nombre: str,
    base: str | Path,
    semilla: int = 42,
    *,
    ruta_json: str | Path | None = None,
    estres: bool = False,
) -> dict[str, Any]:
    """Carga el ejemplo pequeño, genera un sintético o valida un JSON externo."""
    clave = nombre.lower().strip()
    if clave in {"pequeño", "pequeno", "small"}:
        datos = cargar_datos(Path(base) / "datos" / "ejemplo.json")
    elif clave in {"mediano", "grande"}:
        datos = generar_escenario_sintetico(clave, semilla, estres=estres)
    elif clave in {"json", "personalizado"}:
        if ruta_json is None:
            raise ValueError("Selecciona un archivo JSON para el escenario personalizado")
        datos = cargar_datos(ruta_json)
    else:
        raise ValueError(f"Escenario desconocido: {nombre}")
    validar_datos(datos)
    return datos

