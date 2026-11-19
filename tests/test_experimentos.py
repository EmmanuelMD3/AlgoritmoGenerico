"""Pruebas del ejecutor, métodos, presupuestos y exportaciones de Fase 4."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from horarios_ga.baselines import ejecutar_busqueda_aleatoria, ejecutar_heuristica_constructiva
from horarios_ga.datos import cargar_datos, cargar_problema
from horarios_ga.experimentos import (
    ConfiguracionExperimento, estimar_experimento, ejecutar_experimento,
    exportar_experimento, generar_variantes_un_parametro,
)
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import Configuracion, ejecutar
from interfaz.experimentacion import configuracion_experimento_desde_valores


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


def config_corta(**cambios):
    base = Configuracion(
        poblacion=8, generaciones=1, elitismo=1, torneo=2, semilla=17,
        prob_reparacion=.2, mutacion_dirigida=.3,
    )
    return replace(base, **cambios)


class TestsExperimentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)
        cls.datos = cargar_datos(EJEMPLO)

    def test_instrumentacion_no_cambia_resultado_genetico(self):
        config = config_corta(generaciones=2)
        conteo = []
        normal = ejecutar(self.problema, config)
        instrumentado = ejecutar(self.problema, config, al_evaluar=conteo.append)
        self.assertEqual(normal.cromosoma, instrumentado.cromosoma)
        self.assertEqual(normal.evaluacion, instrumentado.evaluacion)
        self.assertGreater(len(conteo), 0)

    def test_baselines_respetan_presupuesto_y_evaluacion(self):
        for funcion in (ejecutar_busqueda_aleatoria, ejecutar_heuristica_constructiva):
            resultado = funcion(self.problema, 9, 23)
            self.assertEqual(resultado.evaluaciones, 9)
            self.problema.validar_cromosoma(resultado.cromosoma)
            self.assertEqual(evaluar(self.problema, resultado.cromosoma), resultado.evaluacion)

    def test_presupuesto_comparable_usa_costo_real_del_ag(self):
        config = ConfiguracionExperimento(
            nombre="Presupuesto", repeticiones=1, genetico=config_corta(), semilla_inicial=17,
        )
        resultado = ejecutar_experimento(config, self.datos)
        por_metodo = {e.metodo: e for e in resultado.ejecuciones}
        self.assertEqual(por_metodo["aleatorio"].evaluaciones, por_metodo["genetico"].evaluaciones)
        self.assertEqual(por_metodo["constructivo"].evaluaciones, por_metodo["genetico"].evaluaciones)
        self.assertGreaterEqual(por_metodo["genetico"].evaluaciones, config.genetico.poblacion)

    def test_repeticiones_y_semillas_controladas(self):
        config = ConfiguracionExperimento(
            nombre="Semillas", repeticiones=2, metodos=("aleatorio",),
            genetico=config_corta(), semilla_inicial=50,
        )
        resultado = ejecutar_experimento(config, self.datos)
        self.assertEqual([e.semilla for e in resultado.ejecuciones], [50, 51])

    def test_solo_repeticion_genetica_elegida_conserva_evolucion(self):
        config = ConfiguracionExperimento(
            nombre="Evolución elegida", repeticiones=2, metodos=("genetico",),
            genetico=config_corta(), semilla_inicial=70, repeticion_evolucion=2,
        )
        resultado = ejecutar_experimento(config, self.datos)
        self.assertIsNone(resultado.ejecuciones[0].evolucion)
        self.assertIsNotNone(resultado.ejecuciones[1].evolucion)
        self.assertEqual(resultado.ejecuciones[1].evolucion.instantaneas[0].generacion, 0)

    def test_reproducibilidad_algoritmica_excluye_tiempo(self):
        config = ConfiguracionExperimento(
            nombre="Reproducible", repeticiones=1,
            genetico=config_corta(), semilla_inicial=33,
        )
        a = ejecutar_experimento(config, self.datos)
        b = ejecutar_experimento(config, self.datos)
        firma = lambda r: [
            (e.metodo, e.semilla, e.cromosoma, e.duras, e.penalizacion_blanda, e.fitness, e.evaluaciones)
            for e in r.ejecuciones
        ]
        self.assertEqual(firma(a), firma(b))

    def test_cancelacion_conserva_ejecuciones_terminadas(self):
        cancelar = False

        def progreso(evento):
            nonlocal cancelar
            if evento.completadas >= 1:
                cancelar = True

        config = ConfiguracionExperimento(
            nombre="Cancelar", repeticiones=3, genetico=config_corta(), semilla_inicial=9,
        )
        resultado = ejecutar_experimento(
            config, self.datos, al_progresar=progreso, debe_cancelar=lambda: cancelar,
        )
        self.assertEqual(resultado.estado, "cancelado")
        self.assertGreaterEqual(len(resultado.ejecuciones), 1)
        self.assertLess(len(resultado.ejecuciones), estimar_experimento(config)["ejecuciones"])

    def test_variantes_cambian_un_parametro(self):
        base = config_corta()
        variantes = generar_variantes_un_parametro(
            base, poblaciones=(8, 12), mutaciones=(.08, .2), cruzas=(.85, .7),
        )
        self.assertEqual(variantes[0][0], "Base")
        for _, variante in variantes[1:]:
            cambios = sum(
                getattr(base, campo) != getattr(variante, campo)
                for campo in base.__dataclass_fields__
            )
            self.assertEqual(cambios, 1)

    def test_exportacion_cientifica_completa_y_sin_sobrescritura(self):
        config = ConfiguracionExperimento(
            nombre="Exportación", repeticiones=1, genetico=config_corta(),
        )
        resultado = ejecutar_experimento(config, self.datos)
        with tempfile.TemporaryDirectory() as tmp:
            primera = exportar_experimento(resultado, tmp)
            segunda = exportar_experimento(resultado, tmp)
            esperados = {
                "configuracion.json", "escenario.json", "ejecuciones.csv",
                "resumen_estadistico.csv", "resumen.json", "factibilidad.png",
                "penalizaciones.png", "tiempos.png", "convergencia.png", "reporte.html",
            }
            self.assertTrue(esperados <= {p.name for p in primera.iterdir()})
            self.assertNotEqual(primera, segunda)
            resumen = json.loads((primera / "resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(resumen["huella_escenario_sha256"], resultado.huella_escenario)
            self.assertGreater((primera / "factibilidad.png").stat().st_size, 5_000)

    def test_conversion_de_controles_de_interfaz(self):
        valores = {
            "nombre": "Interfaz", "descripcion": "Prueba", "escenario": "pequeno",
            "repeticiones": "5", "modo": "comparacion", "poblacion": "12",
            "generaciones": "2", "prob_cruza": ".8", "prob_mutacion": ".1",
            "elitismo": "2", "torneo": "3", "semilla": "5",
            "parada_sin_mejora": "0", "objetivo_penalizacion_blanda": "0",
        }
        config = configuracion_experimento_desde_valores(valores, ("genetico", "aleatorio"))
        self.assertEqual(config.repeticiones, 5)
        self.assertEqual(config.genetico.poblacion, 12)
        self.assertEqual(config.metodos, ("genetico", "aleatorio"))


if __name__ == "__main__":
    unittest.main()

