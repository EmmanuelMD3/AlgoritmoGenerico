"""Casos controlados para restricciones y optimización académica de Fase 2."""
from __future__ import annotations

import random
import unittest
from copy import deepcopy
from pathlib import Path

from horarios_ga.datos import cargar_datos, problema_desde_datos
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import (
    Configuracion, ejecutar, individuo_aleatorio, reparar_individuo,
)


EJEMPLO = Path(__file__).resolve().parents[1] / "datos" / "ejemplo.json"


def datos_minimos(
    *, dias=None, horas=None, clases=None, docentes=None, salones=None, restricciones=None,
):
    return {
        "dias": dias or ["Lunes"],
        "horas": horas or ["07:00", "08:00", "09:00", "10:00"],
        "salones": salones or [
            {"id": "A1", "capacidad": 40, "tipo": "aula"},
            {"id": "A2", "capacidad": 40, "tipo": "aula"},
        ],
        "grupos": [{"id": "G1", "alumnos": 20}],
        "docentes": docentes or [{"id": "D1", "nombre": "Docente 1"}],
        "clases": clases or [{
            "id": "C1", "materia": "Materia", "grupo": "G1", "docente": "D1",
            "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula",
        }],
        "restricciones": restricciones or {},
    }


class TestsFase2(unittest.TestCase):
    def test_json_anterior_conserva_compatibilidad(self):
        datos = cargar_datos(EJEMPLO)
        datos.pop("restricciones", None)
        for grupo in datos["grupos"]:
            grupo.pop("no_disponible", None)
            grupo.pop("max_horas_consecutivas", None)
        for docente in datos["docentes"]:
            docente.pop("preferidos", None)
            docente.pop("max_horas_consecutivas", None)
        for clase in datos["clases"]:
            clase.pop("periodos_permitidos", None)
        problema = problema_desde_datos(datos)
        self.assertFalse(problema.franjas_no_lectivas)
        self.assertIsNone(problema.max_horas_consecutivas_grupo)
        self.assertTrue(all(not g.no_disponible for g in problema.grupos.values()))
        self.assertTrue(all(s.periodos_permitidos is None for s in problema.sesiones))

    def test_disponibilidad_grupo_franja_y_periodo_multibloque(self):
        datos = cargar_datos(EJEMPLO)
        datos["grupos"][0]["no_disponible"] = {"Lunes": ["07:00", "08:00"]}
        datos["restricciones"]["franjas_no_lectivas"] = {"Lunes": ["07:00"]}
        datos["clases"][0]["periodos_permitidos"] = {"Martes": ["09:00", "10:00"]}
        problema = problema_desde_datos(datos)
        genes = list(individuo_aleatorio(problema, random.Random(3)))
        genes[0] = (0, 0, problema.salones_validos[0][0])
        genes[1] = (1, 2, problema.salones_validos[1][0])
        evaluacion = evaluar(problema, tuple(genes))
        self.assertEqual(evaluacion.grupo_no_disponible, 2)
        self.assertGreaterEqual(evaluacion.franja_no_lectiva, 1)
        self.assertEqual(evaluacion.fuera_periodo, 2)
        self.assertFalse(evaluacion.factible)
        self.assertTrue(any("periodo" in r.lower() for r in evaluacion.razones_no_factible()))

    def test_maximo_consecutivo_obligatorio(self):
        datos = cargar_datos(EJEMPLO)
        datos["restricciones"]["max_horas_consecutivas_grupo"] = 2
        problema = problema_desde_datos(datos)
        genes = list(individuo_aleatorio(problema, random.Random(8)))
        por_id = {sesion.id: i for i, sesion in enumerate(problema.sesiones)}
        for sesion_id, bloque in (("C03-S1", 0), ("C04-S1", 1), ("C05-S1", 2)):
            idx = por_id[sesion_id]
            genes[idx] = (3, bloque, problema.salones_validos[idx][0])
        evaluacion = evaluar(problema, tuple(genes))
        self.assertGreaterEqual(evaluacion.exceso_consecutivo_grupo, 1)

    def test_preferencia_docente_es_blanda(self):
        datos = datos_minimos(docentes=[{
            "id": "D1", "nombre": "Docente 1",
            "preferidos": {"Lunes": ["08:00"]},
        }])
        problema = problema_desde_datos(datos)
        evaluacion = evaluar(problema, ((0, 0, 0),))
        self.assertEqual(evaluacion.fuera_preferencia_docente, 1)
        self.assertEqual(evaluacion.duras, 0)
        self.assertTrue(evaluacion.factible)
        self.assertGreater(evaluacion.penalizacion_blanda, 0)

    def test_desglose_de_calidad_academica(self):
        datos = datos_minimos(
            dias=["Lunes", "Martes"],
            clases=[
                {"id": "C1", "materia": "Materia 1", "grupo": "G1", "docente": "D1",
                 "sesiones_semana": 2, "duracion_bloques": 1, "tipo_salon": "aula"},
                {"id": "C2", "materia": "Materia 2", "grupo": "G1", "docente": "D1",
                 "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula"},
            ],
            restricciones={"umbral_jornada_larga": 2},
        )
        problema = problema_desde_datos(datos)
        evaluacion = evaluar(problema, ((0, 0, 0), (1, 3, 1), (0, 3, 0)))
        self.assertEqual(evaluacion.huecos, 2)
        self.assertEqual(evaluacion.jornada_extensa, 2)
        self.assertEqual(evaluacion.sesiones_aisladas_final, 2)
        self.assertEqual(evaluacion.desequilibrio_carga, 1)
        self.assertEqual(evaluacion.cambios_salon, 1)
        self.assertEqual(evaluacion.duras, 0)

    def test_conflicto_persistente_no_se_declara_imposible(self):
        datos = datos_minimos(
            horas=["07:00"],
            salones=[{"id": "A1", "capacidad": 40, "tipo": "aula"}],
            docentes=[
                {"id": "D1", "nombre": "Docente 1"},
                {"id": "D2", "nombre": "Docente 2"},
            ],
            clases=[
                {"id": "C1", "materia": "M1", "grupo": "G1", "docente": "D1",
                 "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula"},
                {"id": "C2", "materia": "M2", "grupo": "G1", "docente": "D2",
                 "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula"},
            ],
        )
        problema = problema_desde_datos(datos)
        resultado = ejecutar(problema, Configuracion(poblacion=8, generaciones=5, semilla=4))
        self.assertGreater(resultado.evaluacion.duras, 0)
        self.assertEqual(resultado.motivo_parada, "generaciones_completadas")
        self.assertNotIn("imposible", resultado.motivo_parada.lower())

    def test_parada_anticipada_exige_calidad_y_estancamiento(self):
        problema = problema_desde_datos(datos_minimos(horas=["07:00", "08:00"]))
        config = Configuracion(
            poblacion=8, generaciones=50, semilla=12,
            parada_sin_mejora=3, objetivo_penalizacion_blanda=0,
        )
        resultado = ejecutar(problema, config)
        self.assertTrue(resultado.evaluacion.factible)
        self.assertEqual(resultado.evaluacion.penalizacion_blanda, 0)
        self.assertEqual(resultado.motivo_parada, "calidad_sin_mejora")
        self.assertEqual(resultado.historial[-1].generacion, 3)

    def test_reparacion_nunca_empeora_prioridad(self):
        problema = problema_desde_datos(cargar_datos(EJEMPLO))
        genes = list(individuo_aleatorio(problema, random.Random(2)))
        genes[0] = (0, 0, problema.salones_validos[0][0])
        genes[1] = genes[0]
        original = tuple(genes)
        reparado = reparar_individuo(problema, original, random.Random(19), intentos=5)
        self.assertGreaterEqual(
            evaluar(problema, reparado).prioridad(),
            evaluar(problema, original).prioridad(),
        )


if __name__ == "__main__":
    unittest.main()
