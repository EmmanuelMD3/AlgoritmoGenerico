"""Pruebas sin pantalla para métricas y gráficas del dashboard Fase 3."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import fields, replace
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from horarios_ga.datos import cargar_problema
from horarios_ga.genetico import Configuracion, Registro, ejecutar
from interfaz.optimizacion import (
    PARAMETROS, VISTAS_GRAFICA, construir_comparacion, debe_redibujar,
    dibujar_historial, exportar_grafica_png, filas_desglose, metricas_resultado,
    resumen_finalizacion,
)


EJEMPLO = Path(__file__).resolve().parents[1] / "datos" / "ejemplo.json"


class TestsDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)
        cls.resultado = ejecutar(
            cls.problema,
            Configuracion(poblacion=12, generaciones=4, semilla=17),
        )

    def test_todos_los_parametros_tienen_control(self):
        claves_dashboard = {clave for clave, _etiqueta, _ayuda in PARAMETROS}
        claves_config = {campo.name for campo in fields(Configuracion)}
        self.assertEqual(claves_dashboard, claves_config)

    def test_kpis_proceden_del_resultado_real(self):
        metricas = metricas_resultado(self.resultado, segundos=1.25)
        evaluacion = self.resultado.evaluacion
        ultimo = self.resultado.historial[-1]
        self.assertEqual(metricas["duras"][0], str(evaluacion.duras))
        self.assertEqual(metricas["blandas"][0], str(evaluacion.penalizacion_blanda))
        self.assertEqual(metricas["fitness"][0], str(evaluacion.fitness))
        self.assertEqual(metricas["diversidad"][0], f"{ultimo.diversidad:.1%}")
        self.assertIn("sin ponderar", metricas["duras"][1].lower())
        self.assertIn("ponderada", metricas["blandas"][1].lower())

    def test_valores_ausentes_y_compatibilidad_de_registro(self):
        self.assertEqual(metricas_resultado(None), {})
        registro_antiguo = Registro(0, 10, 5.0, 1, 2, False)
        compatible = replace(self.resultado, historial=(registro_antiguo,))
        metricas = metricas_resultado(compatible)
        self.assertEqual(metricas["diversidad"][0], "0.0%")
        self.assertEqual(metricas["generaciones"][0].split(" / ")[0], "0")

    def test_cancelacion_y_parada_anticipada_se_interpretan(self):
        cancelado = replace(self.resultado, motivo_parada="cancelada")
        metricas_cancelado = metricas_resultado(cancelado, cancelada=True)
        self.assertEqual(metricas_cancelado["motivo"][0], "Cancelación solicitada")
        self.assertEqual(metricas_cancelado["estado"][2], "warning")
        self.assertIn("parcial", resumen_finalizacion(cancelado, cancelada=True).lower())

        anticipado = replace(self.resultado, motivo_parada="calidad_sin_mejora")
        self.assertEqual(
            metricas_resultado(anticipado)["motivo"][0], "Calidad + estancamiento",
        )

    def test_comparacion_usa_diferencias_absolutas(self):
        filas = {fila[0]: fila for fila in construir_comparacion(self.resultado)}
        inicial, final = self.resultado.inicial, self.resultado.evaluacion
        self.assertEqual(
            filas["Violaciones duras"][3], f"{final.duras - inicial.duras:+d}"
            if final.duras != inicial.duras else "0",
        )
        self.assertEqual(filas["Factibilidad"][1], "Factible" if inicial.factible else "No factible")
        self.assertNotIn("%", filas["Fitness"][3])

    def test_desglose_conserva_pesos_y_contribuciones(self):
        filas = filas_desglose(self.resultado.evaluacion)
        total_duro = sum(f[4] for f in filas if f[0] == "Dura")
        total_blando = sum(f[4] for f in filas if f[0] == "Blanda")
        self.assertEqual(total_duro, self.resultado.evaluacion.penalizacion_dura)
        self.assertEqual(total_blando, self.resultado.evaluacion.penalizacion_blanda)

    def test_vistas_no_inventan_puntos_historicos(self):
        for vista, _etiqueta in VISTAS_GRAFICA:
            figura = Figure()
            FigureCanvasAgg(figura)
            eje = figura.add_subplot(111)
            nota = dibujar_historial(eje, self.resultado.historial, vista)
            self.assertTrue(nota)
            lineas_con_historial = [
                linea for linea in eje.lines
                if len(linea.get_xdata()) == len(self.resultado.historial)
            ]
            self.assertTrue(lineas_con_historial, vista)

    def test_estado_vacio_de_grafica(self):
        figura = Figure()
        FigureCanvasAgg(figura)
        eje = figura.add_subplot(111)
        nota = dibujar_historial(eje, (), "factibilidad")
        self.assertIn("No hay", nota)
        self.assertTrue(eje.texts)

    def test_exportacion_png_de_cada_vista(self):
        with tempfile.TemporaryDirectory() as tmp:
            for vista, _etiqueta in VISTAS_GRAFICA:
                ruta = exportar_grafica_png(
                    self.resultado.historial, vista, Path(tmp) / f"{vista}.png",
                )
                self.assertTrue(ruta.exists())
                self.assertGreater(ruta.stat().st_size, 5_000)

    def test_redibujos_se_agrupan_sin_perder_historial(self):
        self.assertTrue(debe_redibujar(0, 200, 0.0, 0.0))
        self.assertFalse(debe_redibujar(2, 200, 1.0, 1.05))
        self.assertTrue(debe_redibujar(2, 200, 1.0, 1.25))
        self.assertTrue(debe_redibujar(200, 200, 1.0, 1.01))


if __name__ == "__main__":
    unittest.main()
