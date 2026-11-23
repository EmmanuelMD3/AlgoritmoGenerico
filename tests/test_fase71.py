"""Persistencia canónica y edición académica introducidas en Fase 7.1."""
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from horarios_ga.datos import ConflictoArchivoExterno, cargar_datos, problema_desde_datos
from interfaz.aplicacion import PESTANAS_APLICACION
from interfaz.datos_academicos import (
    EstadoCuadriculaSemanal, ModeloDatosAcademicos, migrar_estructura_temporal,
)
from interfaz.experimentacion import configuracion_experimento_desde_valores
from main import ruta_datos_predeterminada


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


def valores_experimento() -> dict[str, str]:
    return {
        "nombre": "Activo", "descripcion": "", "modo": "comparacion",
        "poblacion": "10", "generaciones": "2", "prob_cruza": "0.8",
        "prob_mutacion": "0.1", "elitismo": "1", "torneo": "2",
        "semilla": "9", "parada_sin_mejora": "0",
        "objetivo_penalizacion_blanda": "0", "presupuesto_evaluaciones": "0",
        "repeticiones": "1", "repeticion_evolucion": "0",
    }


class TestsFase71(unittest.TestCase):
    def test_arranque_prioriza_configuracion_canonica_existente(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            datos = cargar_datos(EJEMPLO)
            datos["descripcion"] = "Configuración del usuario"
            canonica.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            self.assertEqual(modelo.datos["descripcion"], "Configuración del usuario")
            self.assertFalse(modelo.modificado)
            self.assertEqual(modelo.ruta_actual, canonica)

    def test_archivo_ausente_usa_plantilla_y_primer_guardado_canonico(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            self.assertTrue(modelo.modificado)
            self.assertTrue(modelo.creado_desde_plantilla)
            self.assertFalse(canonica.exists())
            modelo.guardar()
            self.assertTrue(canonica.exists())
            self.assertFalse(modelo.modificado)
            problema_desde_datos(cargar_datos(canonica))

    def test_guardado_atomico_reemplaza_unico_archivo_sin_temporales(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            modelo.guardar()
            nuevos = deepcopy(modelo.datos)
            nuevos["descripcion"] = "Segunda versión"
            modelo.reemplazar(nuevos)
            modelo.guardar()
            self.assertEqual(cargar_datos(canonica)["descripcion"], "Segunda versión")
            self.assertEqual([p.name for p in Path(temporal).iterdir()], [canonica.name])

    def test_fallo_de_reemplazo_conserva_original_y_limpia_temporal(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            modelo.guardar()
            original = canonica.read_bytes()
            nuevos = deepcopy(modelo.datos)
            nuevos["descripcion"] = "Cambio que no debe alcanzar el disco"
            modelo.reemplazar(nuevos)
            with patch("horarios_ga.datos.os.replace", side_effect=OSError("fallo simulado")):
                with self.assertRaises(OSError):
                    modelo.guardar()
            self.assertEqual(canonica.read_bytes(), original)
            self.assertTrue(modelo.modificado)
            self.assertEqual([p.name for p in Path(temporal).iterdir()], [canonica.name])

    def test_cambios_sucios_descartar_y_persistencia_tras_reinicio(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            guardados = deepcopy(modelo.datos)
            guardados["descripcion"] = "Versión persistente"
            modelo.reemplazar(guardados)
            modelo.guardar()

            editados = deepcopy(modelo.datos)
            editados["descripcion"] = "Sólo en memoria"
            modelo.reemplazar(editados)
            self.assertTrue(modelo.modificado)
            self.assertEqual(modelo.datos["descripcion"], "Sólo en memoria")
            modelo.descartar()
            self.assertFalse(modelo.modificado)
            self.assertEqual(modelo.datos["descripcion"], "Versión persistente")

            reiniciado = ModeloDatosAcademicos(EJEMPLO, canonica)
            self.assertEqual(reiniciado.datos["descripcion"], "Versión persistente")
            self.assertFalse(reiniciado.modificado)

    def test_cambio_externo_impide_sobrescritura_accidental(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            modelo.guardar()
            externo = cargar_datos(canonica)
            externo["descripcion"] = "Cambio externo"
            canonica.write_text(json.dumps(externo, ensure_ascii=False), encoding="utf-8")
            local = deepcopy(modelo.datos)
            local["descripcion"] = "Cambio local"
            modelo.reemplazar(local)
            with self.assertRaises(ConflictoArchivoExterno):
                modelo.guardar()
            self.assertEqual(cargar_datos(canonica)["descripcion"], "Cambio externo")

    def test_modo_canonico_rechaza_rutas_alternas(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo = ModeloDatosAcademicos(EJEMPLO, Path(temporal) / "configuracion_academica.json")
            with self.assertRaises(ValueError):
                modelo.guardar(Path(temporal) / "otra.json")

    def test_validacion_fallida_no_altera_archivo_guardado(self):
        with tempfile.TemporaryDirectory() as temporal:
            canonica = Path(temporal) / "configuracion_academica.json"
            modelo = ModeloDatosAcademicos(EJEMPLO, canonica)
            modelo.guardar()
            contenido_original = canonica.read_bytes()
            modelo.datos["dias"] = []
            with self.assertRaises(ValueError):
                modelo.guardar()
            self.assertEqual(canonica.read_bytes(), contenido_original)

    def test_instantanea_historica_no_cambia_con_el_modelo(self):
        modelo = ModeloDatosAcademicos(EJEMPLO)
        instantanea = modelo.instantanea()
        nuevos = deepcopy(modelo.datos)
        nuevos["descripcion"] = "Edición posterior"
        modelo.reemplazar(nuevos)
        self.assertNotEqual(instantanea["descripcion"], modelo.datos["descripcion"])
        problema_desde_datos(instantanea)

    def test_cuadricula_72_importa_preferencias_sin_crear_tercer_estado(self):
        estado = EstadoCuadriculaSemanal(["Lunes", "Martes"], ["08:00", "09:00"])
        estado.cargar({"Lunes": ["08:00"]}, {"Martes": ["09:00"]})
        no_disponible, preferidos = estado.exportar()
        self.assertEqual(no_disponible, {"Lunes": ["08:00"]})
        self.assertEqual(preferidos, {})
        self.assertEqual(estado.estados[("Martes", "09:00")], "disponible")
        estado.seleccionar_dia("Lunes")
        with self.assertRaises(ValueError):
            estado.marcar("preferido")

    def test_cuadricula_exportada_se_recupera_sin_invertir_semantica(self):
        original = EstadoCuadriculaSemanal(
            ["Lunes", "Martes"], ["08:00", "09:00", "10:00"],
        )
        original.cargar(
            {"Lunes": ["08:00"], "Martes": ["10:00"]},
            {"Lunes": ["09:00"]},
        )
        no_disponible, preferidos = original.exportar()
        recuperado = EstadoCuadriculaSemanal(original.dias, original.horas)
        recuperado.cargar(no_disponible, preferidos)
        self.assertEqual(recuperado.estados, original.estados)
        self.assertEqual(recuperado.exportar(), (no_disponible, preferidos))

    def test_cuadricula_grupo_no_admite_preferencias(self):
        estado = EstadoCuadriculaSemanal(["Lunes"], ["08:00"], permite_preferidos=False)
        estado.seleccion = {("Lunes", "08:00")}
        with self.assertRaises(ValueError):
            estado.marcar("preferido")

    def test_periodos_permitidos_distinguen_ausencia_y_subconjunto(self):
        estado = EstadoCuadriculaSemanal(["Lunes"], ["08:00", "09:00"], False)
        estado.cargar_periodos_permitidos(None)
        self.assertIsNone(estado.periodos_permitidos())
        estado.seleccion = {("Lunes", "09:00")}
        estado.marcar("no_disponible")
        self.assertEqual(estado.periodos_permitidos(), {"Lunes": ["08:00"]})

    def test_copia_de_dia_preserva_semantica_binaria(self):
        estado = EstadoCuadriculaSemanal(["Lunes", "Martes"], ["08:00", "09:00"])
        estado.cargar({"Lunes": ["08:00"]}, {"Lunes": ["09:00"]})
        estado.copiar_dia("Lunes", "Martes")
        self.assertEqual(estado.exportar()[0]["Martes"], ["08:00"])
        self.assertEqual(estado.exportar()[1], {})

    def test_cambio_temporal_poda_mapas_y_conserva_bloques_variables(self):
        datos = cargar_datos(EJEMPLO)
        nuevos, impacto = migrar_estructura_temporal(
            datos, ["Lunes", "Martes"], ["09:00", "09:30", "10:00", "10:30"], 30,
        )
        self.assertEqual(nuevos["metadatos"]["duracion_bloque_minutos"], 30)
        self.assertGreater(impacto.referencias_eliminadas, 0)
        problema = problema_desde_datos(nuevos)
        self.assertEqual(problema.duracion_bloque_minutos, 30)

    def test_laboratorio_predetermina_configuracion_activa(self):
        configuracion = configuracion_experimento_desde_valores(
            valores_experimento(), ("genetico",),
        )
        self.assertEqual(configuracion.escenario, "activo")

    def test_aplicacion_expone_exactamente_siete_pestanas(self):
        self.assertEqual(len(PESTANAS_APLICACION), 7)
        self.assertNotIn("Constructor de escenarios", PESTANAS_APLICACION)

    def test_consola_prioriza_canonica_y_retrocede_al_ejemplo(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            ejemplo = base / "datos" / "ejemplo.json"
            ejemplo.write_text("{}", encoding="utf-8")
            self.assertEqual(ruta_datos_predeterminada(base), ejemplo)
            canonica = base / "datos" / "configuracion_academica.json"
            canonica.write_text("{}", encoding="utf-8")
            self.assertEqual(ruta_datos_predeterminada(base), canonica)


if __name__ == "__main__":
    unittest.main()
