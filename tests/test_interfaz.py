"""Pruebas de las extensiones usadas por la interfaz, sin requerir una pantalla."""
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from horarios_ga.datos import cargar_datos, cargar_problema, problema_desde_datos
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import (
    Configuracion, EjecucionCancelada, Registro, Resultado, ejecutar, individuo_aleatorio,
)
from interfaz.datos_academicos import ModeloDatosAcademicos
from interfaz.horarios import construir_matriz
from interfaz.optimizacion import configuracion_desde_textos


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


class TestsInterfaz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)

    def test_validacion_parametros_interfaz(self):
        config = configuracion_desde_textos({
            "poblacion": "20", "generaciones": "5", "prob_cruza": "0.8",
            "prob_mutacion": "0.1", "elitismo": "2", "torneo": "3", "semilla": "9",
            "mutacion_dirigida": "0.4", "prob_reparacion": "0.2", "inmigrantes": "0.05",
            "parada_sin_mejora": "6", "objetivo_penalizacion_blanda": "80",
        })
        self.assertEqual(config.poblacion, 20)
        self.assertEqual(config.torneo, 3)
        self.assertEqual(config.parada_sin_mejora, 6)
        self.assertEqual(config.objetivo_penalizacion_blanda, 80)
        with self.assertRaises(ValueError):
            configuracion_desde_textos({
                "poblacion": "3", "generaciones": "5", "prob_cruza": "0.8",
                "prob_mutacion": "0.1", "elitismo": "2", "torneo": "3", "semilla": "9",
            })

    def test_carga_guardado_y_compatibilidad_modelo(self):
        modelo = ModeloDatosAcademicos(EJEMPLO)
        original = modelo.validar()
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "academicos.json"
            modelo.guardar(destino)
            recargado = cargar_datos(destino)
            problema = problema_desde_datos(recargado)
        self.assertEqual(problema.dias, original.dias)
        self.assertEqual(problema.horas, original.horas)
        self.assertEqual(problema.sesiones, original.sesiones)

    def test_callback_opcional_recibe_generaciones_reales(self):
        vistos: list[Registro] = []
        config = Configuracion(poblacion=12, generaciones=3, semilla=8)
        resultado = ejecutar(self.problema, config, callback=vistos.append)
        self.assertEqual([r.generacion for r in vistos], [0, 1, 2, 3])
        self.assertEqual(tuple(vistos), resultado.historial)

    def test_cancelacion_cooperativa_conserva_resultado(self):
        cancelar = False

        def callback(registro: Registro):
            nonlocal cancelar
            cancelar = registro.generacion >= 2

        with self.assertRaises(EjecucionCancelada) as contexto:
            ejecutar(
                self.problema, Configuracion(poblacion=12, generaciones=20),
                callback=callback, debe_cancelar=lambda: cancelar,
            )
        parcial = contexto.exception.resultado
        self.assertEqual(parcial.historial[-1].generacion, 2)
        self.assertEqual(parcial.evaluacion.fitness, parcial.historial[-1].mejor_fitness)

    def _resultado_manual(self, colision: bool = False) -> Resultado:
        cromosoma = list(individuo_aleatorio(self.problema, random.Random(77)))
        cromosoma[0] = (0, 0, 2)
        if colision:
            cromosoma[1] = (0, 0, 2)
        cromosoma_t = tuple(cromosoma)
        evaluacion = evaluar(self.problema, cromosoma_t)
        registro = Registro(0, evaluacion.fitness, float(evaluacion.fitness), evaluacion.duras, evaluacion.huecos, evaluacion.factible)
        return Resultado(cromosoma_t, evaluacion, evaluacion, (registro,), Configuracion())

    def test_sesion_multibloque_muestra_continuacion(self):
        resultado = self._resultado_manual()
        matriz = construir_matriz(self.problema, resultado, "grupo", "ISC-301")
        primera = next(e for e in matriz[(0, 0)] if e.sesion.id == "C01-S1")
        segunda = next(e for e in matriz[(1, 0)] if e.sesion.id == "C01-S1")
        self.assertFalse(primera.continuacion)
        self.assertTrue(segunda.continuacion)

    def test_conflictos_quedan_marcados_en_celdas(self):
        resultado = self._resultado_manual(colision=True)
        matriz = construir_matriz(self.problema, resultado, "grupo", "ISC-301")
        afectadas = [e for e in matriz[(0, 0)] if e.sesion.id in {"C01-S1", "C01-S2"}]
        self.assertEqual(len(afectadas), 2)
        self.assertTrue(all(e.conflicto for e in afectadas))
        self.assertGreater(resultado.evaluacion.duras, 0)


if __name__ == "__main__":
    unittest.main()
