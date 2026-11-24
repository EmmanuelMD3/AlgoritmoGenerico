"""Verificador opcional de factibilidad completa mediante OR-Tools CP-SAT."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .diagnostico import EstadoFactibilidad, candidatos_estaticos
from .fitness import evaluar
from .modelo import Cromosoma, Problema


@dataclass(frozen=True)
class ResultadoVerificacion:
    estado: EstadoFactibilidad
    mensaje: str
    cromosoma: Cromosoma | None = None
    estado_solver: str = "NO_EJECUTADO"
    segundos: float = 0.0
    variables_booleanas: int = 0


def verificar_factibilidad(
    problema: Problema, *, limite_segundos: float = 30.0, trabajadores: int = 1,
) -> ResultadoVerificacion:
    """Modela todas las restricciones duras; sólo INFEASIBLE prueba imposibilidad."""
    if limite_segundos <= 0:
        raise ValueError("El límite del verificador debe ser positivo")
    if trabajadores < 1:
        raise ValueError("El número de trabajadores debe ser positivo")
    inicio = perf_counter()
    dominios = tuple(candidatos_estaticos(problema, i) for i in range(len(problema.sesiones)))
    sin_dominio = [problema.sesiones[i].id for i, dominio in enumerate(dominios) if not dominio]
    if sin_dominio:
        return ResultadoVerificacion(
            EstadoFactibilidad.IMPOSIBILIDAD_DEMOSTRADA,
            "Sesiones sin posición compatible con disponibilidad, franjas y periodos: "
            + ", ".join(sin_dominio),
            estado_solver="PREPROCESAMIENTO", segundos=perf_counter() - inicio,
        )
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return ResultadoVerificacion(
            EstadoFactibilidad.INCONCLUSA,
            "OR-Tools no está instalado. Instálalo en una versión de Python compatible "
            "para ejecutar la verificación independiente.",
            estado_solver="DEPENDENCIA_AUSENTE", segundos=perf_counter() - inicio,
        )

    modelo = cp_model.CpModel()
    variables: dict[tuple[int, int], object] = {}
    for indice, dominio in enumerate(dominios):
        fila = []
        for candidato, _gen in enumerate(dominio):
            variable = modelo.NewBoolVar(f"s{indice}_c{candidato}")
            variables[(indice, candidato)] = variable
            fila.append(variable)
        modelo.AddExactlyOne(fila)

    ocupacion_docente: dict[tuple[str, int, int], list[object]] = {}
    ocupacion_grupo: dict[tuple[str, int, int], list[object]] = {}
    ocupacion_salon: dict[tuple[int, int, int], list[object]] = {}
    for indice, (sesion, dominio) in enumerate(zip(problema.sesiones, dominios)):
        for candidato, (dia, inicio_bloque, salon) in enumerate(dominio):
            variable = variables[(indice, candidato)]
            for bloque in range(inicio_bloque, inicio_bloque + sesion.duracion):
                ocupacion_docente.setdefault((sesion.docente, dia, bloque), []).append(variable)
                ocupacion_grupo.setdefault((sesion.grupo, dia, bloque), []).append(variable)
                ocupacion_salon.setdefault((salon, dia, bloque), []).append(variable)
    for ocupacion in (ocupacion_docente, ocupacion_grupo, ocupacion_salon):
        for fila in ocupacion.values():
            modelo.Add(sum(fila) <= 1)

    def agregar_maximos(ocupacion, entidades, limite_global):
        for entidad_id, entidad in entidades.items():
            limite = entidad.max_horas_consecutivas or limite_global
            if limite is None or limite >= len(problema.horas):
                continue
            for dia in range(len(problema.dias)):
                for inicio_ventana in range(len(problema.horas) - limite):
                    terminos = []
                    for bloque in range(inicio_ventana, inicio_ventana + limite + 1):
                        terminos.extend(ocupacion.get((entidad_id, dia, bloque), ()))
                    if terminos:
                        modelo.Add(sum(terminos) <= limite)

    agregar_maximos(
        ocupacion_grupo, problema.grupos, problema.max_horas_consecutivas_grupo,
    )
    agregar_maximos(
        ocupacion_docente, problema.docentes, problema.max_horas_consecutivas_docente,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(limite_segundos)
    solver.parameters.num_search_workers = int(trabajadores)
    solver.parameters.random_seed = 0
    estado = solver.Solve(modelo)
    nombre_estado = solver.StatusName(estado)
    segundos = perf_counter() - inicio
    cantidad_variables = len(variables)
    if estado in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        genes = []
        for indice, dominio in enumerate(dominios):
            elegido = next(
                candidato for candidato in range(len(dominio))
                if solver.Value(variables[(indice, candidato)])
            )
            genes.append(dominio[elegido])
        cromosoma = tuple(genes)
        evaluacion = evaluar(problema, cromosoma)
        if not evaluacion.factible:
            return ResultadoVerificacion(
                EstadoFactibilidad.INCONCLUSA,
                "CP-SAT devolvió una asignación que el evaluador completo rechazó: "
                + "; ".join(evaluacion.razones_no_factible()),
                cromosoma, nombre_estado, segundos, cantidad_variables,
            )
        return ResultadoVerificacion(
            EstadoFactibilidad.SOLUCION_FACTIBLE,
            "CP-SAT encontró una asignación y el evaluador oficial confirmó cero violaciones duras.",
            cromosoma, nombre_estado, segundos, cantidad_variables,
        )
    if estado == cp_model.INFEASIBLE:
        return ResultadoVerificacion(
            EstadoFactibilidad.IMPOSIBILIDAD_DEMOSTRADA,
            "CP-SAT demostró que el modelo completo de restricciones duras es infactible.",
            estado_solver=nombre_estado, segundos=segundos,
            variables_booleanas=cantidad_variables,
        )
    return ResultadoVerificacion(
        EstadoFactibilidad.INCONCLUSA,
        "El verificador terminó sin solución ni prueba de infactibilidad; "
        "aumentar el tiempo puede cambiar este estado, pero no garantiza una conclusión.",
        estado_solver=nombre_estado, segundos=segundos,
        variables_booleanas=cantidad_variables,
    )
