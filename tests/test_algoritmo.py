"""Pruebas unitarias con unittest (incluido en Python)."""
import json
import random
import tempfile
import unittest
from pathlib import Path

from horarios_ga.datos import cargar_problema
from horarios_ga.fitness import evaluar
from horarios_ga.genetico import Configuracion, cruzar, ejecutar, individuo_aleatorio, mutar
from horarios_ga.reportes import exportar


EJEMPLO = Path(__file__).resolve().parents[1] / "datos" / "ejemplo.json"


class TestsAlgoritmo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problema = cargar_problema(EJEMPLO)

    def test_datos_cargados_y_sesiones_expandibles(self):
        self.assertEqual(len(self.problema.sesiones), 36)
        self.assertEqual(len(self.problema.grupos), 3)
        self.assertTrue(all(self.problema.salones_validos))

    def test_genes_validos_al_azar_y_tras_operadores(self):
        rng = random.Random(10)
        for _ in range(30):
            a = individuo_aleatorio(self.problema, rng)
            b = individuo_aleatorio(self.problema, rng)
            hijos = cruzar(a, b, rng)
            for hijo in hijos:
                mutado = mutar(self.problema, hijo, 0.6, rng)
                self.problema.validar_cromosoma(mutado)

    def test_penaliza_choques_y_disponibilidad(self):
        # C01-S1 y C01-S2 tienen el mismo grupo/docente y son sesiones
        # de dos bloques en un laboratorio; se pisan ambos bloques.
        genes = list(individuo_aleatorio(self.problema, random.Random(11)))
        genes[0] = (0, 0, 2)
        genes[1] = (0, 0, 2)
        ev = evaluar(self.problema, tuple(genes))
        self.assertGreaterEqual(ev.conflicto_docente, 2)
        self.assertGreaterEqual(ev.conflicto_grupo, 2)
        self.assertGreaterEqual(ev.conflicto_salon, 2)
        self.assertGreaterEqual(ev.fuera_disponibilidad, 2)  # D1 no Lunes 07/08

    def test_rechaza_salones_incompatibles(self):
        genes = list(individuo_aleatorio(self.problema, random.Random(1)))
        genes[0] = (0, 0, 0)  # C01 exige laboratorio, A1 es aula
        with self.assertRaises(ValueError):
            evaluar(self.problema, tuple(genes))

    def test_config_invalida(self):
        with self.assertRaises(ValueError):
            Configuracion(poblacion=3).validar()
        with self.assertRaises(ValueError):
            Configuracion(prob_mutacion=1.8).validar()

    def test_reproduce_semilla_y_mejora_conflictos(self):
        config = Configuracion(poblacion=42, generaciones=45, semilla=22)
        a = ejecutar(self.problema, config)
        b = ejecutar(self.problema, config)
        self.assertEqual(a.cromosoma, b.cromosoma)
        self.assertLessEqual(a.evaluacion.duras, a.historial[0].conflictos_duros)
        self.assertEqual(len(a.historial), 46)
        # Gracias al elitismo, los conflictos duros no deben aumentar nunca.
        self.assertTrue(all(
            later.conflictos_duros <= earlier.conflictos_duros
            for earlier, later in zip(a.historial, a.historial[1:])
        ))

    def test_exportacion(self):
        r = ejecutar(self.problema, Configuracion(poblacion=12, generaciones=2))
        with tempfile.TemporaryDirectory() as tmp:
            archivos = exportar(self.problema, r, tmp)
            nombres = {p.name for p in archivos}
            self.assertTrue({"horario_sesiones.csv", "horarios_por_grupo.html", "evolucion.csv", "resumen.json"} <= nombres)
            contenido = json.loads((Path(tmp)/"resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(contenido["sesiones"], 36)


if __name__ == "__main__":
    unittest.main()
