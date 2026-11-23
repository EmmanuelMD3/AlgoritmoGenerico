"""Disponibilidad binaria, migración y guardado aislado de Fase 7.2."""
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from horarios_ga.datos import ConflictoArchivoExterno, cargar_datos, problema_desde_datos
from horarios_ga.fitness import evaluar
from interfaz.aplicacion import Aplicacion, PESTANAS_APLICACION
from interfaz.datos_academicos import (
    EstadoCuadriculaSemanal,
    ModeloDatosAcademicos,
    aplicar_disponibilidad_entidad,
    calcular_horas_disponibles,
    contar_preferencias_docentes,
)


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


def _modelo_temporal(temporal: str) -> tuple[ModeloDatosAcademicos, Path]:
    canonica = Path(temporal) / "configuracion_academica.json"
    canonica.write_text(EJEMPLO.read_text(encoding="utf-8"), encoding="utf-8")
    return ModeloDatosAcademicos(EJEMPLO, canonica), canonica


def _datos_preferencia() -> dict:
    return {
        "dias": ["Lunes"],
        "horas": ["07:00", "08:00"],
        "salones": [{"id": "A1", "capacidad": 30, "tipo": "aula"}],
        "grupos": [{"id": "G1", "alumnos": 20}],
        "docentes": [{
            "id": "D1", "nombre": "Docente 1",
            "preferidos": {"Lunes": ["08:00"]},
        }],
        "clases": [{
            "id": "C1", "materia": "Materia", "grupo": "G1", "docente": "D1",
            "sesiones_semana": 1, "duracion_bloques": 1, "tipo_salon": "aula",
        }],
        "restricciones": {},
    }


def _destruir_app_prueba(app: Aplicacion) -> None:
    """Drena callbacks de dibujo de Matplotlib antes de destruir el intérprete Tk."""
    app.update_idletasks()
    for identificador in app.tk.call("after", "info"):
        try:
            app.after_cancel(identificador)
        except Exception:
            pass
    app.destroy()


class TestsFase72(unittest.TestCase):
    def test_estado_es_binario_y_el_clic_logico_alterna(self):
        estado = EstadoCuadriculaSemanal(["Lunes"], ["08:00"])
        self.assertEqual(estado.ESTADOS, {"disponible", "no_disponible"})
        estado.alternar_disponibilidad("Lunes", "08:00")
        self.assertEqual(estado.estados[("Lunes", "08:00")], "no_disponible")
        estado.alternar_disponibilidad("Lunes", "08:00")
        self.assertEqual(estado.estados[("Lunes", "08:00")], "disponible")
        with self.assertRaises(ValueError):
            estado.marcar("preferido")

    def test_dia_completo_y_acciones_masivas(self):
        estado = EstadoCuadriculaSemanal(
            ["Lunes", "Martes"], ["08:00", "09:00"],
        )
        estado.alternar_dia("Lunes")
        self.assertTrue(all(
            estado.estados[("Lunes", hora)] == "no_disponible"
            for hora in estado.horas
        ))
        estado.marcar_todo("disponible")
        self.assertTrue(all(valor == "disponible" for valor in estado.estados.values()))

    def test_horas_disponibles_respetan_duracion_de_30_minutos(self):
        estado = EstadoCuadriculaSemanal(
            ["Lunes", "Martes"], ["08:00", "08:30", "09:00"],
        )
        estado.alternar_disponibilidad("Lunes", "08:00")
        self.assertEqual(calcular_horas_disponibles(estado, 30), 2.5)

    def test_conversion_json_binaria_ignora_preferencias_anteriores(self):
        estado = EstadoCuadriculaSemanal(["Lunes"], ["07:00", "08:00"])
        estado.cargar({"Lunes": ["07:00"]}, {"Lunes": ["08:00"]})
        self.assertEqual(estado.exportar_no_disponible(), {"Lunes": ["07:00"]})
        self.assertNotIn("preferido", estado.estados.values())

    def test_guardado_aislado_d1_preserva_otras_entidades_y_borradores(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            modelo.preparar_disponibilidad_binaria()
            d2_original = deepcopy(cargar_datos(canonica)["docentes"][1])
            pendientes = deepcopy(modelo.datos)
            pendientes["descripcion"] = "Cambio general sólo en memoria"
            pendientes["docentes"][1]["nombre"] = "D2 pendiente"
            modelo.reemplazar(pendientes)

            mapa = {"Lunes": ["07:00", "08:00"]}
            modelo.guardar_disponibilidad("Docente", "D1", mapa)
            disco = cargar_datos(canonica)
            self.assertEqual(disco["docentes"][0]["no_disponible"], mapa)
            self.assertEqual(disco["docentes"][1], d2_original)
            self.assertNotEqual(disco["descripcion"], "Cambio general sólo en memoria")
            self.assertEqual(modelo.datos["docentes"][1]["nombre"], "D2 pendiente")
            self.assertEqual(modelo.datos["descripcion"], "Cambio general sólo en memoria")
            self.assertTrue(modelo.modificado)

    def test_guardado_aislado_g1_y_persistencia_al_reiniciar(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            mapa = {"Viernes": ["13:00", "14:00"]}
            modelo.guardar_disponibilidad("Grupo", "ISC-301", mapa)
            reiniciado = ModeloDatosAcademicos(EJEMPLO, canonica)
            grupo = next(x for x in reiniciado.datos["grupos"] if x["id"] == "ISC-301")
            self.assertEqual(grupo["no_disponible"], mapa)

    def test_guardado_general_persiste_todos_los_cambios(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            nuevos = aplicar_disponibilidad_entidad(
                modelo.datos, "Docente", "D1", {"Martes": ["09:00"]},
            )
            nuevos["descripcion"] = "Guardado general"
            modelo.reemplazar(nuevos)
            modelo.guardar()
            disco = cargar_datos(canonica)
            self.assertEqual(disco["descripcion"], "Guardado general")
            self.assertEqual(disco["docentes"][0]["no_disponible"], {"Martes": ["09:00"]})
            self.assertFalse(modelo.modificado)

    def test_conflicto_externo_cancela_o_se_resuelve_sin_pisar_datos_ajenos(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            local = deepcopy(modelo.datos)
            local["docentes"][1]["nombre"] = "Borrador local D2"
            modelo.reemplazar(local)
            externo = cargar_datos(canonica)
            externo["descripcion"] = "Edición externa preservada"
            canonica.write_text(json.dumps(externo, ensure_ascii=False), encoding="utf-8")
            mapa = {"Lunes": ["07:00"]}
            with self.assertRaises(ConflictoArchivoExterno):
                modelo.guardar_disponibilidad("Grupo", "ISC-301", mapa)
            modelo.guardar_disponibilidad(
                "Grupo", "ISC-301", mapa, resolver_conflicto=True,
            )
            disco = cargar_datos(canonica)
            self.assertEqual(disco["descripcion"], "Edición externa preservada")
            self.assertEqual(disco["grupos"][0]["no_disponible"], mapa)
            self.assertEqual(modelo.datos["descripcion"], "Edición externa preservada")
            self.assertEqual(modelo.datos["docentes"][1]["nombre"], "Borrador local D2")
            self.assertTrue(modelo.modificado)

    def test_reemplazo_aislado_es_atomico_y_no_deja_temporales(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            modelo.guardar_disponibilidad(
                "Docente", "D1", {"Lunes": ["07:00"]},
            )
            self.assertEqual([p.name for p in Path(temporal).iterdir()], [canonica.name])

    def test_migracion_desactiva_efecto_sin_borrar_datos_historicos(self):
        with tempfile.TemporaryDirectory() as temporal:
            modelo, canonica = _modelo_temporal(temporal)
            cantidad = contar_preferencias_docentes(modelo.datos)
            self.assertGreater(cantidad, 0)
            self.assertEqual(modelo.preparar_disponibilidad_binaria(), cantidad)
            self.assertFalse(modelo.validar().preferencias_docentes_activas)
            preferidos = deepcopy(modelo.datos["docentes"][0]["preferidos"])
            modelo.guardar_disponibilidad(
                "Docente", "D1", modelo.datos["docentes"][0]["no_disponible"],
            )
            disco = cargar_datos(canonica)
            self.assertFalse(disco["restricciones"]["preferencias_docentes_activas"])
            self.assertEqual(disco["docentes"][0]["preferidos"], preferidos)

    def test_json_anterior_conserva_fitness_historico_hasta_migracion_explicita(self):
        datos = _datos_preferencia()
        historico = problema_desde_datos(datos)
        self.assertEqual(evaluar(historico, ((0, 0, 0),)).fuera_preferencia_docente, 1)
        migrados = deepcopy(datos)
        migrados["restricciones"]["preferencias_docentes_activas"] = False
        actual = problema_desde_datos(migrados)
        evaluacion = evaluar(actual, ((0, 0, 0),))
        self.assertEqual(evaluacion.fuera_preferencia_docente, 0)
        self.assertEqual(evaluacion.penalizacion_blanda, 0)

    def test_interfaz_carga_automaticamente_d1_d2_y_edita_con_clic(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            (base / "datos" / "ejemplo.json").write_text(
                EJEMPLO.read_text(encoding="utf-8"), encoding="utf-8",
            )
            (base / "datos" / "configuracion_academica.json").write_text(
                EJEMPLO.read_text(encoding="utf-8"), encoding="utf-8",
            )
            app = Aplicacion(base)
            app.withdraw()
            try:
                vista = app.datos
                self.assertEqual(tuple(vista.combo_ambito.cget("values")), ("Docente", "Grupo"))
                self.assertEqual(vista._clave_disponibilidad, ("Docente", "D1"))
                etiqueta_d2 = vista._etiquetas_por_entidad["D2"]
                vista.entidad_disponibilidad.set(etiqueta_d2)
                vista.combo_entidad.event_generate("<<ComboboxSelected>>")
                app.update()
                self.assertEqual(vista._clave_disponibilidad, ("Docente", "D2"))
                clave = next(iter(vista.editor_semanal.botones))
                anterior = vista.editor_semanal.estado.estados[clave]
                vista.editor_semanal.botones[clave].invoke()
                app.update()
                self.assertNotEqual(vista.editor_semanal.estado.estados[clave], anterior)
                self.assertTrue(vista._borrador_disponibilidad_sucio)
            finally:
                _destruir_app_prueba(app)

    def test_cambio_entidad_pendiente_puede_cancelarse(self):
        with tempfile.TemporaryDirectory() as temporal:
            base = Path(temporal)
            (base / "datos").mkdir()
            for nombre in ("ejemplo.json", "configuracion_academica.json"):
                (base / "datos" / nombre).write_text(
                    EJEMPLO.read_text(encoding="utf-8"), encoding="utf-8",
                )
            app = Aplicacion(base)
            app.withdraw()
            try:
                vista = app.datos
                next(iter(vista.editor_semanal.botones.values())).invoke()
                destino = vista._etiquetas_por_entidad["D2"]
                with patch(
                    "interfaz.datos_academicos.messagebox.askyesnocancel",
                    return_value=None,
                ):
                    vista.entidad_disponibilidad.set(destino)
                    vista._seleccion_disponibilidad_cambio()
                self.assertEqual(vista._clave_disponibilidad, ("Docente", "D1"))
                self.assertTrue(vista._borrador_disponibilidad_sucio)
            finally:
                _destruir_app_prueba(app)

    def test_siete_secciones_y_mismo_modelo_para_optimizacion_experimentacion(self):
        self.assertEqual(len(PESTANAS_APLICACION), 7)
        with tempfile.TemporaryDirectory() as temporal:
            modelo, _canonica = _modelo_temporal(temporal)
            modelo.preparar_disponibilidad_binaria()
            instantanea = modelo.instantanea()
            self.assertFalse(
                problema_desde_datos(instantanea).preferencias_docentes_activas,
            )
            # Una copia usada por experimentación conserva el mismo contrato y
            # no modifica la configuración compartida.
            copia_experimento = deepcopy(instantanea)
            self.assertEqual(copia_experimento, instantanea)


if __name__ == "__main__":
    unittest.main()
