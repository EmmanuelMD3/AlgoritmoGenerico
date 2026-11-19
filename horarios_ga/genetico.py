"""Algoritmo genetico: poblacion, seleccion, cruza, mutacion y elitismo."""
from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean
from time import perf_counter
from typing import Callable

from .fitness import Evaluacion, evaluar, evaluar_detallado
from .modelo import Cromosoma, Gen, Problema


@dataclass(frozen=True)
class Configuracion:
    poblacion: int = 120
    generaciones: int = 200
    prob_cruza: float = 0.85
    prob_mutacion: float = 0.08
    elitismo: int = 4
    torneo: int = 4
    semilla: int = 42
    mutacion_dirigida: float = 0.35
    prob_reparacion: float = 0.25
    inmigrantes: float = 0.03
    parada_sin_mejora: int = 0
    objetivo_penalizacion_blanda: int = 0
    variante: str = "clasico"
    inicializacion_heuristica: bool = False
    porcentaje_inicializacion_heuristica: float = 0.30
    busqueda_local: bool = False
    estrategia_busqueda_local: str = "mejores"
    vecindario_busqueda_local: str = "mixta"
    criterio_busqueda_local: str = "primera"
    frecuencia_busqueda_local: int = 5
    porcentaje_busqueda_local: float = 0.20
    evaluaciones_busqueda_local: int = 12
    mejoras_busqueda_local: int = 2
    mutacion_adaptativa: bool = False
    mutacion_min: float = 0.02
    mutacion_max: float = 0.25
    estancamiento_mutacion: int = 10
    umbral_diversidad: float = 0.25
    factor_incremento_mutacion: float = 1.5
    factor_recuperacion_mutacion: float = 0.85
    presupuesto_evaluaciones: int = 0

    def validar(self) -> None:
        if self.poblacion < 4 or self.generaciones < 1:
            raise ValueError("La poblacion debe ser >= 4 y las generaciones >= 1")
        if not (0 <= self.prob_cruza <= 1 and 0 <= self.prob_mutacion <= 1):
            raise ValueError("Las probabilidades deben estar entre 0 y 1")
        if not (
            0 <= self.mutacion_dirigida <= 1
            and 0 <= self.prob_reparacion <= 1
            and 0 <= self.inmigrantes < 1
        ):
            raise ValueError("Mutación dirigida, reparación e inmigrantes deben estar entre 0 y 1")
        if not (1 <= self.elitismo < self.poblacion):
            raise ValueError("El elitismo debe ser >= 1 y menor que la poblacion")
        if not (2 <= self.torneo <= self.poblacion):
            raise ValueError("El torneo debe ser >= 2 y <= poblacion")
        if self.parada_sin_mejora < 0 or self.objetivo_penalizacion_blanda < 0:
            raise ValueError("La parada sin mejora y el objetivo blando no pueden ser negativos")
        if self.variante not in {"clasico", "hibrido"}:
            raise ValueError("La variante debe ser 'clasico' o 'hibrido'")
        if not 0 <= self.porcentaje_inicializacion_heuristica <= 0.5:
            raise ValueError("La inicialización heurística debe estar entre 0 y 0.5")
        if self.estrategia_busqueda_local not in {"mejores", "aleatoria", "estancamiento"}:
            raise ValueError("Estrategia de búsqueda local desconocida")
        if self.vecindario_busqueda_local not in {"reasignacion", "intercambio", "mixta"}:
            raise ValueError("Vecindario de búsqueda local desconocido")
        if self.criterio_busqueda_local not in {"primera", "mejor"}:
            raise ValueError("El criterio local debe ser 'primera' o 'mejor'")
        if self.frecuencia_busqueda_local < 1 or not 0 < self.porcentaje_busqueda_local <= 1:
            raise ValueError("Frecuencia y proporción de búsqueda local no válidas")
        if self.evaluaciones_busqueda_local < 1 or self.mejoras_busqueda_local < 1:
            raise ValueError("Los límites de búsqueda local deben ser positivos")
        if not 0 <= self.mutacion_min <= self.mutacion_max <= 1:
            raise ValueError("Los límites de mutación deben estar ordenados entre 0 y 1")
        if self.mutacion_adaptativa and not self.mutacion_min <= self.prob_mutacion <= self.mutacion_max:
            raise ValueError("Con adaptación, la mutación base debe quedar entre mínimo y máximo")
        if self.estancamiento_mutacion < 1 or not 0 <= self.umbral_diversidad <= 1:
            raise ValueError("Umbrales adaptativos no válidos")
        if self.factor_incremento_mutacion <= 1 or not 0 < self.factor_recuperacion_mutacion < 1:
            raise ValueError("Los factores adaptativos deben aumentar (>1) y recuperar (0..1)")
        if self.presupuesto_evaluaciones < 0:
            raise ValueError("El presupuesto de evaluaciones no puede ser negativo")
        if 0 < self.presupuesto_evaluaciones < self.poblacion:
            raise ValueError("El presupuesto debe ser cero o al menos igual a la población")


@dataclass(frozen=True)
class Registro:
    generacion: int
    mejor_fitness: int
    media_fitness: float
    conflictos_duros: int
    huecos: int
    factible: bool
    penalizacion_blanda: int = 0
    diversidad: float = 0.0
    prob_mutacion_usada: float = 0.0
    evaluaciones_acumuladas: int = 0
    aplicaciones_busqueda_local: int = 0
    mejoras_busqueda_local: int = 0
    individuos_mejorados_busqueda_local: int = 0
    mejoro_global: bool = False
    estancada: bool = False


@dataclass(frozen=True)
class EstadisticasEjecucion:
    variante: str = "clasico"
    individuos_aleatorios: int = 0
    individuos_heuristicos: int = 0
    evaluaciones_totales: int = 0
    evaluaciones_inicializacion: int = 0
    evaluaciones_busqueda_local: int = 0
    aplicaciones_busqueda_local: int = 0
    mejoras_busqueda_local: int = 0
    individuos_mejorados_busqueda_local: int = 0
    mejora_duras_busqueda_local: int = 0
    mejora_blanda_busqueda_local: int = 0
    tiempo_inicializacion: float = 0.0
    tiempo_evolucion: float = 0.0
    tiempo_busqueda_local: float = 0.0


@dataclass(frozen=True)
class Resultado:
    cromosoma: Cromosoma
    evaluacion: Evaluacion
    inicial: Evaluacion
    historial: tuple[Registro, ...]
    configuracion: Configuracion
    motivo_parada: str = "generaciones_completadas"
    estadisticas: EstadisticasEjecucion = EstadisticasEjecucion()


class PresupuestoAgotado(RuntimeError):
    """Señal interna para no sobrepasar el máximo de evaluaciones."""


class EjecucionCancelada(RuntimeError):
    """Cancelación cooperativa que conserva el mejor resultado disponible."""

    def __init__(self, resultado: Resultado):
        super().__init__("La ejecución fue cancelada por el usuario")
        self.resultado = resultado


def gen_aleatorio(problema: Problema, idx: int, rng: random.Random) -> Gen:
    sesion = problema.sesiones[idx]

    def candidato() -> Gen:
        return (
            rng.randrange(len(problema.dias)),
            rng.randrange(len(problema.horas) - sesion.duracion + 1),
            rng.choice(problema.salones_validos[idx]),
        )

    def violaciones_estaticas(gen: Gen) -> int:
        dia, inicio, _salon = gen
        docente = problema.docentes[sesion.docente]
        grupo = problema.grupos[sesion.grupo]
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

    # Un pequeño muestreo evita restricciones estáticas cuando hay alternativa,
    # pero no declara imposible un caso sin posiciones perfectas.
    candidatos = [candidato() for _ in range(6)]
    return min(candidatos, key=violaciones_estaticas)


def individuo_aleatorio(problema: Problema, rng: random.Random) -> Cromosoma:
    return tuple(gen_aleatorio(problema, i, rng) for i in range(len(problema.sesiones)))


def cruzar(a: Cromosoma, b: Cromosoma, rng: random.Random) -> tuple[Cromosoma, Cromosoma]:
    # Cruza uniforme. La identidad de cada sesion nunca se cambia.
    mascara = [rng.random() < 0.5 for _ in a]
    return (
        tuple(x if flag else y for x, y, flag in zip(a, b, mascara)),
        tuple(y if flag else x for x, y, flag in zip(a, b, mascara)),
    )


def mutar(
    problema: Problema,
    cromosoma: Cromosoma,
    prob_mutacion: float,
    rng: random.Random,
    prob_dirigida: float = 0.0,
    al_evaluar: Callable[[Evaluacion], None] | None = None,
    evaluador_detallado: Callable[[Cromosoma], tuple[Evaluacion, frozenset[int]]] | None = None,
) -> Cromosoma:
    genes = list(cromosoma)
    forzados: set[int] = set()
    if prob_dirigida > 0 and rng.random() < prob_dirigida:
        evaluacion, indices = (
            evaluador_detallado(cromosoma)
            if evaluador_detallado is not None
            else evaluar_detallado(problema, cromosoma)
        )
        if al_evaluar is not None and evaluador_detallado is None:
            al_evaluar(evaluacion)
        conflictivos = tuple(indices)
        if conflictivos:
            forzados.add(rng.choice(conflictivos))
    for idx, (dia, hora, salon) in enumerate(genes):
        if idx not in forzados and rng.random() >= prob_mutacion:
            continue
        tipo = rng.choice(("dia", "hora", "salon", "completo"))
        nuevo = gen_aleatorio(problema, idx, rng)
        if tipo == "dia":
            genes[idx] = (nuevo[0], hora, salon)
        elif tipo == "hora":
            genes[idx] = (dia, nuevo[1], salon)
        elif tipo == "salon":
            genes[idx] = (dia, hora, nuevo[2])
        else:
            genes[idx] = nuevo
    return tuple(genes)


def reparar_individuo(
    problema: Problema,
    cromosoma: Cromosoma,
    rng: random.Random,
    intentos: int = 3,
    al_evaluar: Callable[[Evaluacion], None] | None = None,
    evaluador: Callable[[Cromosoma], Evaluacion] | None = None,
    evaluador_detallado: Callable[[Cromosoma], tuple[Evaluacion, frozenset[int]]] | None = None,
) -> Cromosoma:
    """Prueba reasignaciones locales y sólo conserva mejoras lexicográficas."""
    mejor = cromosoma
    ev_mejor, conflictivos = (
        evaluador_detallado(mejor)
        if evaluador_detallado is not None
        else evaluar_detallado(problema, mejor)
    )
    if al_evaluar is not None and evaluador_detallado is None:
        al_evaluar(ev_mejor)
    if not conflictivos:
        return mejor
    objetivos = list(conflictivos)
    rng.shuffle(objetivos)
    for idx in objetivos[:intentos]:
        for _ in range(3):
            genes = list(mejor)
            genes[idx] = gen_aleatorio(problema, idx, rng)
            candidato = tuple(genes)
            ev_candidato = evaluador(candidato) if evaluador is not None else evaluar(problema, candidato)
            if al_evaluar is not None and evaluador is None:
                al_evaluar(ev_candidato)
            if ev_candidato.prioridad() > ev_mejor.prioridad():
                mejor, ev_mejor = candidato, ev_candidato
                break
    return mejor


def ejecutar(
    problema: Problema,
    config: Configuracion = Configuracion(),
    callback: Callable[[Registro], None] | None = None,
    debe_cancelar: Callable[[], bool] | None = None,
    al_evaluar: Callable[[Evaluacion], None] | None = None,
    callback_instantanea: Callable[[object], None] | None = None,
    capturar_cada: int = 1,
    esperar_si_pausado: Callable[[], float] | None = None,
) -> Resultado:
    """Ejecuta el algoritmo y notifica de forma opcional al terminar cada generación.

    Los callbacks se invocan desde el mismo hilo que llama a esta
    función. La capa de presentación es responsable de trasladar notificaciones a
    su hilo principal. ``al_evaluar`` sólo instrumenta evaluaciones completas y no
    participa en la prioridad ni en los operadores. La cancelación se consulta
    entre generaciones y nunca interrumpe una operación.
    """
    config.validar()
    if capturar_cada < 1:
        raise ValueError("La frecuencia de captura debe ser al menos una generación")
    from .hibrido import busqueda_local, individuo_constructivo, tasa_mutacion_adaptativa

    inicio_calculo = perf_counter()
    tiempo_artificial = 0.0
    tiempo_local = 0.0
    rng = random.Random(config.semilla)
    modo_hibrido = config.variante == "hibrido"
    cantidad_heuristica = (
        round(config.poblacion * config.porcentaje_inicializacion_heuristica)
        if modo_hibrido and config.inicializacion_heuristica else 0
    )
    cantidad_aleatoria = config.poblacion - cantidad_heuristica
    if modo_hibrido:
        poblacion = [individuo_aleatorio(problema, rng) for _ in range(cantidad_aleatoria)]
        vistos = set(poblacion)
        for _ in range(cantidad_heuristica):
            candidato = individuo_constructivo(problema, rng)
            for _reintento in range(8):
                if candidato not in vistos:
                    break
                candidato = individuo_constructivo(problema, rng)
            poblacion.append(candidato)
            vistos.add(candidato)
        rng.shuffle(poblacion)
    else:
        # Mantener exactamente la ruta pseudoaleatoria histórica del modo clásico.
        poblacion = [individuo_aleatorio(problema, rng) for _ in range(config.poblacion)]
    muestra_inicial = tuple(poblacion[0])
    tiempo_construccion = perf_counter() - inicio_calculo
    cache: dict[Cromosoma, Evaluacion] = {}
    evaluaciones_totales = 0
    evaluaciones_inicializacion = 0
    evaluaciones_locales = 0
    aplicaciones_locales = 0
    mejoras_locales = 0
    individuos_mejorados_locales = 0
    mejora_duras_local = 0
    mejora_blanda_local = 0

    def registrar(evaluacion: Evaluacion) -> Evaluacion:
        nonlocal evaluaciones_totales
        if config.presupuesto_evaluaciones and evaluaciones_totales >= config.presupuesto_evaluaciones:
            raise PresupuestoAgotado
        evaluaciones_totales += 1
        if al_evaluar is not None:
            al_evaluar(evaluacion)
        return evaluacion

    def eval_cache(c: Cromosoma) -> Evaluacion:
        if c not in cache:
            if config.presupuesto_evaluaciones and evaluaciones_totales >= config.presupuesto_evaluaciones:
                raise PresupuestoAgotado
            cache[c] = registrar(evaluar(problema, c))
        return cache[c]

    def eval_detallado(c: Cromosoma) -> tuple[Evaluacion, frozenset[int]]:
        if config.presupuesto_evaluaciones and evaluaciones_totales >= config.presupuesto_evaluaciones:
            raise PresupuestoAgotado
        evaluacion, indices = evaluar_detallado(problema, c)
        registrar(evaluacion)
        cache[c] = evaluacion
        return evaluacion, indices

    inicial = max((eval_cache(c) for c in poblacion), key=lambda ev: ev.prioridad())
    evaluaciones_inicializacion = evaluaciones_totales
    tiempo_inicializacion = perf_counter() - inicio_calculo
    historial: list[Registro] = []
    mejor_prioridad: tuple[int, int, int] | None = None
    mejor_global: Cromosoma | None = None
    evaluacion_global: Evaluacion | None = None
    ultima_mejora = 0
    primera_generacion_factible: int | None = None
    tasa_mutacion = config.prob_mutacion
    aplicaciones_ultima = 0
    mejoras_ultima = 0
    individuos_mejorados_ultima = 0

    def resultado_actual(cromosoma: Cromosoma, evaluacion: Evaluacion, motivo: str) -> Resultado:
        tiempo_total = perf_counter() - inicio_calculo - tiempo_artificial
        estadisticas = EstadisticasEjecucion(
            variante=config.variante,
            individuos_aleatorios=cantidad_aleatoria,
            individuos_heuristicos=cantidad_heuristica,
            evaluaciones_totales=evaluaciones_totales,
            evaluaciones_inicializacion=evaluaciones_inicializacion,
            evaluaciones_busqueda_local=evaluaciones_locales,
            aplicaciones_busqueda_local=aplicaciones_locales,
            mejoras_busqueda_local=mejoras_locales,
            individuos_mejorados_busqueda_local=individuos_mejorados_locales,
            mejora_duras_busqueda_local=mejora_duras_local,
            mejora_blanda_busqueda_local=mejora_blanda_local,
            tiempo_inicializacion=tiempo_inicializacion,
            tiempo_evolucion=max(0.0, tiempo_total - tiempo_inicializacion - tiempo_local),
            tiempo_busqueda_local=tiempo_local,
        )
        return Resultado(cromosoma, evaluacion, inicial, tuple(historial), config, motivo, estadisticas)

    try:
        for generacion in range(config.generaciones + 1):
            orden = sorted(poblacion, key=lambda c: eval_cache(c).prioridad(), reverse=True)
            mejor = orden[0]
            ev_mejor = eval_cache(mejor)
            mejoro_global = mejor_prioridad is None or ev_mejor.prioridad() > mejor_prioridad
            if mejoro_global:
                mejor_prioridad = ev_mejor.prioridad()
                mejor_global, evaluacion_global = mejor, ev_mejor
                ultima_mejora = generacion
            diversidad = len(set(poblacion)) / len(poblacion)
            generaciones_sin_mejora = generacion - ultima_mejora
            if modo_hibrido and config.mutacion_adaptativa:
                tasa_mutacion = tasa_mutacion_adaptativa(
                    tasa_mutacion, config.prob_mutacion, config.mutacion_min,
                    config.mutacion_max, generaciones_sin_mejora,
                    config.estancamiento_mutacion, diversidad, config.umbral_diversidad,
                    config.factor_incremento_mutacion, config.factor_recuperacion_mutacion,
                )
            registro = Registro(
                generacion=generacion,
                mejor_fitness=ev_mejor.fitness,
                media_fitness=mean(eval_cache(c).fitness for c in poblacion),
                conflictos_duros=ev_mejor.duras,
                huecos=ev_mejor.huecos,
                factible=ev_mejor.factible,
                penalizacion_blanda=ev_mejor.penalizacion_blanda,
                diversidad=diversidad,
                prob_mutacion_usada=tasa_mutacion,
                evaluaciones_acumuladas=evaluaciones_totales,
                aplicaciones_busqueda_local=aplicaciones_ultima,
                mejoras_busqueda_local=mejoras_ultima,
                individuos_mejorados_busqueda_local=individuos_mejorados_ultima,
                mejoro_global=mejoro_global,
                estancada=generaciones_sin_mejora >= config.estancamiento_mutacion,
            )
            historial.append(registro)
            if primera_generacion_factible is None and ev_mejor.factible:
                primera_generacion_factible = generacion
            if callback is not None:
                callback(registro)
            cancelar_ahora = debe_cancelar is not None and debe_cancelar()
            calidad_alcanzada = ev_mejor.factible and ev_mejor.penalizacion_blanda <= config.objetivo_penalizacion_blanda
            termina_calidad = (
                config.parada_sin_mejora > 0 and calidad_alcanzada
                and generaciones_sin_mejora >= config.parada_sin_mejora
            )
            es_ultima = generacion == config.generaciones
            debe_capturar = callback_instantanea is not None and (
                generacion == 0 or generacion % capturar_cada == 0
                or cancelar_ahora or termina_calidad or es_ultima
            )
            if debe_capturar:
                from .evolucion import crear_instantanea

                callback_instantanea(crear_instantanea(
                    problema, generacion, mejor, mejor_global or mejor,
                    ev_mejor, evaluacion_global or ev_mejor, registro,
                    perf_counter() - inicio_calculo - tiempo_artificial,
                    muestra_inicial=muestra_inicial if generacion == 0 else None,
                    primera_generacion_factible=primera_generacion_factible,
                    evaluador_detallado=eval_detallado,
                ))
            if cancelar_ahora:
                raise EjecucionCancelada(resultado_actual(mejor_global or mejor, evaluacion_global or ev_mejor, "cancelada"))
            if termina_calidad:
                return resultado_actual(mejor_global or mejor, evaluacion_global or ev_mejor, "calidad_sin_mejora")
            if es_ultima:
                return resultado_actual(mejor_global or mejor, evaluacion_global or ev_mejor, "generaciones_completadas")

            if esperar_si_pausado is not None:
                tiempo_artificial += max(0.0, esperar_si_pausado())
                if debe_cancelar is not None and debe_cancelar():
                    raise EjecucionCancelada(resultado_actual(mejor_global or mejor, evaluacion_global or ev_mejor, "cancelada"))

            nueva = list(orden[: config.elitismo])

            def seleccionar() -> Cromosoma:
                candidatos = rng.sample(poblacion, k=config.torneo)
                return max(candidatos, key=lambda c: eval_cache(c).prioridad())

            while len(nueva) < config.poblacion:
                padre_a, padre_b = seleccionar(), seleccionar()
                if rng.random() < config.prob_cruza:
                    hijo_a, hijo_b = cruzar(padre_a, padre_b, rng)
                else:
                    hijo_a, hijo_b = padre_a, padre_b
                hijo_a = mutar(
                    problema, hijo_a, tasa_mutacion, rng, config.mutacion_dirigida,
                    evaluador_detallado=eval_detallado,
                )
                if rng.random() < config.prob_reparacion:
                    hijo_a = reparar_individuo(
                        problema, hijo_a, rng, evaluador=eval_cache,
                        evaluador_detallado=eval_detallado,
                    )
                nueva.append(hijo_a)
                if len(nueva) < config.poblacion:
                    hijo_b = mutar(
                        problema, hijo_b, tasa_mutacion, rng, config.mutacion_dirigida,
                        evaluador_detallado=eval_detallado,
                    )
                    if rng.random() < config.prob_reparacion:
                        hijo_b = reparar_individuo(
                            problema, hijo_b, rng, evaluador=eval_cache,
                            evaluador_detallado=eval_detallado,
                        )
                    nueva.append(hijo_b)
            cantidad_inmigrantes = min(
                config.poblacion - config.elitismo,
                round(config.poblacion * config.inmigrantes),
            )
            for desplazamiento in range(cantidad_inmigrantes):
                nueva[-1 - desplazamiento] = individuo_aleatorio(problema, rng)

            aplicaciones_ultima = 0
            mejoras_ultima = 0
            individuos_mejorados_ultima = 0
            aplicar_local = modo_hibrido and config.busqueda_local and (
                (generacion + 1) % config.frecuencia_busqueda_local == 0
            )
            if config.estrategia_busqueda_local == "estancamiento":
                aplicar_local = aplicar_local and generaciones_sin_mejora >= config.estancamiento_mutacion
            if aplicar_local:
                cantidad = max(1, round(config.poblacion * config.porcentaje_busqueda_local))
                if config.estrategia_busqueda_local == "aleatoria":
                    indices_locales = rng.sample(range(len(nueva)), k=min(cantidad, len(nueva)))
                else:
                    orden_indices = sorted(
                        range(len(nueva)), key=lambda i: eval_cache(nueva[i]).prioridad(), reverse=True,
                    )
                    indices_locales = orden_indices[:cantidad]
                inicio_local = perf_counter()
                for indice in indices_locales:
                    antes = evaluaciones_totales
                    resultado_local = busqueda_local(
                        problema, nueva[indice], eval_cache, rng,
                        vecindario=config.vecindario_busqueda_local,
                        criterio=config.criterio_busqueda_local,
                        max_evaluaciones=config.evaluaciones_busqueda_local,
                        max_mejoras=config.mejoras_busqueda_local,
                        debe_cancelar=debe_cancelar,
                        contador_evaluaciones=lambda: evaluaciones_totales,
                    )
                    nueva[indice] = resultado_local.cromosoma
                    aplicaciones_locales += 1
                    aplicaciones_ultima += 1
                    mejoras_locales += resultado_local.mejoras
                    mejoras_ultima += resultado_local.mejoras
                    if resultado_local.mejoras:
                        individuos_mejorados_locales += 1
                        individuos_mejorados_ultima += 1
                    evaluaciones_locales += evaluaciones_totales - antes
                    mejora_duras_local += resultado_local.mejora_duras
                    mejora_blanda_local += resultado_local.mejora_blanda
                tiempo_local += perf_counter() - inicio_local
            poblacion = nueva
    except PresupuestoAgotado:
        if mejor_global is None or evaluacion_global is None:
            raise RuntimeError("El presupuesto no alcanzó para evaluar la población inicial")
        return resultado_actual(mejor_global, evaluacion_global, "presupuesto_evaluaciones")

    raise AssertionError("Iteración inesperadamente finalizada")
