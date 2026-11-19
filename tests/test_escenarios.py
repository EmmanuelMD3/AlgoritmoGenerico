"""Pruebas del generador académico reproducible de Fase 4."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from horarios_ga.datos import problema_desde_datos
from horarios_ga.escenarios import (
    ESPECIFICACIONES, cargar_escenario, generar_escenario_sintetico, huella_escenario,
)


BASE = Path(__file__).resolve().parents[1]


class TestsEscenarios(unittest.TestCase):
    def test_generacion_reproducible_y_huella(self):
        a = generar_escenario_sintetico("mediano", 81)
        b = generar_escenario_sintetico("mediano", 81)
        c = generar_escenario_sintetico("mediano", 82)
        self.assertEqual(a, b)
        self.assertEqual(huella_escenario(a), huella_escenario(b))
        self.assertNotEqual(huella_escenario(a), huella_escenario(c))

    def test_cantidades_objetivo_e_integridad(self):
        for tamano in ("mediano", "grande"):
            datos = generar_escenario_sintetico(tamano, 7)
            problema = problema_desde_datos(datos)
            especificacion = ESPECIFICACIONES[tamano]
            self.assertEqual(len(problema.grupos), especificacion["grupos"])
            self.assertEqual(len(problema.docentes), especificacion["docentes"])
            self.assertEqual(len(problema.salones), especificacion["salones"])
            self.assertTrue(all(problema.salones_validos))
            self.assertTrue(any(s.duracion > 1 for s in problema.sesiones))

    def test_testigo_no_se_expone_en_json(self):
        datos = generar_escenario_sintetico("mediano", 9)
        serializado = json.dumps(datos, ensure_ascii=False).lower()
        self.assertNotIn("cromosoma", serializado)
        self.assertNotIn("asignacion_conocida", serializado)
        self.assertTrue(datos["metadatos"]["factibilidad_testigo_validada"])

    def test_carga_json_personalizado_validado(self):
        original = generar_escenario_sintetico("mediano", 12)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "escenario.json"
            ruta.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            cargado = cargar_escenario("json", BASE, ruta_json=ruta)
        self.assertEqual(huella_escenario(original), huella_escenario(cargado))

    def test_tamano_no_admitido(self):
        with self.assertRaises(ValueError):
            generar_escenario_sintetico("pequeno", 1)


if __name__ == "__main__":
    unittest.main()

