"""Pruebas del constructor y los lotes de escenarios de Fase 7."""
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from horarios_ga.constructor_escenarios import (
    ConfiguracionEscenario,
    GestorEscenarios,
    crear_escenario_manual,
    generar_escenario_configurable,
    generar_lote,
    resumen_escenario,
    validar_escenario_detallado,
)
from horarios_ga.datos import cargar_datos, guardar_datos, problema_desde_datos
from horarios_ga.escenarios import huella_escenario
from horarios_ga.experimentos import (
    ConfiguracionExperimento,
    ejecutar_lote_escenarios,
    exportar_experimento,
)
from horarios_ga.genetico import Configuracion, ejecutar
from horarios_ga.reportes import hora_final
from interfaz.datos_academicos import ModeloDatosAcademicos


BASE = Path(__file__).resolve().parents[1]
EJEMPLO = BASE / "datos" / "ejemplo.json"


def configuracion_pequena(**cambios) -> ConfiguracionEscenario:
    base = ConfiguracionEscenario(
        nombre="Prueba Fase 7", docentes=5, grupos=3, materias=5, salones=4,
        sesiones_por_asignacion=2, duracion_sesion=1, dias_lectivos=5,
        hora_inicio="08:00", hora_fin="15:00", semilla=71,
    )
    return replace(base, **cambios)


class TestsFase7(unittest.TestCase):
    def test_json_anterior_conserva_bloques_de_sesenta_minutos(self):
        problema = problema_desde_datos(cargar_datos(EJEMPLO))
        self.assertEqual(problema.duracion_bloque_minutos, 60)

    def test_bloques_variables_se_reflejan_en_hora_final(self):
        datos = crear_escenario_manual()
        datos["horas"] = ["08:00", "08:30", "09:00"]
        datos["metadatos"]["duracion_bloque_minutos"] = 30
        datos["clases"][0]["duracion_bloques"] = 2
        problema = problema_desde_datos(datos)
        self.assertEqual(hora_final(problema, 0, 2), "09:00")

    def test_manual_se_guarda_y_recarga_sin_cambiar(self):
        datos = crear_escenario_manual("Manual persistente")
        with tempfile.TemporaryDirectory() as temporal:
            ruta = guardar_datos(datos, Path(temporal) / "manual.json")
            self.assertEqual(cargar_datos(ruta), datos)
            self.assertTrue(validar_escenario_detallado(cargar_datos(ruta)).correcto)

    def test_generacion_es_exactamente_reproducible(self):
        config = configuracion_pequena()
        primero = generar_escenario_configurable(config)
        segundo = generar_escenario_configurable(config)
        self.assertEqual(primero, segundo)
        self.assertEqual(huella_escenario(primero), huella_escenario(segundo))

    def test_materias_asignaciones_y_sesiones_no_se_confunden(self):
        datos = generar_escenario_configurable(configuracion_pequena(materias=3, grupos=5))
        resumen = resumen_escenario(datos)
        self.assertEqual(resumen["materias"], 3)
        self.assertEqual(resumen["asignaciones"], 5)
        self.assertEqual(resumen["sesiones"], 10)

    def test_sesiones_multibloque_e_ids_estables(self):
        datos = generar_escenario_configurable(
            configuracion_pequena(duracion_sesion=2, sesiones_por_asignacion=2)
        )
        problema = problema_desde_datos(datos)
        self.assertTrue(all(sesion.duracion == 2 for sesion in problema.sesiones))
        self.assertEqual(problema.sesiones[0].id, "C0001-S1")
        self.assertEqual(problema.sesiones[1].id, "C0001-S2")

    def test_perfil_dificil_reduce_disponibilidad_sin_certificar_imposibilidad(self):
        facil = generar_escenario_configurable(configuracion_pequena(perfil="facil"))
        dificil = generar_escenario_configurable(configuracion_pequena(perfil="dificil"))
        indisponibles = lambda d: sum(
            len(horas) for entidad in d["docentes"] + d["grupos"]
            for horas in entidad.get("no_disponible", {}).values()
        )
        self.assertGreater(indisponibles(dificil), indisponibles(facil))
        self.assertNotIn("imposible", json.dumps(dificil, ensure_ascii=False).lower())

    def test_testigo_conocido_se_valida_pero_no_se_publica(self):
        datos = generar_escenario_configurable(configuracion_pequena(factibilidad_conocida=True))
        self.assertTrue(datos["metadatos"]["factibilidad_testigo_validada"])
        self.assertNotIn("solucion", datos)
        self.assertNotIn("cromosoma", datos)

    def test_estres_elimina_garantia_de_factibilidad(self):
        datos = generar_escenario_configurable(configuracion_pequena(estres=True))
        self.assertFalse(datos["metadatos"]["factibilidad_testigo_validada"])

    def test_validacion_distingue_errores_y_advertencias(self):
        roto = crear_escenario_manual()
        roto["clases"][0]["docente"] = "NO-EXISTE"
        resultado = validar_escenario_detallado(roto)
        self.assertFalse(resultado.correcto)
        self.assertIn("docente_inexistente", {i.codigo for i in resultado.errores})

        limitado = crear_escenario_manual()
        limitado["docentes"][0]["no_disponible"] = {"Lunes": ["08:00", "09:00"]}
        resultado = validar_escenario_detallado(limitado)
        codigos = {i.codigo for i in resultado.advertencias}
        self.assertTrue(resultado.correcto)
        self.assertIn("disponibilidad_vacia", codigos)
        self.assertIn("sin_ubicacion", codigos)

    def test_gestor_confina_nombres_y_operaciones_al_directorio(self):
        with tempfile.TemporaryDirectory() as temporal:
            gestor = GestorEscenarios(temporal)
            ruta = gestor.guardar("../escenario seguro", crear_escenario_manual())
            self.assertEqual(ruta.parent, Path(temporal).resolve())
            copia = gestor.duplicar(ruta, "Copia")
            renombrada = gestor.renombrar(copia, "Renombrada")
            self.assertTrue(ruta.exists() and renombrada.exists())
            self.assertFalse(copia.exists())

    def test_lote_genera_cinco_json_identificables_y_manifiesto(self):
        with tempfile.TemporaryDirectory() as temporal:
            registros = generar_lote(
                configuracion_pequena(nombre="Lote"), 5, temporal,
                semilla_inicial=200,
            )
            self.assertEqual(len(registros), 5)
            self.assertEqual([r.semilla for r in registros], list(range(200, 205)))
            self.assertEqual(len({r.huella for r in registros}), 5)
            self.assertTrue(all(r.ruta.exists() and r.valido for r in registros))
            manifiesto = json.loads((Path(temporal) / "manifiesto_lote.json").read_text(encoding="utf-8"))
            self.assertEqual(manifiesto["cantidad_generada"], 5)
            self.assertFalse(manifiesto["cancelado"])

    def test_lote_es_cancelable_y_conserva_resultados_completos(self):
        with tempfile.TemporaryDirectory() as temporal:
            detener = False

            def al_generar(_registro):
                nonlocal detener
                detener = True

            registros = generar_lote(
                configuracion_pequena(nombre="Cancelado"), 4, temporal,
                debe_cancelar=lambda: detener, al_generar=al_generar,
            )
            self.assertEqual(len(registros), 1)
            self.assertTrue(registros[0].ruta.exists())
            manifiesto = json.loads((Path(temporal) / "manifiesto_lote.json").read_text(encoding="utf-8"))
            self.assertTrue(manifiesto["cancelado"])

    def test_modelo_compartido_adopta_marca_y_persiste(self):
        modelo = ModeloDatosAcademicos(EJEMPLO)
        datos = generar_escenario_configurable(configuracion_pequena(nombre="Compartido"))
        modelo.adoptar(datos, modificado=True)
        self.assertTrue(modelo.modificado)
        self.assertEqual(modelo.nombre_escenario, "Compartido")
        with tempfile.TemporaryDirectory() as temporal:
            modelo.guardar(Path(temporal) / "compartido.json")
            self.assertFalse(modelo.modificado)
            self.assertEqual(modelo.validar().sesiones[0].id, "C0001-S1")

    def test_laboratorio_ejecuta_escenarios_sin_mezclar_resultados(self):
        manual = crear_escenario_manual("Manual")
        generado = generar_escenario_configurable(
            configuracion_pequena(nombre="Generado", sesiones_por_asignacion=1)
        )
        ga = Configuracion(poblacion=4, generaciones=1, elitismo=1, torneo=2, semilla=9)
        config = ConfiguracionExperimento(
            nombre="Lote científico", repeticiones=1, metodos=("constructivo",),
            genetico=ga, hibrido=ga, semilla_inicial=9, repeticion_evolucion=0,
        )
        lote = ejecutar_lote_escenarios(config, (("Manual", manual), ("Generado", generado)))
        self.assertFalse(lote.cancelado)
        self.assertEqual(lote.nombres, ("Manual", "Generado"))
        self.assertEqual(len(lote.resultados), 2)
        self.assertNotEqual(lote.resultados[0].huella_escenario, lote.resultados[1].huella_escenario)
        self.assertTrue(all(len(resultado.ejecuciones) == 1 for resultado in lote.resultados))
        with tempfile.TemporaryDirectory() as temporal:
            carpetas = [exportar_experimento(r, temporal) for r in lote.resultados]
            self.assertEqual(len(carpetas), 2)
            self.assertTrue(all((carpeta / "escenario.json").exists() for carpeta in carpetas))

    def test_escenario_generado_funciona_en_optimizacion_y_evolucion(self):
        datos = generar_escenario_configurable(
            configuracion_pequena(sesiones_por_asignacion=1, nombre="Evolutivo")
        )
        problema = problema_desde_datos(deepcopy(datos))
        instantaneas = []
        resultado = ejecutar(
            problema,
            Configuracion(poblacion=8, generaciones=2, elitismo=1, torneo=2, semilla=17),
            callback_instantanea=instantaneas.append,
        )
        problema.validar_cromosoma(resultado.cromosoma)
        self.assertGreaterEqual(len(instantaneas), 2)
        self.assertTrue(all(len(i.mejor_global) == len(problema.sesiones) for i in instantaneas))


if __name__ == "__main__":
    unittest.main()
