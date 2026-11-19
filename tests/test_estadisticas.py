"""Pruebas de estadística científica sin depender de Tkinter."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from horarios_ga.estadisticas import (
    conclusiones_descriptivas, estadisticas_descriptivas, percentil, resumir_ejecuciones,
)


def corrida(metodo="A", factible=True, duras=0, blanda=10, tiempo=1.0, error=None):
    return SimpleNamespace(
        etiqueta_metodo=metodo, metodo=metodo, factible=factible, duras=duras,
        penalizacion_blanda=blanda, fitness=1000 - blanda, duracion=tiempo,
        evaluaciones=100, evaluaciones_hasta_factible=50 if factible else None,
        generaciones_ejecutadas=10, error=error,
    )


class TestsEstadisticas(unittest.TestCase):
    def test_estadisticas_y_percentiles(self):
        estadisticas = estadisticas_descriptivas([1, 2, 3, 4])
        self.assertEqual(estadisticas["n"], 4)
        self.assertEqual(estadisticas["media"], 2.5)
        self.assertEqual(estadisticas["mediana"], 2.5)
        self.assertEqual(percentil([1, 2, 3, 4], 25), 1.75)
        self.assertEqual(percentil([1, 2, 3, 4], 75), 3.25)

    def test_datos_incompletos(self):
        estadisticas = estadisticas_descriptivas([None, None])
        self.assertEqual(estadisticas["n"], 0)
        self.assertIsNone(estadisticas["media"])

    def test_calidad_excluye_no_factibles(self):
        resumen = resumir_ejecuciones([
            corrida(factible=True, blanda=80),
            corrida(factible=False, duras=1, blanda=0),
        ])[0]
        self.assertEqual(resumen["factibles"], 1)
        self.assertEqual(resumen["tasa_factibilidad"], 50)
        self.assertEqual(resumen["penalizacion_blanda_factible"]["media"], 80)

    def test_sin_factibles_es_explicito(self):
        ejecuciones = [corrida(factible=False, duras=2, blanda=0)]
        resumen = resumir_ejecuciones(ejecuciones)[0]
        self.assertEqual(resumen["penalizacion_blanda_factible"]["n"], 0)
        self.assertIn("Sin soluciones factibles", conclusiones_descriptivas(ejecuciones))

    def test_errores_no_entran_en_muestras_validas(self):
        resumen = resumir_ejecuciones([corrida(), corrida(error="fallo")])[0]
        self.assertEqual(resumen["ejecuciones"], 2)
        self.assertEqual(resumen["muestras_validas"], 1)
        self.assertEqual(resumen["errores"], 1)


if __name__ == "__main__":
    unittest.main()

