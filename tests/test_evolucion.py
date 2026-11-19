"""Pruebas de captura, reproducción, comparación y exportación evolutiva."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from horarios_ga.datos import cargar_datos, cargar_problema
from horarios_ga.evolucion import (
    ControlDidactico, RegistroEvolucion, VERSION_EVOLUCION, cargar_evolucion,
    comparar_instantaneas, crear_instantanea, describir_diferencia, guardar_evolucion,
)
from horarios_ga.exportaciones_evolucion import (
    exportar_comparacion_png, exportar_gif, exportar_instantanea_png,
    exportar_secuencia_png,
)
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import Configuracion, EjecucionCancelada, ejecutar


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


class TestsEvolucion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)
        cls.datos = cargar_datos(EJEMPLO)
        cls.config = Configuracion(
            poblacion=12, generaciones=4, elitismo=2, torneo=3, semilla=42,
        )
        cls.instantaneas = []
        cls.resultado = ejecutar(
            cls.problema, cls.config, callback_instantanea=cls.instantaneas.append,
        )
        cls.registro = RegistroEvolucion(
            VERSION_EVOLUCION, cls.config, cls.datos,
            tuple(s.id for s in cls.problema.sesiones), tuple(cls.instantaneas),
            cls.resultado.motivo_parada,
        )

    def test_generacion_cero_es_poblacion_inicial(self):
        inicial = self.instantaneas[0]
        self.assertEqual(inicial.generacion, 0)
        self.assertEqual(inicial.evaluacion_global, self.resultado.inicial)
        self.assertIsNotNone(inicial.muestra_inicial)
        self.problema.validar_cromosoma(inicial.muestra_inicial)

    def test_copias_independientes_e_inmutables(self):
        inicial = self.instantaneas[0]
        self.assertIsNot(inicial.mejor_global, self.resultado.cromosoma)
        self.assertIsInstance(inicial.mejor_global, tuple)
        self.assertTrue(all(isinstance(gen, tuple) for gen in inicial.mejor_global))
        with self.assertRaises((TypeError, AttributeError)):
            inicial.mejor_global[0] = (0, 0, 0)  # type: ignore[index]

    def test_registro_completo_y_captura_espaciada(self):
        capturas = []
        ejecutar(
            self.problema, replace(self.config, generaciones=5),
            callback_instantanea=capturas.append, capturar_cada=2,
        )
        self.assertEqual([x.generacion for x in capturas], [0, 2, 4, 5])

    def test_diferencias_dia_hora_salon_y_multibloque(self):
        anterior = self.instantaneas[0]
        genes = list(anterior.mejor_global)
        sesion = self.problema.sesiones[0]
        self.assertGreater(sesion.duracion, 1)
        dia, hora, salon = genes[0]
        nuevo_dia = (dia + 1) % len(self.problema.dias)
        nuevo_hora = (hora + 1) % (len(self.problema.horas) - sesion.duracion + 1)
        salones = self.problema.salones_validos[0]
        nuevo_salon = next((s for s in salones if s != salon), salon)
        genes[0] = (nuevo_dia, nuevo_hora, nuevo_salon)
        cromosoma = tuple(genes)
        evaluacion = evaluar(self.problema, cromosoma)
        actual = crear_instantanea(
            self.problema, 1, cromosoma, cromosoma, evaluacion, evaluacion,
            replace(anterior.registro, generacion=1), .1,
        )
        diferencia = comparar_instantaneas(self.problema, anterior, actual)
        cambio = diferencia.cambios[0]
        self.assertTrue(cambio.cambio_dia)
        self.assertTrue(cambio.cambio_hora)
        self.assertEqual(cambio.cambio_salon, nuevo_salon != salon)
        self.assertIn(self.problema.sesiones[0].id, "\n".join(describir_diferencia(self.problema, diferencia)))

    def test_mejor_sin_cambios_es_explicito(self):
        anterior = self.instantaneas[0]
        igual = replace(anterior, generacion=1, registro=replace(anterior.registro, generacion=1))
        diferencia = comparar_instantaneas(self.problema, anterior, igual)
        self.assertEqual(diferencia.sesiones_reasignadas, 0)
        self.assertIn("mantuvo sin cambios", " ".join(describir_diferencia(self.problema, diferencia)))

    def test_metricas_y_factibilidad_coinciden_con_fitness(self):
        for instantanea in self.instantaneas:
            self.assertEqual(evaluar(self.problema, instantanea.mejor_global), instantanea.evaluacion_global)
            self.assertEqual(instantanea.factible, instantanea.evaluacion_global.duras == 0)

    def test_guardado_carga_comprimida_y_validacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = guardar_evolucion(self.registro, Path(tmp) / "evolucion.json.gz")
            cargado = cargar_evolucion(ruta)
            self.assertEqual(cargado.configuracion, self.registro.configuracion)
            self.assertEqual(cargado.instantaneas, self.registro.instantaneas)
            invalido = Path(tmp) / "invalido.json"
            invalido.write_text(json.dumps({"version": 999}), encoding="utf-8")
            with self.assertRaises(ValueError):
                cargar_evolucion(invalido)

    def test_pausa_reanudacion_y_paso(self):
        control = ControlDidactico()
        control.pausar()
        terminado = threading.Event()

        def esperar():
            control.esperar()
            terminado.set()

        hilo = threading.Thread(target=esperar)
        hilo.start()
        time.sleep(.04)
        self.assertFalse(terminado.is_set())
        control.paso()
        hilo.join(timeout=1)
        self.assertTrue(terminado.is_set())
        self.assertTrue(control.pausado)
        control.continuar()
        self.assertFalse(control.pausado)

    def test_cancelacion_conserva_ultima_instantanea(self):
        capturas = []
        cancelar = False

        def progreso(registro):
            nonlocal cancelar
            cancelar = registro.generacion >= 1

        with self.assertRaises(EjecucionCancelada):
            ejecutar(
                self.problema, replace(self.config, generaciones=20), callback=progreso,
                debe_cancelar=lambda: cancelar, callback_instantanea=capturas.append,
            )
        self.assertEqual(capturas[-1].generacion, 1)

    def test_reproducibilidad_con_instantaneas(self):
        capturas = []
        ejecutar(self.problema, self.config, callback_instantanea=capturas.append)
        self.assertEqual(
            [(x.generacion, x.mejor_global, x.evaluacion_global) for x in capturas],
            [(x.generacion, x.mejor_global, x.evaluacion_global) for x in self.instantaneas],
        )

    def test_callback_opcional_no_cambia_motor(self):
        sin_captura = ejecutar(self.problema, self.config)
        con_captura = ejecutar(self.problema, self.config, callback_instantanea=lambda _x: None)
        self.assertEqual(sin_captura.cromosoma, con_captura.cromosoma)
        self.assertEqual(sin_captura.evaluacion, con_captura.evaluacion)

    def test_exportaciones_png_secuencia_comparacion_y_gif(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            png = exportar_instantanea_png(
                self.problema, self.config, self.instantaneas[0], carpeta / "vista.png",
                "grupo", "ISC-301",
            )
            comparacion = exportar_comparacion_png(
                self.problema, self.config, self.instantaneas[0], self.instantaneas[-1],
                carpeta / "comparacion.png", "grupo", "ISC-301",
            )
            secuencia = exportar_secuencia_png(
                self.problema, self.registro, carpeta / "frames",
                modo="grupo", identificador="ISC-301", cada=2,
            )
            gif = exportar_gif(
                self.problema, self.registro, carpeta / "evolucion.gif",
                modo="grupo", identificador="ISC-301", cada=2, duracion=.1,
            )
            self.assertGreater(png.stat().st_size, 5_000)
            self.assertGreater(comparacion.stat().st_size, png.stat().st_size)
            self.assertEqual(len(secuencia), 3)
            self.assertGreater(gif.stat().st_size, 5_000)


if __name__ == "__main__":
    unittest.main()

