"""Operadores opcionales del algoritmo memético/híbrido.

Este módulo no conoce escenarios de prueba ni soluciones testigo.  Sus decisiones
usan exclusivamente el :class:`Problema`, un generador pseudoaleatorio y la misma
evaluación lexicográfica que el algoritmo clásico.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import combinations
from typing import Callable

from .diagnostico import candidatos_estaticos
from .fitness import Evaluacion
from .modelo import Cromosoma, Gen, Problema


Evaluador = Callable[[Cromosoma], Evaluacion]
EvaluadorDetallado = Callable[[Cromosoma], tuple[Evaluacion, frozenset[int]]]


@dataclass(frozen=True)
class ResultadoBusquedaLocal:
    cromosoma: Cromosoma
    evaluacion: Evaluacion
    evaluaciones: int
    mejoras: int
    mejora_duras: int
    mejora_blanda: int


def _penalizacion_estatica(problema: Problema, indice: int, gen: Gen) -> int:
    sesion = problema.sesiones[indice]
    docente = problema.docentes[sesion.docente]
    grupo = problema.grupos[sesion.grupo]
    dia, inicio, _salon = gen
    return sum(
        (dia, bloque) in docente.no_disponible
        or (dia, bloque) in grupo.no_disponible
        or (dia, bloque) in problema.franjas_no_lectivas
        or (
            sesion.periodos_permitidos is not None
            and (dia, bloque) not in sesion.periodos_permitidos
        )
        for bloque in range(inicio, inicio + sesion.duracion)
    )


def _colisiones_parciales(
    problema: Problema, indice: int, gen: Gen, asignados: dict[int, Gen],
) -> int:
    sesion = problema.sesiones[indice]
    dia, inicio, salon = gen
    bloques = set(range(inicio, inicio + sesion.duracion))
    total = 0
    for otro_indice, (otro_dia, otro_inicio, otro_salon) in asignados.items():
        if dia != otro_dia:
            continue
        otra = problema.sesiones[otro_indice]
        if not bloques.intersection(range(otro_inicio, otro_inicio + otra.duracion)):
            continue
        total += int(sesion.docente == otra.docente)
        total += int(sesion.grupo == otra.grupo)
        total += int(salon == otro_salon)
    return total


def individuo_constructivo(problema: Problema, rng: random.Random) -> Cromosoma:
    """Construye un individuo diverso minimizando conflictos parciales visibles."""
    asignados: dict[int, Gen] = {}
    indices = list(range(len(problema.sesiones)))
    # Primero sesiones largas y con menos salones; el desempate aleatorio evita
    # que toda la fracción heurística sea idéntica.
    rng.shuffle(indices)
    indices.sort(key=lambda i: (
        problema.sesiones[i].duracion, -len(problema.salones_validos[i]),
    ), reverse=True)
    for indice in indices:
        sesion = problema.sesiones[indice]
        candidatos = [
            (dia, inicio, salon)
            for dia in range(len(problema.dias))
            for inicio in range(len(problema.horas) - sesion.duracion + 1)
            for salon in problema.salones_validos[indice]
        ]
        rng.shuffle(candidatos)
        candidatos.sort(key=lambda gen: (
            _penalizacion_estatica(problema, indice, gen),
            _colisiones_parciales(problema, indice, gen, asignados),
        ))
        # Elegir entre los mejores empates conserva diversidad sin aceptar una
        # opción objetivamente peor en las dos señales constructivas.
        mejor_clave = (
            _penalizacion_estatica(problema, indice, candidatos[0]),
            _colisiones_parciales(problema, indice, candidatos[0], asignados),
        )
        mejores = [
            gen for gen in candidatos
            if (
                _penalizacion_estatica(problema, indice, gen),
                _colisiones_parciales(problema, indice, gen, asignados),
            ) == mejor_clave
        ]
        asignados[indice] = rng.choice(mejores)
    return tuple(asignados[i] for i in range(len(problema.sesiones)))


def tasa_mutacion_adaptativa(
    actual: float,
    base: float,
    minimo: float,
    maximo: float,
    generaciones_sin_mejora: int,
    umbral_estancamiento: int,
    diversidad: float,
    umbral_diversidad: float,
    factor_incremento: float,
    factor_recuperacion: float,
) -> float:
    """Aumenta exploración ante estancamiento/baja diversidad y vuelve a la base."""
    tension = 0
    if umbral_estancamiento > 0 and generaciones_sin_mejora >= umbral_estancamiento:
        tension += 1
    if diversidad < umbral_diversidad:
        tension += 1
    if tension:
        nueva = actual * (factor_incremento ** tension)
    elif actual > base:
        nueva = max(base, actual * factor_recuperacion)
    elif actual < base:
        nueva = min(base, actual / factor_recuperacion)
    else:
        nueva = actual
    return min(maximo, max(minimo, nueva))


def _impacto_colisiones(
    problema: Problema, cromosoma: Cromosoma, indice: int, gen: Gen,
) -> int:
    """Ordena dominios por colisiones directas sin sustituir la evaluación oficial."""
    sesion = problema.sesiones[indice]
    dia, inicio, salon = gen
    bloques = set(range(inicio, inicio + sesion.duracion))
    total = 0
    for otro_indice, (otro_dia, otro_inicio, otro_salon) in enumerate(cromosoma):
        if otro_indice == indice or otro_dia != dia:
            continue
        otra = problema.sesiones[otro_indice]
        solapamiento = len(bloques.intersection(
            range(otro_inicio, otro_inicio + otra.duracion),
        ))
        if not solapamiento:
            continue
        total += solapamiento * (
            int(sesion.docente == otra.docente)
            + int(sesion.grupo == otra.grupo)
            + int(salon == otro_salon)
        )
    return total


def _bloqueadores(
    problema: Problema, cromosoma: Cromosoma, indice: int, gen: Gen,
) -> tuple[int, ...]:
    sesion = problema.sesiones[indice]
    dia, inicio, salon = gen
    bloques = set(range(inicio, inicio + sesion.duracion))
    resultado = []
    for otro_indice, (otro_dia, otro_inicio, otro_salon) in enumerate(cromosoma):
        if otro_indice == indice or otro_dia != dia:
            continue
        otra = problema.sesiones[otro_indice]
        if not bloques.intersection(range(otro_inicio, otro_inicio + otra.duracion)):
            continue
        if (
            sesion.docente == otra.docente
            or sesion.grupo == otra.grupo
            or salon == otro_salon
        ):
            resultado.append(otro_indice)
    return tuple(resultado)


def reparar_dirigido_avanzado(
    problema: Problema,
    cromosoma: Cromosoma,
    rng: random.Random,
    *,
    evaluador: Evaluador,
    evaluador_detallado: EvaluadorDetallado,
    max_evaluaciones: int = 6,
    max_mejoras: int = 2,
    dominios_estaticos: tuple[tuple[Gen, ...], ...] | None = None,
    priorizar_impacto: bool = False,
) -> Cromosoma:
    """Repara dominios críticos y permite una cadena de expulsión de dos genes.

    A diferencia de la reparación histórica, no prueba tres posiciones al azar.
    Primero examina posiciones estáticamente válidas con menor colisión directa;
    si ninguna mejora por sí sola, reubica también un bloqueador. Toda aceptación
    se decide con la evaluación completa y la prioridad lexicográfica oficial.
    """
    actual = cromosoma
    ev_actual, conflictivos = evaluador_detallado(actual)
    evaluaciones = 0
    mejoras = 0
    while conflictivos and evaluaciones < max_evaluaciones and mejoras < max_mejoras:
        def dominio_de(indice: int) -> tuple[Gen, ...]:
            return (
                dominios_estaticos[indice]
                if dominios_estaticos is not None else candidatos_estaticos(problema, indice)
            )

        objetivos = list(conflictivos)
        rng.shuffle(objetivos)
        if priorizar_impacto:
            # El pulido ocasional del élite puede pagar este análisis global.
            objetivos.sort(key=lambda i: (
                min(
                    (_impacto_colisiones(problema, actual, i, gen) for gen in dominio_de(i)),
                    default=10**9,
                ),
                len(dominio_de(i)),
            ))
        else:
            # Los descendientes usan la versión barata en cada reproducción.
            objetivos.sort(key=lambda i: len(dominio_de(i)))
        mejor_par: tuple[Cromosoma, Evaluacion] | None = None
        candidatos_objetivo: dict[int, list[Gen]] = {}
        for indice in objetivos[:min(4, len(objetivos))]:
            dominio = list(dominio_de(indice))
            rng.shuffle(dominio)
            dominio.sort(key=lambda gen: _impacto_colisiones(
                problema, actual, indice, gen,
            ))
            candidatos_objetivo[indice] = dominio
            # El orden local es barato; sólo los dos candidatos más prometedores
            # pasan por la evaluación completa para no consumir el presupuesto
            # en decenas de variantes casi equivalentes.
            for gen in dominio[:2]:
                if evaluaciones >= max_evaluaciones:
                    break
                if gen == actual[indice]:
                    continue
                genes = list(actual)
                genes[indice] = gen
                candidato = tuple(genes)
                ev_candidato = evaluador(candidato)
                evaluaciones += 1
                if ev_candidato.prioridad() <= ev_actual.prioridad():
                    continue
                if mejor_par is None or ev_candidato.prioridad() > mejor_par[1].prioridad():
                    mejor_par = (candidato, ev_candidato)
            if mejor_par is not None or evaluaciones >= max_evaluaciones:
                break

        if mejor_par is None and evaluaciones < max_evaluaciones:
            # Una meseta dura suele requerir liberar el recurso de destino. Se
            # limita a un bloqueador para mantener el presupuesto controlado.
            for indice in objetivos[:min(3, len(objetivos))]:
                for gen in candidatos_objetivo.get(indice, ())[:2]:
                    bloqueadores = _bloqueadores(problema, actual, indice, gen)
                    if len(bloqueadores) != 1:
                        continue
                    bloqueador = bloqueadores[0]
                    intermedio = list(actual)
                    intermedio[indice] = gen
                    dominio_bloqueador = list(dominio_de(bloqueador))
                    rng.shuffle(dominio_bloqueador)
                    dominio_bloqueador.sort(key=lambda candidato: _impacto_colisiones(
                        problema, tuple(intermedio), bloqueador, candidato,
                    ))
                    for reemplazo in dominio_bloqueador[:2]:
                        if evaluaciones >= max_evaluaciones:
                            break
                        if reemplazo == actual[bloqueador]:
                            continue
                        genes = list(intermedio)
                        genes[bloqueador] = reemplazo
                        candidato = tuple(genes)
                        ev_candidato = evaluador(candidato)
                        evaluaciones += 1
                        if ev_candidato.prioridad() <= ev_actual.prioridad():
                            continue
                        if mejor_par is None or ev_candidato.prioridad() > mejor_par[1].prioridad():
                            mejor_par = (candidato, ev_candidato)
                    if mejor_par is not None or evaluaciones >= max_evaluaciones:
                        break
                if mejor_par is not None or evaluaciones >= max_evaluaciones:
                    break

        if mejor_par is None:
            break
        actual, ev_actual = mejor_par
        mejoras += 1
        if ev_actual.factible:
            break
        ev_actual, conflictivos = evaluador_detallado(actual)
    return actual


def busqueda_local(
    problema: Problema,
    cromosoma: Cromosoma,
    evaluador: Evaluador,
    rng: random.Random,
    *,
    vecindario: str = "mixta",
    criterio: str = "primera",
    max_evaluaciones: int = 12,
    max_mejoras: int = 2,
    debe_cancelar: Callable[[], bool] | None = None,
    contador_evaluaciones: Callable[[], int] | None = None,
) -> ResultadoBusquedaLocal:
    """Descenso local por reasignación y/o intercambio, sin aceptar retrocesos."""
    inicial = evaluador(cromosoma)
    mejor, ev_mejor = cromosoma, inicial
    mejoras = 0
    contador_inicial = contador_evaluaciones() if contador_evaluaciones else 0
    intentos = 0

    while intentos < max_evaluaciones and mejoras < max_mejoras:
        if debe_cancelar is not None and debe_cancelar():
            break
        vecinos: list[Cromosoma] = []
        indices = list(range(len(mejor)))
        rng.shuffle(indices)
        if vecindario in {"reasignacion", "mixta"}:
            for indice in indices:
                sesion = problema.sesiones[indice]
                gen = (
                    rng.randrange(len(problema.dias)),
                    rng.randrange(len(problema.horas) - sesion.duracion + 1),
                    rng.choice(problema.salones_validos[indice]),
                )
                genes = list(mejor)
                genes[indice] = gen
                vecinos.append(tuple(genes))
        if vecindario in {"intercambio", "mixta"}:
            pares = list(combinations(indices, 2))
            rng.shuffle(pares)
            for a, b in pares[:max(1, len(indices))]:
                genes = list(mejor)
                genes[a], genes[b] = genes[b], genes[a]
                candidato = tuple(genes)
                if problema.gen_valido(a, candidato[a]) and problema.gen_valido(b, candidato[b]):
                    vecinos.append(candidato)
        rng.shuffle(vecinos)

        elegido: tuple[Cromosoma, Evaluacion] | None = None
        for vecino in vecinos:
            if intentos >= max_evaluaciones:
                break
            if debe_cancelar is not None and debe_cancelar():
                break
            intentos += 1
            ev_vecino = evaluador(vecino)
            if ev_vecino.prioridad() <= ev_mejor.prioridad():
                continue
            if criterio == "primera":
                elegido = (vecino, ev_vecino)
                break
            if elegido is None or ev_vecino.prioridad() > elegido[1].prioridad():
                elegido = (vecino, ev_vecino)
        if elegido is None:
            break
        mejor, ev_mejor = elegido
        mejoras += 1

    evaluaciones = (
        contador_evaluaciones() - contador_inicial
        if contador_evaluaciones else intentos
    )
    return ResultadoBusquedaLocal(
        mejor, ev_mejor, evaluaciones, mejoras,
        max(0, inicial.duras - ev_mejor.duras),
        max(0, inicial.penalizacion_blanda - ev_mejor.penalizacion_blanda),
    )
