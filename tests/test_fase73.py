"""Importación segura y activación inmediata de escenarios JSON (Fase 7.3)."""
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from horarios_ga.datos import (
    ConflictoArchivoExterno, cargar_datos, problema_desde_datos,
)
from horarios_ga.genetico import Configuracion, ejecutar
from horarios_ga.importacion import preparar_importacion
from interfaz.aplicacion import Aplicacion
from interfaz.datos_academicos import ModeloDatosAcademicos


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


def _datos_minimos(nombre: str = "Escenario importado") -> dict:
    return {
        "descripcion": "Escenario de prueba de importación",
        "dias": ["Lunes", "Martes"],
        "horas": ["08:00", "09:00", "10:00"],
        "salones": [{"id": "A1", "capacidad": 35, "tipo": "aula"}],
        "grupos": [{
            "id": "G1", "nombre": "Grupo 1", "alumnos": 20,
            "no_disponible": {"Martes": ["10:00"]},
        }],
        "docentes": [{
            "id": "D1", "nombre": "Docente 1",
            "no_disponible": {"Lunes": ["10:00"]},
        }],
        "clases": [{
            "id": "C1", "materia_id": "M1", "materia": "Materia 1",
            "grupo": "G1", "docente": "D1", "sesiones_semana": 1,
            "duracion_bloques": 2, "tipo_salon": "aula",
            "periodos_permitidos": {
                "Lunes": ["08:00", "09:00"],
                "Martes": ["08:00", "09:00"],
            },
        }],
        "restricciones": {
            "franjas_no_lectivas": {}, "umbral_jornada_larga": 3,
        },
        "metadatos": {
            "nombre": nombre, "duracion_bloque_minutos": 60,
        },
    }


def _escribir_json(ruta: Path, datos: dict) -> bytes:
    contenido = (json.dumps(datos, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ruta.write_bytes(contenido)
    return contenido


def _modelo_temporal(carpeta: Path) -> tuple[ModeloDatosAcademicos, Path]:
    canonica = carpeta / "configuracion_academica.json"
    canonica.write_bytes(EJEMPLO.read_bytes())
    return ModeloDatosAcademicos(EJEMPLO, canonica), canonica


def _destruir_app(app: Aplicacion) -> None:
    app.update_idletasks()
    for identificador in app.tk.call("after", "info"):
        try:
            app.after_cancel(identificador)
        except Exception:
            pass
    app.destroy()


class TestsFase73(unittest.TestCase):
    def test_vista_previa_valida_muestra_conteos_y_no_toca_origen(self):
        with tempfile.TemporaryDirectory() as temporal:
            origen = Path(temporal) / "escenario.json"
            original = _escribir_json(origen, _datos_minimos("Importación válida"))
            previa = preparar_importacion(origen)
            self.assertTrue(previa.importable)
            self.assertEqual(previa.nombre, "Importación válida")
            self.assertEqual(
                (previa.docentes, previa.grupos, previa.materias,
                 previa.sesiones, previa.salones),
                (1, 1, 1, 1, 1),
            )
            self.assertEqual(previa.rango_horario, "08:00 – 11:00")
            self.assertEqual(origen.read_bytes(), original)

    def test_formato_anterior_sin_metadatos_ni_restricciones_usa_valores_historicos(self):
        with tempfile.TemporaryDirectory() as temporal:
            datos = _datos_minimos()
            datos.pop("metadatos")
            datos.pop("restricciones")
            origen = Path(temporal) / "anterior.json"
            _escribir_json(origen, datos)
            previa = preparar_importacion(origen)
            self.assertTrue(previa.importable)
            self.assertEqual(previa.duracion_bloque_minutos, 60)
            self.assertEqual(previa.nombre, datos["descripcion"])

    def test_json_malformado_y_codificacion_invalida_producen_error_comprensible(self):
        with tempfile.TemporaryDirectory() as temporal:
            malformado = Path(temporal) / "malformado.json"
            malformado.write_text('{"dias": [}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "línea"):
                preparar_importacion(malformado)
            codificacion = Path(temporal) / "codificacion.json"
            codificacion.write_bytes(b"\xff\xfe\x00")
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                preparar_importacion(codificacion)

    def test_archivo_inexistente_extension_y_tamano_se_rechazan(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            with self.assertRaises(FileNotFoundError):
                preparar_importacion(carpeta / "ausente.json")
            texto = carpeta / "escenario.txt"
            texto.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "extensión"):
                preparar_importacion(texto)
            grande = carpeta / "grande.json"
            grande.write_text("{}  ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "límite"):
                preparar_importacion(grande, limite_bytes=2)

    def test_permiso_de_lectura_se_reporta_sin_mutaciones(self):
        with tempfile.TemporaryDirectory() as temporal:
            origen = Path(temporal) / "sin_permiso.json"
            _escribir_json(origen, _datos_minimos())
            with patch("pathlib.Path.open", side_effect=PermissionError("acceso denegado")):
                with self.assertRaisesRegex(OSError, "No se pudo leer"):
                    preparar_importacion(origen)

    def test_referencias_duracion_y_duplicados_invalidos_no_son_importables(self):
        casos = []
        referencia = _datos_minimos()
        referencia["clases"][0]["docente"] = "D404"
        casos.append((referencia, "docente_inexistente"))
        duracion = _datos_minimos()
        duracion["clases"][0]["duracion_bloques"] = 99
        casos.append((duracion, "sesion_invalida"))
        duplicado = _datos_minimos()
        duplicado["salones"].append(deepcopy(duplicado["salones"][0]))
        casos.append((duplicado, "id_duplicado"))
        with tempfile.TemporaryDirectory() as temporal:
            for indice, (datos, codigo) in enumerate(casos):
                with self.subTest(codigo=codigo):
                    ruta = Path(temporal) / f"invalido_{indice}.json"
                    _escribir_json(ruta, datos)
                    previa = preparar_importacion(ruta)
                    self.assertFalse(previa.importable)
                    self.assertIn(codigo, {x.codigo for x in previa.validacion.errores})

    def test_objetos_de_configuracion_mal_tipados_se_muestran_como_error(self):
        with tempfile.TemporaryDirectory() as temporal:
            datos = _datos_minimos()
            datos["metadatos"] = ["no es un objeto"]
            ruta = Path(temporal) / "metadatos_invalidos.json"
            _escribir_json(ruta, datos)
            previa = preparar_importacion(ruta)
            self.assertFalse(previa.importable)
            self.assertIn("modelo_invalido", {x.codigo for x in previa.validacion.errores})

    def test_disponibilidad_y_periodos_fuera_del_calendario_se_rechazan(self):
        with tempfile.TemporaryDirectory() as temporal:
            datos = _datos_minimos()
            datos["grupos"][0]["no_disponible"] = {"Domingo": ["08:00"]}
            ruta = Path(temporal) / "dia_invalido.json"
            _escribir_json(ruta, datos)
            previa = preparar_importacion(ruta)
            self.assertFalse(previa.importable)
            self.assertTrue(any("Día desconocido" in x.mensaje for x in previa.validacion.errores))

    def test_importacion_es_atomica_actualiza_memoria_y_no_modifica_origen(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, canonica = _modelo_temporal(carpeta)
            origen = carpeta / "fuente.json"
            original = _escribir_json(origen, _datos_minimos())
            previa = preparar_importacion(origen)
            modelo.importar_configuracion(previa.datos)
            self.assertEqual(origen.read_bytes(), original)
            self.assertEqual(modelo.datos["metadatos"]["nombre"], "Escenario importado")
            self.assertEqual(cargar_datos(canonica), modelo.datos)
            self.assertFalse(modelo.modificado)
            self.assertFalse(any(p.suffix == ".tmp" for p in carpeta.iterdir()))

    def test_error_de_escritura_conserva_disco_y_memoria_anteriores(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, canonica = _modelo_temporal(carpeta)
            disco_anterior = canonica.read_bytes()
            memoria_anterior = deepcopy(modelo.datos)
            with patch("horarios_ga.datos.os.replace", side_effect=PermissionError("bloqueado")):
                with self.assertRaises(PermissionError):
                    modelo.importar_configuracion(_datos_minimos())
            self.assertEqual(canonica.read_bytes(), disco_anterior)
            self.assertEqual(modelo.datos, memoria_anterior)
            self.assertFalse(any(p.suffix == ".tmp" for p in carpeta.iterdir()))

    def test_conflicto_externo_exige_resolucion_y_reintento_explicito(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, canonica = _modelo_temporal(carpeta)
            externo = cargar_datos(canonica)
            externo["descripcion"] = "Cambio externo"
            _escribir_json(canonica, externo)
            with self.assertRaises(ConflictoArchivoExterno):
                modelo.importar_configuracion(_datos_minimos())
            self.assertEqual(cargar_datos(canonica)["descripcion"], "Cambio externo")
            modelo.importar_configuracion(_datos_minimos(), resolver_conflicto=True)
            self.assertEqual(cargar_datos(canonica)["metadatos"]["nombre"], "Escenario importado")

    def test_reinicio_carga_exactamente_el_escenario_importado(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, canonica = _modelo_temporal(carpeta)
            modelo.importar_configuracion(_datos_minimos("Persistente"))
            reiniciado = ModeloDatosAcademicos(EJEMPLO, canonica)
            self.assertEqual(reiniciado.datos, modelo.datos)
            self.assertEqual(reiniciado.datos["metadatos"]["nombre"], "Persistente")

    def test_preferencias_anteriores_se_conservan_pero_quedan_desactivadas(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, canonica = _modelo_temporal(carpeta)
            datos = _datos_minimos()
            datos["docentes"][0]["preferidos"] = {"Lunes": ["08:00"]}
            modelo.importar_configuracion(datos)
            disco = cargar_datos(canonica)
            self.assertEqual(disco["docentes"][0]["preferidos"], {"Lunes": ["08:00"]})
            self.assertFalse(disco["restricciones"]["preferencias_docentes_activas"])

    def test_archivo_historico_no_cambia_durante_la_importacion(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            modelo, _ = _modelo_temporal(carpeta)
            historico = carpeta / "resultado_historico.json"
            historico.write_bytes(b'{"resultado": "anterior"}\n')
            original = historico.read_bytes()
            modelo.importar_configuracion(_datos_minimos())
            self.assertEqual(historico.read_bytes(), original)

    def test_escenario_importado_ejecuta_algoritmos_clasico_e_hibrido(self):
        problema = problema_desde_datos(_datos_minimos())
        clasica = Configuracion(
            poblacion=8, generaciones=2, elitismo=1, torneo=2, semilla=73,
        )
        hibrida = replace(
            clasica, variante="hibrido", inicializacion_heuristica=True,
            porcentaje_inicializacion_heuristica=.25, busqueda_local=True,
            frecuencia_busqueda_local=1, porcentaje_busqueda_local=.25,
            evaluaciones_busqueda_local=2, mejoras_busqueda_local=1,
            mutacion_adaptativa=True,
        )
        for configuracion in (clasica, hibrida):
            with self.subTest(variante=configuracion.variante):
                resultado = ejecutar(problema, configuracion)
                problema.validar_cromosoma(resultado.cromosoma)
                self.assertEqual(len(resultado.cromosoma), len(problema.sesiones))

    def test_interfaz_activa_importacion_en_todas_las_vistas_y_marca_resultado_historico(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            for nombre in ("ejemplo.json", "configuracion_academica.json"):
                (base / "datos" / nombre).write_bytes(EJEMPLO.read_bytes())
            origen = base / "escenario_nuevo.json"
            _escribir_json(origen, _datos_minimos("Nuevo escenario UI"))
            previa = preparar_importacion(origen)
            app = Aplicacion(base)
            app.withdraw()
            try:
                app.resultado = object()
                app.huella_ejecucion = "0" * 64
                app.nombre_ejecucion = "Resultado anterior"
                app.optimizacion.establecer_origen_resultado = Mock()
                with (
                    patch("interfaz.datos_academicos.messagebox.showinfo"),
                    patch(
                        "interfaz.datos_academicos.messagebox.askyesnocancel",
                        return_value=False,
                    ),
                ):
                    self.assertTrue(app.datos._aplicar_importacion(previa))
                self.assertEqual(app.datos.kpis["docentes"].get(), "1")
                self.assertIn("Nuevo escenario UI", app.optimizacion.escenario_actual.get())
                self.assertEqual(
                    app.experimentacion.escenario_activo_datos,
                    app.modelo_datos.datos,
                )
                app.optimizacion.establecer_origen_resultado.assert_called_with(
                    "Resultado anterior", "0" * 64, historico=True,
                )
                self.assertEqual(app.datos.estado_importacion.get(), "Importación completada")
            finally:
                _destruir_app(app)

    def test_cancelar_seleccion_y_cancelar_cambios_pendientes_no_alteran_archivo(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            for nombre in ("ejemplo.json", "configuracion_academica.json"):
                (base / "datos" / nombre).write_bytes(EJEMPLO.read_bytes())
            app = Aplicacion(base)
            app.withdraw()
            try:
                canonica = base / "datos" / "configuracion_academica.json"
                anterior = canonica.read_bytes()
                with patch(
                    "interfaz.datos_academicos.filedialog.askopenfilename",
                    return_value="",
                ):
                    self.assertFalse(app.datos._importar_escenario_json())
                cambios = deepcopy(app.modelo_datos.datos)
                cambios["descripcion"] = "Borrador local"
                app.modelo_datos.reemplazar(cambios)
                with patch(
                    "interfaz.datos_academicos.messagebox.askyesnocancel",
                    return_value=None,
                ):
                    self.assertFalse(app.datos._resolver_cambios_para_importar())
                self.assertEqual(canonica.read_bytes(), anterior)
                self.assertEqual(app.modelo_datos.datos["descripcion"], "Borrador local")
            finally:
                _destruir_app(app)

    def test_cancelar_vista_previa_no_reemplaza_configuracion(self):
        class DialogoCancelado:
            def __init__(self, _padre, _previa):
                self.confirmado = False

        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            for nombre in ("ejemplo.json", "configuracion_academica.json"):
                (base / "datos" / nombre).write_bytes(EJEMPLO.read_bytes())
            origen = base / "seleccionado.json"
            _escribir_json(origen, _datos_minimos())
            app = Aplicacion(base)
            app.withdraw()
            try:
                canonica = base / "datos" / "configuracion_academica.json"
                anterior = canonica.read_bytes()
                with (
                    patch(
                        "interfaz.datos_academicos.filedialog.askopenfilename",
                        return_value=str(origen),
                    ),
                    patch(
                        "interfaz.datos_academicos.DialogoVistaPreviaImportacion",
                        DialogoCancelado,
                    ),
                    patch.object(app.datos, "wait_window"),
                ):
                    self.assertFalse(app.datos._importar_escenario_json())
                self.assertEqual(canonica.read_bytes(), anterior)
                self.assertEqual(app.datos.estado_importacion.get(), "Importación cancelada")
            finally:
                _destruir_app(app)


if __name__ == "__main__":
    unittest.main()
