"""Diagnóstico, estados de factibilidad y reparación híbrida avanzada."""
from __future__ import annotations

import importlib.util
import json
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from horarios_ga.constructor_escenarios import validar_escenario_detallado
from horarios_ga.datos import cargar_datos, cargar_problema, problema_desde_datos
from horarios_ga.diagnostico import (
    EstadoFactibilidad, analizar_cotas_necesarias, candidatos_estaticos,
    diagnosticar_horario, formatear_diagnostico,
)
from horarios_ga.fitness import evaluar, evaluar_detallado
from horarios_ga.experimento_factibilidad import ejecutar_comparacion, exportar_comparacion, resumir
from horarios_ga.genetico import Configuracion, ejecutar
from horarios_ga.hibrido import reparar_dirigido_avanzado
from horarios_ga.verificador_cp_sat import verificar_factibilidad


BASE = Path(__file__).resolve().parents[1]
CUELLO = BASE / "datos" / "configuracion_academica.json"


def _datos_minimos(*, sesiones: int = 2, bloques: int = 2) -> dict:
    return {
        "dias": ["Lunes"],
        "horas": [f"{8 + hora:02d}:00" for hora in range(bloques)],
        "salones": [{"id": "A1", "capacidad": 30, "tipo": "aula"}],
        "grupos": [{"id": "G1", "alumnos": 20}],
        "docentes": [
            {"id": f"D{i + 1}", "nombre": f"Docente {i + 1}"}
            for i in range(sesiones)
        ],
        "clases": [
            {
                "id": f"C{i + 1}", "materia": f"Materia {i + 1}",
                "grupo": "G1", "docente": f"D{i + 1}",
                "sesiones_semana": 1, "duracion_bloques": 1,
                "tipo_salon": "aula",
            }
            for i in range(sesiones)
        ],
        "restricciones": {},
    }


class TestsDiagnosticoFactibilidad(unittest.TestCase):
    def test_escenario_real_es_estructuralmente_valido_y_sin_referencias_rotas(self):
        datos = cargar_datos(CUELLO)
        validacion = validar_escenario_detallado(datos)
        problema = problema_desde_datos(datos)
        self.assertTrue(validacion.correcto)
        self.assertEqual(validacion.errores, ())
        self.assertEqual(
            (len(problema.grupos), len(problema.docentes),
             len(problema.sesiones), len(problema.salones)),
            (7, 20, 98, 5),
        )

    def test_escenario_real_no_tiene_contradiccion_en_cotas_necesarias(self):
        problema = cargar_problema(CUELLO)
        cotas = analizar_cotas_necesarias(problema)
        self.assertTrue(cotas)
        self.assertFalse(any(cota.contradiccion for cota in cotas))
        dominios = [len(candidatos_estaticos(problema, i)) for i in range(98)]
        self.assertEqual(min(dominios), 4)
        self.assertNotIn(0, dominios)

    def test_cota_de_grupo_demuestra_imposibilidad_simple(self):
        problema = problema_desde_datos(_datos_minimos(sesiones=3, bloques=2))
        contradicciones = [
            cota for cota in analizar_cotas_necesarias(problema)
            if cota.contradiccion
        ]
        self.assertTrue(any(cota.recurso == "Grupo G1" for cota in contradicciones))
        diagnostico = diagnosticar_horario(
            problema, ((0, 0, 0), (0, 0, 0), (0, 1, 0)),
        )
        self.assertEqual(diagnostico.estado, EstadoFactibilidad.IMPOSIBILIDAD_DEMOSTRADA)

    def test_diagnostico_nombra_sesiones_razones_y_alternativas_reales(self):
        problema = problema_desde_datos(_datos_minimos())
        cromosoma = ((0, 0, 0), (0, 0, 0))
        diagnostico = diagnosticar_horario(problema, cromosoma)
        self.assertEqual(diagnostico.estado, EstadoFactibilidad.NO_ENCONTRADA)
        self.assertEqual(len(diagnostico.asignaciones_conflictivas), 2)
        self.assertTrue(all(x.razones for x in diagnostico.asignaciones_conflictivas))
        self.assertTrue(any(x.alternativas for x in diagnostico.asignaciones_conflictivas))
        texto = formatear_diagnostico(diagnostico)
        self.assertIn("C1-S1", texto)
        self.assertIn("Colisión", texto)
        self.assertIn("Alternativas", texto)

    def test_diagnostico_factible_no_inventa_conflictos(self):
        problema = problema_desde_datos(_datos_minimos())
        diagnostico = diagnosticar_horario(problema, ((0, 0, 0), (0, 1, 0)))
        self.assertEqual(diagnostico.estado, EstadoFactibilidad.SOLUCION_FACTIBLE)
        self.assertEqual(diagnostico.asignaciones_conflictivas, ())

    def test_sesion_sin_dominio_es_imposibilidad_demostrada_sin_solver(self):
        datos = _datos_minimos(sesiones=1)
        datos["clases"][0]["periodos_permitidos"] = {}
        problema = problema_desde_datos(datos)
        resultado = verificar_factibilidad(problema, limite_segundos=1)
        self.assertEqual(resultado.estado, EstadoFactibilidad.IMPOSIBILIDAD_DEMOSTRADA)
        self.assertEqual(resultado.estado_solver, "PREPROCESAMIENTO")

    def test_cp_sat_opcional_distingue_dependencia_o_solucion_confirmada(self):
        problema = problema_desde_datos(_datos_minimos())
        resultado = verificar_factibilidad(problema, limite_segundos=2)
        if importlib.util.find_spec("ortools") is None:
            self.assertEqual(resultado.estado, EstadoFactibilidad.INCONCLUSA)
            self.assertEqual(resultado.estado_solver, "DEPENDENCIA_AUSENTE")
        else:
            self.assertEqual(resultado.estado, EstadoFactibilidad.SOLUCION_FACTIBLE)
            self.assertTrue(evaluar(problema, resultado.cromosoma).factible)

    def test_reparacion_avanzada_resuelve_conflicto_y_nunca_empeora(self):
        problema = problema_desde_datos(_datos_minimos())
        inicial = ((0, 0, 0), (0, 0, 0))
        reparado = reparar_dirigido_avanzado(
            problema, inicial, random.Random(7),
            evaluador=lambda c: evaluar(problema, c),
            evaluador_detallado=lambda c: evaluar_detallado(problema, c),
        )
        self.assertGreaterEqual(
            evaluar(problema, reparado).prioridad(),
            evaluar(problema, inicial).prioridad(),
        )
        self.assertTrue(evaluar(problema, reparado).factible)

    def test_clasico_ignora_mejoras_hibridas_y_sigue_reproducible(self):
        problema = problema_desde_datos(_datos_minimos())
        base = Configuracion(
            poblacion=8, generaciones=3, elitismo=1, torneo=2, semilla=19,
            reparacion_avanzada=False, reinicio_estancamiento=False,
        )
        banderas = replace(base, reparacion_avanzada=True, reinicio_estancamiento=True)
        primero = ejecutar(problema, base)
        segundo = ejecutar(problema, banderas)
        self.assertEqual(primero.cromosoma, segundo.cromosoma)
        self.assertEqual(primero.evaluacion, segundo.evaluacion)
        self.assertEqual(primero.historial, segundo.historial)

    def test_hibrido_avanzado_es_reproducible(self):
        problema = problema_desde_datos(_datos_minimos())
        config = Configuracion(
            poblacion=8, generaciones=3, elitismo=1, torneo=2, semilla=29,
            variante="hibrido", inicializacion_heuristica=True,
            porcentaje_inicializacion_heuristica=.25,
            reparacion_avanzada=True, reinicio_estancamiento=True,
        )
        primero = ejecutar(problema, config)
        segundo = ejecutar(problema, config)
        self.assertEqual(primero.cromosoma, segundo.cromosoma)
        self.assertEqual(primero.evaluacion, segundo.evaluacion)
        self.assertEqual(primero.historial, segundo.historial)

    def test_comparacion_antes_despues_iguala_semillas_y_presupuesto(self):
        problema = problema_desde_datos(_datos_minimos())
        filas = ejecutar_comparacion(
            problema, semillas=(17,), poblacion=8, generaciones=2, presupuesto=24,
        )
        self.assertEqual([(f.variante, f.semilla) for f in filas], [
            ("antes", 17), ("despues", 17),
        ])
        self.assertTrue(all(f.presupuesto == 24 for f in filas))
        self.assertEqual(set(resumir(filas)), {"antes", "despues"})
        with tempfile.TemporaryDirectory() as tmp:
            ruta = exportar_comparacion(filas, Path(tmp) / "comparacion.json", huella="abc")
            contenido = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(contenido["huella_escenario_sha256"], "abc")
            self.assertEqual(len(contenido["resultados"]), 2)


if __name__ == "__main__":
    unittest.main()
