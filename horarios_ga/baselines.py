"""Métodos de referencia que comparten el modelo y la evaluación del AG."""
from __future__ import annotations

import random
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .fitness import Evaluacion, evaluar
from .modelo import Cromosoma, Gen, Problema


@dataclass(frozen=True)
class ResultadoMetodo:
    metodo: str
    cromosoma: Cromosoma
    evaluacion: Evaluacion
    evaluaciones: int
    duracion: float
    motivo_parada: str
    evaluacion_primera_factible: int | None = None


def _gen_uniforme(problema: Problema, indice: int, rng: random.Random) -> Gen:
    sesion = problema.sesiones[indice]
    return (
        rng.randrange(len(problema.dias)),
        rng.randrange(len(problema.horas) - sesion.duracion + 1),
        rng.choice(problema.salones_validos[indice]),
    )


def _individuo_uniforme(problema: Problema, rng: random.Random) -> Cromosoma:
    return tuple(_gen_uniforme(problema, i, rng) for i in range(len(problema.sesiones)))


def ejecutar_busqueda_aleatoria(
    problema: Problema,
    presupuesto: int,
    semilla: int,
    *,
    debe_cancelar: Callable[[], bool] | None = None,
) -> ResultadoMetodo:
    """Muestrea horarios completos independientes y conserva el mejor."""
    if presupuesto < 1:
        raise ValueError("El presupuesto debe incluir al menos una evaluación completa")
    rng = random.Random(semilla)
    inicio = perf_counter()
    mejor: Cromosoma | None = None
    ev_mejor: Evaluacion | None = None
    primera_factible: int | None = None
    realizadas = 0
    cancelada = False
    for numero in range(1, presupuesto + 1):
        if debe_cancelar is not None and debe_cancelar():
            cancelada = True
            break
        cromosoma = _individuo_uniforme(problema, rng)
        evaluacion = evaluar(problema, cromosoma)
        realizadas = numero
        if primera_factible is None and evaluacion.factible:
            primera_factible = numero
        if ev_mejor is None or evaluacion.prioridad() > ev_mejor.prioridad():
            mejor, ev_mejor = cromosoma, evaluacion
    if mejor is None or ev_mejor is None:
        # La cancelación anterior a la primera evaluación debe quedar explícita.
        cromosoma = _individuo_uniforme(problema, rng)
        ev_mejor = evaluar(problema, cromosoma)
        mejor, realizadas = cromosoma, 1
        primera_factible = 1 if ev_mejor.factible else None
    return ResultadoMetodo(
        "aleatorio", mejor, ev_mejor, realizadas, perf_counter() - inicio,
        "cancelada" if cancelada else "presupuesto_agotado", primera_factible,
    )


def _opciones(problema: Problema, indice: int) -> list[Gen]:
    sesion = problema.sesiones[indice]
    return [
        (dia, inicio, salon)
        for dia in range(len(problema.dias))
        for inicio in range(len(problema.horas) - sesion.duracion + 1)
        for salon in problema.salones_validos[indice]
    ]


def ejecutar_heuristica_constructiva(
    problema: Problema,
    presupuesto: int,
    semilla: int,
    *,
    debe_cancelar: Callable[[], bool] | None = None,
) -> ResultadoMetodo:
    """Construye y refina un horario sin operadores evolutivos.

    Inicializa una asignación válida en dominio, ordena las sesiones por cantidad
    de opciones y fija progresivamente la mejor ubicación observada para cada una.
    Si queda presupuesto repite barridos locales. Cada candidato se compara con la
    misma prioridad lexicográfica del AG y cada evaluación completa se contabiliza.
    """
    if presupuesto < 1:
        raise ValueError("El presupuesto debe incluir al menos una evaluación completa")
    rng = random.Random(semilla)
    inicio = perf_counter()
    opciones = [_opciones(problema, i) for i in range(len(problema.sesiones))]
    orden = sorted(range(len(problema.sesiones)), key=lambda i: (len(opciones[i]), -problema.sesiones[i].duracion, i))
    actual = tuple(rng.choice(opciones[i]) for i in range(len(opciones)))
    ev_actual = evaluar(problema, actual)
    mejor, ev_mejor = actual, ev_actual
    realizadas = 1
    primera_factible = 1 if ev_actual.factible else None
    cancelada = False

    while realizadas < presupuesto:
        hubo_candidato = False
        for indice in orden:
            alternativas = opciones[indice][:]
            rng.shuffle(alternativas)
            mejor_local, ev_local = actual, ev_actual
            for opcion in alternativas:
                if realizadas >= presupuesto:
                    break
                if debe_cancelar is not None and debe_cancelar():
                    cancelada = True
                    break
                genes = list(actual)
                genes[indice] = opcion
                candidato = tuple(genes)
                ev_candidato = evaluar(problema, candidato)
                realizadas += 1
                hubo_candidato = True
                if primera_factible is None and ev_candidato.factible:
                    primera_factible = realizadas
                if ev_candidato.prioridad() > ev_local.prioridad():
                    mejor_local, ev_local = candidato, ev_candidato
                if ev_candidato.prioridad() > ev_mejor.prioridad():
                    mejor, ev_mejor = candidato, ev_candidato
            actual, ev_actual = mejor_local, ev_local
            if cancelada or realizadas >= presupuesto:
                break
        if cancelada or not hubo_candidato:
            break
    return ResultadoMetodo(
        "constructivo", mejor, ev_mejor, realizadas, perf_counter() - inicio,
        "cancelada" if cancelada else "presupuesto_agotado", primera_factible,
    )

