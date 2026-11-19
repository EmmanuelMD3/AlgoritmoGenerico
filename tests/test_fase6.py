"""Pruebas de los operadores híbridos, presupuestos y ablaciones de Fase 6."""
from __future__ import annotations

import random
import unittest
from dataclasses import replace
from pathlib import Path

from horarios_ga.datos import cargar_datos, cargar_problema
from horarios_ga.experimentos import (
    ConfiguracionExperimento, ejecutar_experimento, generar_ablaciones,
)
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import Configuracion, ejecutar, individuo_aleatorio
from horarios_ga.hibrido import (
    busqueda_local, individuo_constructivo, tasa_mutacion_adaptativa,
)
from interfaz.optimizacion import configuracion_desde_textos


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


class TestsFase6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)
        cls.datos = cargar_datos(EJEMPLO)

    def config_hibrida(self, **cambios) -> Configuracion:
        base = Configuracion(
            poblacion=12, generaciones=4, elitismo=2, torneo=3, semilla=31,
            variante="hibrido", inicializacion_heuristica=True,
            porcentaje_inicializacion_heuristica=.25,
            busqueda_local=True, frecuencia_busqueda_local=2,
            porcentaje_busqueda_local=.25, evaluaciones_busqueda_local=4,
            mejoras_busqueda_local=1, mutacion_adaptativa=True,
        )
        return replace(base, **cambios)

    def test_clasico_sigue_siendo_predeterminado_e_ignora_modulos_hibridos(self):
        base = Configuracion(poblacion=12, generaciones=3, elitismo=2, torneo=3, semilla=8)
        banderas = replace(
            base, inicializacion_heuristica=True, busqueda_local=True,
            mutacion_adaptativa=True,
        )
        primero = ejecutar(self.problema, base)
        segundo = ejecutar(self.problema, banderas)
        self.assertEqual(base.variante, "clasico")
        self.assertEqual(primero.cromosoma, segundo.cromosoma)
        self.assertEqual(primero.evaluacion, segundo.evaluacion)
        self.assertEqual(primero.historial, segundo.historial)

    def test_constructivo_es_valido_reproducible_y_sin_testigo(self):
        a = individuo_constructivo(self.problema, random.Random(10))
        b = individuo_constructivo(self.problema, random.Random(10))
        self.assertEqual(a, b)
        self.problema.validar_cromosoma(a)
        # El escenario contiene sesiones multibloque; sus inicios siguen siendo válidos.
        self.assertTrue(any(s.duracion > 1 for s in self.problema.sesiones))
        self.assertFalse(hasattr(self.problema, "solucion"))

    def test_poblacion_mixta_registra_cantidades_reales(self):
        resultado = ejecutar(self.problema, self.config_hibrida(generaciones=1))
        self.assertEqual(resultado.estadisticas.individuos_heuristicos, 3)
        self.assertEqual(resultado.estadisticas.individuos_aleatorios, 9)
        self.assertEqual(resultado.estadisticas.variante, "hibrido")

    def test_porcentajes_extremos_cero_y_cincuenta(self):
        cero = ejecutar(
            self.problema,
            self.config_hibrida(generaciones=1, porcentaje_inicializacion_heuristica=0),
        )
        mitad = ejecutar(
            self.problema,
            self.config_hibrida(generaciones=1, porcentaje_inicializacion_heuristica=.5),
        )
        self.assertEqual(cero.estadisticas.individuos_heuristicos, 0)
        self.assertEqual(mitad.estadisticas.individuos_heuristicos, 6)

    def test_constructivos_sucesivos_conservan_diversidad(self):
        rng = random.Random(91)
        construidos = {individuo_constructivo(self.problema, rng) for _ in range(6)}
        self.assertGreater(len(construidos), 1)

    def test_busqueda_local_acepta_cancelacion_cooperativa(self):
        inicial = individuo_aleatorio(self.problema, random.Random(92))
        conteo = 0

        def evaluador(cromosoma):
            nonlocal conteo
            conteo += 1
            return evaluar(self.problema, cromosoma)

        resultado = busqueda_local(
            self.problema, inicial, evaluador, random.Random(93),
            max_evaluaciones=20, debe_cancelar=lambda: True,
        )
        self.assertEqual(conteo, 1)
        self.assertEqual(resultado.cromosoma, inicial)

    def test_busqueda_local_reasignacion_no_empeora_y_respeta_limite(self):
        inicial = individuo_aleatorio(self.problema, random.Random(4))
        conteo = 0

        def evaluador(cromosoma):
            nonlocal conteo
            conteo += 1
            return evaluar(self.problema, cromosoma)

        resultado = busqueda_local(
            self.problema, inicial, evaluador, random.Random(5),
            vecindario="reasignacion", criterio="mejor",
            max_evaluaciones=7, max_mejoras=2,
        )
        self.assertGreaterEqual(resultado.evaluacion.prioridad(), evaluar(self.problema, inicial).prioridad())
        self.assertLessEqual(conteo, 1 + 7 * 2)
        self.problema.validar_cromosoma(resultado.cromosoma)

    def test_busqueda_local_intercambio_conserva_genes_validos(self):
        inicial = individuo_aleatorio(self.problema, random.Random(14))
        resultado = busqueda_local(
            self.problema, inicial, lambda c: evaluar(self.problema, c), random.Random(15),
            vecindario="intercambio", max_evaluaciones=10, max_mejoras=1,
        )
        self.problema.validar_cromosoma(resultado.cromosoma)
        self.assertGreaterEqual(resultado.evaluacion.prioridad(), evaluar(self.problema, inicial).prioridad())

    def test_mutacion_adaptativa_sube_baja_y_respeta_cotas(self):
        elevada = tasa_mutacion_adaptativa(.08, .08, .02, .20, 10, 5, .10, .25, 1.5, .8)
        recuperada = tasa_mutacion_adaptativa(elevada, .08, .02, .20, 0, 5, .80, .25, 1.5, .8)
        self.assertEqual(elevada, .18)  # dos señales de tensión: 0.08 * 1.5²
        self.assertLess(recuperada, elevada)
        self.assertGreaterEqual(recuperada, .08)
        self.assertLessEqual(elevada, .20)

    def test_presupuesto_cuenta_todas_las_evaluaciones_sin_excederlo(self):
        observadas = []
        config = self.config_hibrida(generaciones=20, presupuesto_evaluaciones=80)
        resultado = ejecutar(self.problema, config, al_evaluar=observadas.append)
        self.assertEqual(resultado.motivo_parada, "presupuesto_evaluaciones")
        self.assertEqual(len(observadas), resultado.estadisticas.evaluaciones_totales)
        self.assertLessEqual(len(observadas), 80)
        self.assertGreaterEqual(len(observadas), config.poblacion)

    def test_reproducibilidad_hibrida_excluye_tiempos(self):
        a = ejecutar(self.problema, self.config_hibrida())
        b = ejecutar(self.problema, self.config_hibrida())
        self.assertEqual(a.cromosoma, b.cromosoma)
        self.assertEqual(a.evaluacion, b.evaluacion)
        self.assertEqual(a.historial, b.historial)
        self.assertEqual(a.estadisticas.evaluaciones_totales, b.estadisticas.evaluaciones_totales)

    def test_historial_expone_tasa_local_estancamiento_y_evaluaciones(self):
        resultado = ejecutar(self.problema, self.config_hibrida())
        self.assertTrue(all(r.prob_mutacion_usada > 0 for r in resultado.historial))
        self.assertTrue(all(a.evaluaciones_acumuladas <= b.evaluaciones_acumuladas
                            for a, b in zip(resultado.historial, resultado.historial[1:])))
        self.assertTrue(any(r.aplicaciones_busqueda_local for r in resultado.historial[1:]))

    def test_ablacion_a_e_aisla_componentes_y_combina_el_final(self):
        variantes = generar_ablaciones(Configuracion(poblacion=12, generaciones=2, elitismo=2, torneo=3))
        self.assertEqual([nombre[0] for nombre, _ in variantes], list("ABCDE"))
        self.assertEqual(variantes[0][1].variante, "clasico")
        self.assertTrue(variantes[1][1].inicializacion_heuristica)
        self.assertTrue(variantes[2][1].busqueda_local and not variantes[2][1].inicializacion_heuristica)
        self.assertTrue(variantes[3][1].mutacion_adaptativa and not variantes[3][1].inicializacion_heuristica)
        self.assertTrue(variantes[4][1].busqueda_local and variantes[4][1].mutacion_adaptativa)

    def test_laboratorio_distingue_clasico_e_hibrido(self):
        clasico = Configuracion(poblacion=8, generaciones=1, elitismo=1, torneo=2, semilla=20)
        hibrido = replace(
            clasico, variante="hibrido", inicializacion_heuristica=True,
            busqueda_local=True, mutacion_adaptativa=True,
        )
        config = ConfiguracionExperimento(
            nombre="Fase 6", repeticiones=1, metodos=("genetico", "hibrido"),
            genetico=clasico, hibrido=hibrido, semilla_inicial=20,
            repeticion_evolucion=0,
        )
        resultado = ejecutar_experimento(config, self.datos)
        self.assertEqual([e.metodo for e in resultado.ejecuciones], ["genetico", "hibrido"])
        self.assertTrue(all(e.evaluaciones <= e.presupuesto_objetivo for e in resultado.ejecuciones))
        self.assertGreater(resultado.ejecuciones[1].evaluaciones_inicializacion, 0)

    def test_interfaz_convierte_controles_hibridos(self):
        valores = {
            "poblacion": "12", "generaciones": "2", "prob_cruza": ".8",
            "prob_mutacion": ".1", "elitismo": "2", "torneo": "3", "semilla": "4",
            "variante": "hibrido", "inicializacion_heuristica": "True",
            "busqueda_local": "True", "mutacion_adaptativa": "True",
            "presupuesto_evaluaciones": "120",
        }
        config = configuracion_desde_textos(valores)
        self.assertEqual(config.variante, "hibrido")
        self.assertTrue(config.inicializacion_heuristica and config.busqueda_local)
        self.assertEqual(config.presupuesto_evaluaciones, 120)


if __name__ == "__main__":
    unittest.main()
