# Diagnóstico de factibilidad: cuello de botella de laboratorios

Fecha de la medición: 23 de noviembre de 2026. Escenario analizado:
`datos/configuracion_academica.json`, SHA-256
`90466177940bfd3928f46fe2bfa33c5d39e197f84bb15998740d054a3e32fedb`.

## Conclusión comprobada

El escenario es estructuralmente válido y sí es factible respecto al evaluador
oficial. La prueba constructiva es independiente de la nota de metadatos: el
modo híbrido encontró horarios con cero violaciones duras para las semillas 40,
41 y 42 dentro de las 120 evaluaciones de la población inicial.

El resultado clásico observado con semilla 42 —5 violaciones duras, penalización
blanda 2278 y fitness -1778— significa **no se encontró solución dentro del
presupuesto**. No demuestra imposibilidad. Las cotas necesarias implementadas no
detectan una contradicción de capacidad y ninguna de las 98 sesiones tiene un
dominio estático vacío.

## Inspección del escenario y de la interpretación

- 7 grupos, 20 docentes, 49 clases expandidas a 98 sesiones y 5 salones.
- 5 días, 11 bloques por día y 2 franjas institucionales no lectivas.
- 126 bloques de demanda total; 3 aulas y 2 laboratorios.
- La validación detallada produjo 0 errores y 0 advertencias.
- Los dominios estáticos incluyen tipo/capacidad del salón, duración, disponibilidad
  de docente y grupo, franjas no lectivas y todos los periodos permitidos. El
  dominio más estrecho contiene 4 asignaciones; ninguno contiene 0.
- Se revisaron cotas necesarias por grupo, docente y subconjuntos compatibles de
  salones. Ninguna demanda supera su capacidad superior. Estas cotas sólo pueden
  demostrar algunos casos imposibles; su holgura no prueba factibilidad.

Importador, editor, consola y evaluador terminan construyendo el mismo `Problema`
mediante `problema_desde_datos`; no se observó una traducción distinta de las
restricciones. Sí hay una debilidad de procedencia: la nota libre del JSON afirma
que se construyó un testigo interno, pero el archivo no contiene el campo
estructurado `factibilidad_testigo_validada` ni el identificador del generador
actual. Esa nota no se usa como prueba. La solución híbrida validada por la función
fitness es la evidencia efectiva de factibilidad.

## Reproducción del resultado clásico y conflictos finales

Configuración: población 120, 600 generaciones, semilla 42. Dos ejecuciones
produjeron el mismo cromosoma y la misma evaluación final; los tiempos observados
fueron 82.594 s y 85.374 s. Se realizaron 193856 evaluaciones completas. La última
mejora dura ocurrió en la generación 403 y la última mejora global en la 439.

Desglose duro final: 2 colisiones de salón, 1 colisión de grupo, 1 bloque de
indisponibilidad docente y 1 bloque fuera del periodo permitido. Ocho sesiones
están implicadas en esas cinco violaciones:

| Sesión | Asignación final | Razón | Alternativa individual comprobada |
|---|---|---|---|
| `C02-06-S1` | Martes 09:00, LAB02 | Colisión con `C03-04-S1` | Miércoles 07:00, LAB02 reduce duras a 4 |
| `C03-02-S1` | Jueves 14:00, LAB02 | Fuera del periodo permitido | Ninguna reubicación individual mejora; requiere coordinación |
| `C03-04-S1` | Martes 09:00, LAB02 | Colisión con `C02-06-S1` | Jueves 11:00, LAB01 reduce duras a 4 |
| `C03-06-S2` | Viernes 14:00, LAB02 | Colisión con `C06-03-S2` | Viernes 17:00, LAB01 reduce duras a 4 |
| `C05-01-S1` | Viernes 10:00, A03 | Colisión de grupo con `C05-06-S1` | Lunes 11:00, A02 reduce duras a 4 |
| `C05-06-S1` | Viernes 10:00, LAB01 | Colisión de grupo con `C05-01-S1` | Martes 09:00, LAB01 reduce duras a 4 |
| `C06-03-S2` | Viernes 14:00, LAB02 | Colisión con `C03-06-S2` | Ninguna reubicación individual mejora; requiere coordinación |
| `C07-03-S1` | Miércoles 09:00, LAB02 | Docente no disponible | Ninguna reubicación individual mejora; requiere coordinación |

Las alternativas de la tabla se evaluaron sustituyendo el gen y ejecutando la
función completa; no son sugerencias obtenidas de un modelo simplificado.

## Causa del estancamiento

La mutación dirigida histórica seleccionaba una sesión conflictiva, pero luego
muestreaba una posición sin considerar la ocupación actual de docente, grupo o
salón. La reparación histórica probaba sólo tres reemplazos aleatorios para hasta
tres sesiones, actuaba únicamente sobre descendientes y no podía efectuar un
movimiento coordinado. La cruza uniforme también puede romper bloques parciales
buenos. El valor de diversidad cercano a 1 sólo indica cromosomas completos
distintos: no descarta que los genes críticos estén congelados.

La mejora híbrida conserva el clásico como referencia y añade:

- dominios estáticos precalculados;
- mutación dirigida que prioriza la menor colisión directa con la ocupación actual;
- reparación lexicográfica con movimientos de un gen y una cadena limitada que
  libera un único bloqueador;
- pulido periódico del élite y reinicio parcial del 12 % ante estancamiento, sin
  reemplazar élites;
- aceptación exclusivamente mediante la evaluación oficial: primero menos duras
  y sólo después menor penalización blanda.

## Comparación experimental antes/después

Protocolo: modo híbrido sin inicialización heurística ni búsqueda local, mutación
adaptativa activa, población 120, máximo 600 generaciones y exactamente 30000
evaluaciones por corrida. Sólo cambian la reparación avanzada y el reinicio por
estancamiento. Los datos completos están en
`resultados/comparacion_factibilidad.json`.

| Semilla | Antes: duras / blanda / fitness | Después: duras / blanda / fitness |
|---:|---:|---:|
| 40 | 20 / 2834 / -3834 | 8 / 2664 / -2464 |
| 41 | 17 / 2746 / -3446 | 2 / 2870 / -2070 |
| 42 | 21 / 2576 / -3676 | 6 / 3030 / -2630 |

La media de violaciones duras bajó de 19.333 a 5.333 y la mediana de 20 a 6;
ninguna de estas seis corridas fue factible. Los tiempos medios observados fueron
12.813 s y 16.800 s. No se concluye una mejora de calidad blanda porque ninguna
corrida alcanzó primero la factibilidad y el criterio blando es subordinado.

Con la inicialización constructiva habitual del híbrido, las semillas 40, 41 y
42 sí produjeron una solución factible en generación 0 con un presupuesto de sólo
120 evaluaciones. Sus penalizaciones blandas fueron 2786, 2726 y 2094. Esto no
demuestra optimalidad, pero sí demuestra factibilidad para el modelo evaluado.

Reproducir la comparación controlada:

```powershell
python -m horarios_ga.experimento_factibilidad `
  --datos datos/configuracion_academica.json `
  --salida resultados/comparacion_factibilidad.json `
  --semillas 40 41 42 --poblacion 120 --generaciones 600 --presupuesto 30000
```

## Verificador exacto opcional

`horarios_ga.verificador_cp_sat` construye una variable booleana por candidato
estáticamente válido y modela exactamente una asignación por sesión, colisiones de
docente/grupo/salón, disponibilidad, franjas, periodos, duración, tipo/capacidad de
salón y máximos consecutivos. Una solución de CP-SAT se vuelve a comprobar con
`fitness.evaluar`; si hay discrepancia, el resultado es inconcluso.

Los estados expuestos son:

- `solucion_factible_encontrada`: solución validada por el evaluador oficial;
- `no_se_encontro_solucion_en_el_presupuesto`: el algoritmo terminó con conflictos;
- `imposibilidad_demostrada`: dominio vacío, cota necesaria violada o CP-SAT
  `INFEASIBLE` sobre el modelo completo;
- `verificacion_inconclusa`: dependencia ausente, límite agotado, modelo inválido
  o cualquier discrepancia con el evaluador.

En el entorno de esta medición, Python 3.15.0, `pip` no encontró una distribución
compatible de OR-Tools; por ello la verificación CP-SAT local quedó inconclusa y no
se presenta como evidencia. En un entorno compatible se instala de forma opcional
con `python -m pip install -r requirements-optional.txt`.

## Limitaciones pendientes

- Las cotas rápidas no son un demostrador completo; un estado sin contradicciones
  sólo significa que esas pruebas necesarias no bastaron.
- El verificador CP-SAT es de factibilidad dura, no optimiza las penalizaciones
  blandas ni prueba optimalidad académica.
- La reparación coordinada está deliberadamente limitada a una cadena corta para
  respetar el presupuesto; pueden existir mesetas que necesiten movimientos mayores.
- Tres semillas muestran una mejora descriptiva, no una prueba estadística general.
- La nota de procedencia del JSON debería migrarse en el futuro a campos
  estructurados verificables, sin usar metadatos narrativos como certificado.
