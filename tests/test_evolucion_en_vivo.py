"""Regresiones del transporte asíncrono y la presentación evolutiva en vivo."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path

from horarios_ga.datos import cargar_datos, cargar_problema
from horarios_ga.evolucion import ControlDidactico
from horarios_ga.genetico import Configuracion, ejecutar
from interfaz.aplicacion import EVENTOS_MAXIMOS_POR_CICLO, extraer_lote_eventos
from interfaz.evolucion import VistaEvolucion


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


class TestsEvolucionEnVivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)
        cls.datos = cargar_datos(EJEMPLO)
        cls.config = Configuracion(
            poblacion=8, generaciones=3, elitismo=2, torneo=3, semilla=42,
        )

    def test_consumidor_extrae_lote_acotado_ordenado_y_no_bloqueante(self):
        eventos: queue.Queue[tuple[str, object]] = queue.Queue()
        for numero in range(EVENTOS_MAXIMOS_POR_CICLO + 9):
            eventos.put(("evento", numero))
        lote = extraer_lote_eventos(eventos, presupuesto=10.0)
        self.assertEqual(len(lote), EVENTOS_MAXIMOS_POR_CICLO)
        self.assertEqual([contenido for _tipo, contenido in lote], list(range(EVENTOS_MAXIMOS_POR_CICLO)))
        self.assertEqual(eventos.qsize(), 9)
        self.assertEqual(extraer_lote_eventos(queue.Queue()), [])

    def test_callbacks_llegan_desde_trabajador_en_orden_incluyendo_g0(self):
        for variante in ("clasico", "hibrido"):
            with self.subTest(variante=variante):
                eventos: queue.Queue[tuple[str, int, int]] = queue.Queue()
                config = replace(
                    self.config, variante=variante,
                    inicializacion_heuristica=variante == "hibrido",
                    porcentaje_inicializacion_heuristica=.25,
                    mutacion_adaptativa=variante == "hibrido",
                )

                def trabajador():
                    ejecutar(
                        self.problema, config,
                        callback=lambda r: eventos.put(("progreso", r.generacion, threading.get_ident())),
                        callback_instantanea=lambda s: eventos.put(("instantanea", s.generacion, threading.get_ident())),
                    )
                    eventos.put(("completa", -1, threading.get_ident()))

                hilo = threading.Thread(target=trabajador, name=f"prueba-{variante}")
                hilo.start()
                recibidos = []
                while True:
                    evento = eventos.get(timeout=5)
                    recibidos.append(evento)
                    if evento[0] == "completa":
                        break
                hilo.join(timeout=2)
                self.assertFalse(hilo.is_alive())
                principal = threading.get_ident()
                self.assertTrue(all(ident != principal for _tipo, _gen, ident in recibidos))
                self.assertEqual(
                    [gen for tipo, gen, _ident in recibidos if tipo == "progreso"],
                    [0, 1, 2, 3],
                )
                self.assertEqual(
                    [gen for tipo, gen, _ident in recibidos if tipo == "instantanea"],
                    [0, 1, 2, 3],
                )

    def test_modo_didactico_espera_confirmacion_sin_bloquear_al_consumidor(self):
        control = ControlDidactico(sincronizar_presentacion=True)
        control.notificar_captura(0)
        entrando = threading.Event()
        terminado = threading.Event()

        def esperar_presentacion():
            entrando.set()
            control.esperar()
            terminado.set()

        hilo = threading.Thread(target=esperar_presentacion)
        hilo.start()
        self.assertTrue(entrando.wait(timeout=1))
        self.assertTrue(hilo.is_alive())
        self.assertFalse(terminado.is_set())
        control.confirmar_presentacion(0)
        hilo.join(timeout=1)
        self.assertTrue(terminado.is_set())

    def test_paso_libera_exactamente_una_generacion_real(self):
        control = ControlDidactico()
        control.pausar()
        entradas_espera: queue.Queue[int] = queue.Queue()
        capturas = []

        def espera_controlada():
            entradas_espera.put(len(capturas))
            return control.esperar()

        hilo = threading.Thread(
            target=lambda: ejecutar(
                self.problema, replace(self.config, generaciones=3),
                callback_instantanea=capturas.append,
                esperar_si_pausado=espera_controlada,
            ),
        )
        hilo.start()
        self.assertEqual(entradas_espera.get(timeout=2), 1)
        self.assertEqual([s.generacion for s in capturas], [0])
        control.paso()
        self.assertEqual(entradas_espera.get(timeout=2), 2)
        self.assertEqual([s.generacion for s in capturas], [0, 1])
        self.assertTrue(hilo.is_alive())
        control.continuar()
        hilo.join(timeout=5)
        self.assertFalse(hilo.is_alive())
        self.assertEqual([s.generacion for s in capturas], [0, 1, 2, 3])

    def test_espera_didactica_se_registra_separada_del_calculo(self):
        control = ControlDidactico(retardo=.01)
        resultado = ejecutar(
            self.problema, self.config, esperar_si_pausado=control.esperar,
        )
        self.assertGreater(resultado.estadisticas.tiempo_espera_didactica, 0)
        self.assertGreaterEqual(resultado.estadisticas.tiempo_evolucion, 0)
        rapido = ejecutar(self.problema, self.config)
        self.assertEqual(rapido.estadisticas.tiempo_espera_didactica, 0)

    def test_calendario_reutiliza_celdas_y_sigue_la_ultima_captura(self):
        try:
            raiz = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - sólo entornos sin servidor gráfico
            self.skipTest(f"Tk no disponible: {exc}")
        raiz.withdraw()
        try:
            capturas = []
            ejecutar(self.problema, self.config, callback_instantanea=capturas.append)
            vista = VistaEvolucion(
                raiz, BASE, lambda: None, lambda: None,
                lambda: None, lambda: None, lambda: None,
            )
            vista.didactico.set(True)
            vista.preparar(self.problema, self.config, self.datos)
            vista.agregar_instantanea(capturas[0])
            raiz.update_idletasks()
            celdas_iniciales = {clave: id(widget) for clave, widget in vista.calendario._celdas.items()}
            vista.agregar_instantanea(capturas[1])
            raiz.update_idletasks()
            self.assertEqual(celdas_iniciales, {clave: id(widget) for clave, widget in vista.calendario._celdas.items()})
            self.assertEqual(vista.indice_actual, 1)
            self.assertEqual(vista.generacion.get(), "1")
            grupos = list(self.problema.grupos)
            if len(grupos) > 1:
                vista.identificador.set(grupos[1])
                vista._actualizar_vista()
                self.assertEqual(vista.identificador.get(), grupos[1])
        finally:
            raiz.destroy()


if __name__ == "__main__":
    unittest.main()
