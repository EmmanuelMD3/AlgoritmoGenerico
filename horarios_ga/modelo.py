"""Representacion del problema academico y de los cromosomas."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Salon:
    id: str
    capacidad: int
    tipo: str


@dataclass(frozen=True)
class Grupo:
    id: str
    alumnos: int
    no_disponible: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    max_horas_consecutivas: int | None = None


@dataclass(frozen=True)
class Docente:
    id: str
    nombre: str
    # (indice_del_dia, indice_de_la_hora) que NO puede impartir clase.
    no_disponible: frozenset[tuple[int, int]]
    # Si no está vacío, cada bloque fuera de estas franjas recibe penalización blanda.
    preferidos: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    max_horas_consecutivas: int | None = None


@dataclass(frozen=True)
class Sesion:
    id: str
    materia: str
    grupo: str
    docente: str
    duracion: int  # numero de bloques horarios consecutivos
    tipo_salon: str
    clase_id: str = ""
    # None significa cualquier periodo; un conjunto explícito limita cada bloque ocupado.
    periodos_permitidos: frozenset[tuple[int, int]] | None = None


# Dia, primera hora y salon, expresados como indices en el problema.
Gen = tuple[int, int, int]
Cromosoma = tuple[Gen, ...]


@dataclass(frozen=True)
class Problema:
    dias: tuple[str, ...]
    horas: tuple[str, ...]
    salones: tuple[Salon, ...]
    grupos: dict[str, Grupo]
    docentes: dict[str, Docente]
    sesiones: tuple[Sesion, ...]
    salones_validos: tuple[tuple[int, ...], ...]
    franjas_no_lectivas: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    max_horas_consecutivas_grupo: int | None = None
    max_horas_consecutivas_docente: int | None = None
    umbral_jornada_larga: int = 6
    duracion_bloque_minutos: int = 60
    # Los JSON anteriores no incluían este interruptor. En ese caso el lector
    # conserva el comportamiento histórico; la interfaz 7.2 crea explícitamente
    # una migración a ``False`` sin borrar los mapas ``preferidos`` originales.
    preferencias_docentes_activas: bool = True

    def gen_valido(self, sesion_idx: int, gen: Gen) -> bool:
        d, h, a = gen
        sesion = self.sesiones[sesion_idx]
        return (
            0 <= d < len(self.dias)
            and 0 <= h <= len(self.horas) - sesion.duracion
            and a in self.salones_validos[sesion_idx]
        )

    def validar_cromosoma(self, cromosoma: Cromosoma) -> None:
        if len(cromosoma) != len(self.sesiones):
            raise ValueError("El cromosoma debe tener exactamente un gen por sesion")
        for idx, gen in enumerate(cromosoma):
            if not self.gen_valido(idx, gen):
                raise ValueError(f"Gen no valido para la sesion {self.sesiones[idx].id}: {gen}")
