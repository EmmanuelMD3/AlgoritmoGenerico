# Optimización de horarios universitarios mediante algoritmos genéticos

**Universidad Autónoma del Estado de México · Centro Universitario UAEMex Tianguistenco**  
**Materia:** Cómputo Evolutivo  
**Autor:** Emmanuel Martínez Díaz

Aplicación de escritorio para configurar, ejecutar y analizar algoritmos genéticos de horarios universitarios. La **Fase 2** separa factibilidad y calidad académica; la **Fase 3** incorpora el dashboard; la **Fase 4** añade experimentación reproducible; la **Fase 5** permite observar la evolución real; la **Fase 6** incorpora un algoritmo híbrido opcional; la **Fase 7** añadió generación reproducible de escenarios; la **Fase 7.1** concentra toda la edición cotidiana en una única configuración académica canónica; la **Fase 7.2** incorpora navegación lateral y disponibilidad binaria; y la **Fase 7.3** permite importar de forma validada y transaccional escenarios JSON externos. Se conservan la consola, la interfaz en español, el generador sintético de soporte y todas las exportaciones anteriores.

Los datos de `datos/ejemplo.json` son ficticios y sólo sirven para demostración; los resultados son cálculos reales del algoritmo sobre ese conjunto.

## Requisitos e instalación

- Python 3.10 o superior.
- Tkinter/ttk (incluido normalmente con Python para Windows).
- Matplotlib para las gráficas integradas y exportadas.

Desde PowerShell, dentro de la carpeta del proyecto:

```powershell
python -m pip install -r requirements.txt
```

Si `python` no está disponible, se puede sustituir por `py`.

## Aplicación gráfica

Iniciar con:

```powershell
python app.py
```

`python main.py` usa también `datos/configuracion_academica.json` cuando existe; `--datos` permite indicar explícitamente otro JSON para ejecuciones de consola reproducibles. Si todavía no se ha creado el archivo canónico, la consola conserva el respaldo compatible `datos/ejemplo.json`.

La ventana es redimensionable y contiene siete secciones en una barra lateral única:

1. **Optimización:** configuración, métricas, progreso y gráficas de fitness/conflictos.
2. **Datos académicos:** clases, docentes, grupos, salones, días y bloques.
3. **Horarios generados:** consulta por grupo, docente o salón.
4. **Historial evolutivo:** tabla por generación y gráfica completa.
5. **Información del algoritmo:** explicación educativa de la representación y operadores.
6. **Experimentación:** comparaciones reproducibles, estadísticas, gráficas y reportes científicos.
7. **Evolución en vivo:** calendario por generación, cambios, reproducción, comparación y animaciones.

### Configurar y ejecutar

En **Optimización** se pueden cambiar población, generaciones, probabilidades de cruza y mutación, elitismo, torneo y semilla. La Fase 2 añade:

- probabilidad de mutación dirigida a sesiones con violaciones duras;
- probabilidad de reparación local de descendientes;
- fracción de inmigrantes aleatorios para preservar diversidad;
- generaciones sin mejora para parada anticipada (`0` la desactiva);
- objetivo máximo de penalización blanda.

La parada anticipada sólo ocurre cuando el mejor horario es factible, alcanza el objetivo blando configurado y después no mejora durante el número indicado de generaciones. Cero violaciones duras, por sí solo, no detiene la ejecución ni significa optimalidad.

Pulsa **Ejecutar algoritmo**. El cálculo se hace en un hilo trabajador y Tk recibe novedades mediante una cola, por lo que la ventana no se congela. **Detener ejecución** activa una cancelación cooperativa entre generaciones y conserva el mejor resultado parcial disponible.

La comparación genética es lexicográfica: minimiza primero violaciones duras y después la penalización blanda. El panel **Desglose de evaluación** presenta cantidad, peso y penalización de cada criterio, junto con las razones concretas de no factibilidad.

## Optimización híbrida (Fase 6)

El selector **Modo de optimización** mantiene `clasico` como valor predeterminado. Aunque se hayan guardado valores en los controles avanzados, no se ejecutan componentes híbridos mientras el modo sea clásico. Esto permite reproducir el flujo anterior y compararlo de forma independiente.

En modo `hibrido` se pueden activar por separado:

- **Inicialización heurística mixta:** 0–50 % de la población se construye ordenando primero las sesiones más restringidas y minimizando indisponibilidades y colisiones parciales. El resto se genera por la ruta aleatoria habitual. La heurística sólo consulta el problema cargado: no accede a una solución testigo ni garantiza factibilidad.
- **Búsqueda local:** vecindarios de reasignación, intercambio o ambos; selección de los mejores individuos, una muestra aleatoria o activación durante estancamiento; primera o mejor mejora; frecuencia, proporción, evaluaciones y mejoras máximas configurables. Un movimiento sólo se acepta si mejora `(-D, -B, Fitness)`.
- **Mutación adaptativa:** mantiene una tasa dentro de límites mínimo/máximo. La incrementa al detectar estancamiento o diversidad baja y la aproxima de nuevo a la tasa base cuando desaparecen esas señales. El historial conserva la tasa realmente usada en cada generación.
- **Presupuesto máximo:** `0` significa sin límite. Otro valor detiene cooperativamente la corrida antes de superar el número indicado de evaluaciones completas. Debe ser al menos igual al tamaño de población.

El resumen y `resumen.json` separan evaluaciones y tiempos de inicialización, evolución y búsqueda local. `evolucion.csv` añade tasa de mutación, evaluaciones acumuladas, aplicaciones/mejoras locales y marcas de mejora global/estancamiento. Las cifras de tiempo son observaciones del equipo, no parte de la prioridad del optimizador.

La búsqueda local es memética: puede mejorar una solución, pero no demuestra optimalidad. Del mismo modo, agotar generaciones o presupuesto sin hallar factibilidad no demuestra que el escenario sea matemáticamente imposible.

### Cargar y editar datos académicos

`datos/configuracion_academica.json` es la única configuración académica persistente y editable de la aplicación. Al iniciar, se carga automáticamente si existe. En una instalación nueva, `datos/ejemplo.json` se usa sólo como plantilla en memoria; el primer **Guardar todos los cambios** crea el archivo canónico. Una configuración personalizada existente nunca se sustituye silenciosamente por el ejemplo.

La sección **Datos académicos** se organiza mediante navegación secundaria compacta en General, Docentes, Grupos, Materias y sesiones, Salones, Disponibilidad, y Resumen y validación. Permite:

- crear, editar, duplicar y eliminar clases, docentes, grupos y salones con formularios maestro–detalle;
- elegir días lectivos y generar los bloques desde inicio, fin y duración mediante controles cerrados;
- previsualizar cuántos bloques y referencias semanales se verán afectados antes de aplicar un cambio temporal;
- editar la disponibilidad binaria de docentes y grupos con un clic por celda; la entidad se carga automáticamente y se muestra como `Nombre (ID)`;
- alternar días completos y concentrar “todo disponible/no disponible” en un menú de acciones;
- configurar las franjas institucionales no lectivas desde General y los periodos permitidos desde Materias y sesiones;
- validar errores y advertencias, guardar, descartar o ejecutar desde una barra de acciones persistente.

#### Importar un escenario JSON (Fase 7.3)

El botón **Importar escenario JSON** está en la cabecera de Datos académicos. Abre el selector nativo de Windows y acepta un archivo `.json` desde cualquier carpeta accesible. La selección pasa por los mismos cargadores y validadores del motor; no ejecuta código, no deserializa objetos y rechaza archivos mayores de 5 MiB. Antes de escribir muestra una vista previa con archivo, nombre, docentes, grupos, materias, sesiones, salones, días, rango horario, duración de bloque, errores y advertencias. **Importar y utilizar** sólo se habilita para una estructura válida. Las advertencias describen riesgos aproximados y nunca se presentan como demostración de imposibilidad.

Si hay cambios locales pendientes se puede **guardar y continuar**, **descartar al completar la importación** o **cancelar**. El descarte no se hace por adelantado: si falla la lectura, validación o escritura, la configuración en memoria y el archivo anterior permanecen intactos. Un cambio externo del archivo canónico también exige confirmación expresa antes de reintentar el reemplazo.

La fuente seleccionada nunca se modifica. Tras confirmar, se valida de nuevo el contenido y se escribe mediante un temporal en el mismo directorio y reemplazo atómico exclusivamente sobre `datos/configuracion_academica.json`; no se crean copias activas, nombres numerados ni selectores alternos. Los JSON anteriores sin metadatos nuevos conservan los valores predeterminados documentados, incluida una duración de bloque de 60 minutos. No se inventan docentes, grupos, salones ni referencias faltantes.

Al terminar, Datos académicos, Optimización, Experimentación y Evolución en vivo reciben inmediatamente la nueva instantánea central. Las corridas que empiecen después usan esos datos; un resultado ya calculado conserva su nombre, huella y escenario histórico, y no se recalcula ni se sobrescribe. Los estados visibles del flujo son Seleccionando, Validando, Listo para importar, Importando, Completado, Cancelado y Error.

**Guardar disponibilidad** actualiza únicamente `no_disponible` del docente o grupo seleccionado. Parte de la última versión persistida y por ello no guarda accidentalmente borradores de otras entidades o secciones; esos borradores permanecen en memoria. **Guardar todos los cambios** persiste la instantánea académica completa. Ambos validan antes de escribir, crean un temporal en el mismo directorio y usan reemplazo atómico sobre el mismo JSON. Una huella SHA-256 detecta modificaciones externas. En el guardado individual se puede cancelar o reintentar sobre la versión externa más reciente: la reconciliación de tres vías preserva datos ajenos y borradores locales, y sólo sustituye la disponibilidad confirmada. No se crean versiones numeradas ni configuraciones activas paralelas.

Al cambiar de docente o grupo con una edición pendiente se ofrecen tres decisiones explícitas: guardar esa disponibilidad, descartar sólo el borrador de esa entidad o cancelar el cambio. La cabecera muestra la entidad, las horas semanales reales —calculadas con la duración de bloque, incluidos bloques de 30 minutos— y el estado Guardado/Cambios pendientes/Guardando/Error.

La disponibilidad dejó de tener el estado visual **Preferido**. Si un JSON anterior contiene `docentes[].preferidos`, la aplicación lo informa, conserva esos mapas sin borrarlos y prepara `restricciones.preferencias_docentes_activas: false` al siguiente guardado. Así el dato histórico sigue disponible, pero no produce una penalización invisible en Optimización ni Experimentación. Un JSON antiguo leído directamente por consola y sin el nuevo interruptor conserva por compatibilidad el comportamiento histórico hasta que se migre explícitamente; los resultados y archivos de experimentos ya existentes nunca se recalculan.

Las referencias no se cambian automáticamente. No se permite eliminar o renombrar un docente/grupo referenciado por clases, ni dejar una clase sin salón de tipo y capacidad suficientes. Las listas separadas por comas ya no forman parte del flujo gráfico: la cuadrícula convierte cada selección al mapa JSON correspondiente.

Estructura principal del JSON:

- `dias`: nombres de días lectivos únicos.
- `horas`: inicios `HH:MM` de bloques consecutivos; los JSON anteriores conservan 60 minutos.
- `metadatos.duracion_bloque_minutos` opcional: 15–180 minutos; el editor ofrece 15, 30, 45, 60, 90 y 120.
- `salones`: `id`, `capacidad`, `tipo` y `nombre` opcional.
- `grupos`: `id`, `alumnos` y, opcionalmente, `no_disponible` y `max_horas_consecutivas`.
- `docentes`: `id`, `nombre`, `no_disponible` y, opcionalmente, `preferidos` y `max_horas_consecutivas`.
- `clases`: `id`, `materia`, `grupo`, `docente`, `sesiones_semana`, `duracion_bloques`, `tipo_salon` y `periodos_permitidos` opcional.
- `restricciones` opcional: `franjas_no_lectivas`, máximos consecutivos globales para grupos/docentes, `umbral_jornada_larga` y `preferencias_docentes_activas`. Este último es `false` en el flujo gráfico 7.2.

Las disponibilidades y periodos usan el formato JSON `{"Lunes": ["07:00", "08:00"]}`. La ausencia de cualquiera de los campos nuevos conserva el comportamiento compatible de los datos anteriores. Un conjunto válido puede ser muy restrictivo; la carga no lo etiqueta como matemáticamente imposible.

Optimización, Experimentación, Evolución en vivo y las demás vistas reciben copias validadas del mismo modelo central. Al comenzar una corrida se captura una instantánea exacta. Editar después la configuración activa no muta esa ejecución ni reinterpreta sus resultados: el nombre y la huella SHA-256 de origen permanecen asociados al historial mostrado.

## Generación sintética de soporte

La Fase 7.1 retira de la aplicación cotidiana la pestaña Constructor, la biblioteca de múltiples JSON y sus selectores de escenarios. El módulo `horarios_ga/constructor_escenarios.py` se conserva como infraestructura interna para pruebas automatizadas, datos sintéticos reproducibles y estudios controlados; no compite con `datos/configuracion_academica.json` como configuración activa.

El generador mantiene perfiles, semillas, sesiones multibloque, estrés y la opción de construir internamente un testigo factible. Ese testigo nunca se incluye en el JSON ni se entrega al optimizador. Las validaciones distinguen errores estructurales de advertencias aproximadas; ninguna advertencia de demanda o falta de ubicación estática se presenta como prueba general de imposibilidad matemática.

### Consultar y exportar

Después de una ejecución, **Horarios generados** presenta días en columnas y bloques en filas. Cada celda incluye materia, docente y salón; los bloques posteriores de una sesión larga indican “continuación”. Las celdas afectadas por colisión o indisponibilidad se resaltan y el estado nunca afirma que el horario es factible si la evaluación contiene conflictos.

Se puede exportar:

- asignaciones a CSV;
- horarios por grupo a HTML;
- la vista seleccionada a PNG;
- historial de generaciones a CSV.

La carpeta predeterminada es `resultados/` y puede abrirse desde la propia aplicación.

## Evolución en vivo

La séptima pestaña permite inspeccionar directamente cómo cambia el mejor horario desde la población inicial. La generación 0 se captura antes de selección, cruza o mutación y conserva también una muestra aleatoria de la población inicial. Cada instantánea es una copia inmutable que contiene:

- mejor cromosoma de la generación y mejor global;
- evaluación lexicográfica y desglose de conflictos;
- fitness, penalización blanda, diversidad y primera generación factible;
- índices estables de sesiones conflictivas;
- tiempo de cálculo, excluyendo pausas y retardos didácticos.

La frecuencia **Capturar cada** permite reducir memoria en escenarios grandes. Siempre se conservan G0 y la última generación realmente ejecutada. El calendario reutiliza la matriz de horarios existente, admite vistas por grupo, docente o salón, representa sesiones multibloque y dispone de desplazamiento horizontal/vertical.

La comunicación en vivo usa una cola segura entre el trabajador y Tk. El consumidor procesa como máximo ocho eventos o 8 ms por ciclo y devuelve el control al bucle de ventanas; G0 se presenta en un primer lote independiente. En modo rápido se conservan todas las capturas configuradas, pero se agrupan únicamente redibujos intermedios cuando el motor supera la frecuencia de la pantalla. En modo didáctico, el trabajador espera cooperativamente la confirmación de que cada captura fue presentada y después aplica el retardo elegido. Esa espera se registra como `tiempo_espera_didactica` y queda excluida del tiempo algorítmico.

Las celdas del calendario se crean una vez por estructura semanal y después sólo cambian texto y estilo. Las líneas de las gráficas también actualizan sus datos y límites sin reconstruir las cuatro figuras en cada generación; las anotaciones completas se regeneran al finalizar. Pausar cálculo, continuar y avanzar un paso son controles del trabajador, independientes de Pausar animación, que sólo afecta la reproducción visual.

### Reproducción y diferencias

Los botones de reproducción visual permiten ir al inicio/final, avanzar o retroceder, reproducir a velocidades de 0.25 a 5 segundos y elegir una generación mediante deslizador o selector. Pausar la animación no pausa el algoritmo.

Entre dos instantáneas se comparan los genes por identificador estable de sesión. Se informa por separado cambio de día, hora y salón, conflictos aparecidos o desaparecidos y variaciones del desglose duro. Las celdas modificadas incluyen el texto **CAMBIO** y los conflictos muestran **⚠ CONFLICTO**, por lo que la información no depende sólo del color. Si el mejor cromosoma no cambió se indica explícitamente.

La vista **Comparación de generaciones** muestra dos calendarios simultáneos, inicialmente G0 frente a la última captura, con diferencias absolutas de sesiones, día, hora, salón y violaciones duras. La gráfica inferior conserva las cuatro series reales y sólo desplaza el marcador al navegar; no recalcula el historial completo.

### Ejecución didáctica

El modo rápido continúa siendo el predeterminado. Al activar **Ejecución didáctica** se puede añadir un retardo, pausar el cálculo en un punto seguro, continuar o liberar exactamente una generación con **Paso**. La sincronización usa una condición en el hilo trabajador; Tkinter nunca se bloquea. El tiempo artificial se mide aparte y no se usa en los experimentos científicos.

### Guardado y animaciones

Los registros se guardan como JSON o `JSON.GZ`, nunca como `pickle`. Al abrirlos se validan versión, escenario, identificadores, dominios de genes y evaluaciones antes de reproducirlos. Las opciones de exportación incluyen:

- PNG del horario mostrado;
- PNG de comparación entre generaciones;
- secuencia PNG con intervalo configurable;
- GIF con intervalo, duración y entidad visualizada configurables.

Para evitar archivos accidentales excesivos, las secuencias y GIF limitan el número de fotogramas y solicitan aumentar el intervalo cuando corresponde. MP4 no se genera porque el proyecto no exige actualmente una dependencia de codificación portable.

Experimentación captura, de forma predeterminada, sólo la repetición genética seleccionada (`1`; `0` desactiva). Esa ejecución puede abrirse en **Evolución en vivo**. No se inventan generaciones para búsqueda aleatoria ni para la heurística constructiva.

Medición de referencia realizada durante la validación de Fase 5, con escenario pequeño, población 40, 50 generaciones y semilla 42: mediana de tres corridas sin captura `0.81594 s` y con 51 instantáneas `0.83731 s`, un sobrecosto observado de `2.62%`. El registro comprimido ocupó 5291 bytes. Son cifras del equipo y carga de esa prueba, no una garantía de rendimiento universal.

## Laboratorio de experimentación científica

La pestaña **Experimentación** permite estudiar el comportamiento del algoritmo sobre el mismo modelo académico y la misma función de evaluación, sin depender de Tkinter para el cálculo. El laboratorio separa métodos, ejecución, estadística, exportación y presentación.

### Configuración académica del estudio

La interfaz ya no ofrece selectores Pequeño, Mediano, Grande, JSON ni Lote JSON. Cada estudio usa una copia exacta de la configuración académica activa, igual que Optimización. Los generadores sintéticos siguen disponibles en el backend para las pruebas y protocolos programáticos, pero no crean una segunda fuente de verdad en la interfaz.

Cada exportación conserva el JSON exacto del escenario y su huella SHA-256. Mismos datos, configuración y semillas producen los mismos resultados algorítmicos; identificadores, fechas y tiempos de pared pueden variar.

### Métodos comparados

1. **Algoritmo genético:** ruta clásica con selección por torneo, cruza uniforme, mutación, elitismo, reparación, inmigrantes y prioridad lexicográfica.
2. **Algoritmo genético híbrido:** misma base evolutiva más los componentes de Fase 6 habilitados.
3. **Búsqueda aleatoria:** genera horarios completos independientes dentro del dominio de cada gen y conserva el mejor evaluado.
4. **Heurística constructiva:** ordena sesiones por número de opciones, prueba ubicaciones progresivamente y realiza barridos locales sin población, cruza ni mutación.

Todos utilizan `horarios_ga.fitness.evaluar`. Una solución con violaciones duras nunca se compara como equivalente a una factible aunque tenga menor penalización blanda.

### Presupuesto y semillas

El presupuesto nominal previo del algoritmo genético es:

```text
población × (generaciones + 1)
```

El laboratorio instrumenta también las evaluaciones de mutación dirigida, reparación, captura evolutiva y búsqueda local. En las comparaciones históricas sin híbrido, las referencias reciben el conteo real del AG clásico. Cuando se compara clásico frente a híbrido, ambos reciben un máximo común explícito y las referencias usan ese mismo máximo; el CSV conserva tanto el límite como el consumo real. Ninguna evaluación algorítmica se oculta. El tiempo real se registra como métrica secundaria y no como único criterio de comparación.

La repetición `r` utiliza `semilla_inicial + r - 1` en todos los métodos. Cada método crea su propio `random.Random`, evitando depender del estado aleatorio global.

### Métricas y estadística

Por ejecución se registran método, escenario, semilla, configuración, presupuesto, evaluaciones realizadas, tiempo, motivo de parada, cromosoma final, factibilidad, violaciones duras, penalización blanda, fitness, desglose y momento de primera factibilidad. Para el AG también se conserva el historial y las generaciones ejecutadas.

El resumen informa número de muestras válidas, media, mediana, desviación estándar, mínimo, máximo y percentiles 25/75. La calidad blanda y el fitness comparativo se calculan exclusivamente entre soluciones factibles. Si no existe ninguna se muestra **Sin soluciones factibles**.

Las gráficas se interpretan así:

- **Tasa de factibilidad:** proporción de corridas válidas con cero violaciones duras.
- **Penalización blanda:** cajas únicamente de soluciones factibles.
- **Tiempo:** distribución de segundos observados; depende del entorno.
- **Convergencia:** mediana y rango intercuartílico por generación realmente observada; una vista adicional usa evaluaciones acumuladas como eje X y no prolonga corridas terminadas.
- **Operadores híbridos:** tasa de mutación, mejoras locales y evaluaciones/tiempos apilados por fase.
- **Parámetros:** tasa de factibilidad y mediana blanda factible al cambiar un parámetro por vez.

Las conclusiones son descriptivas y no constituyen por sí solas una prueba de superioridad estadística.

### Análisis de parámetros

El modo **Análisis de parámetros del algoritmo genético** genera una configuración base y variantes de población, mutación, cruza o generaciones, cambiando sólo un parámetro a la vez. Antes de ejecutar muestra configuraciones, repeticiones, corridas y evaluaciones nominales. Los estudios de más de 60 corridas o cinco millones de evaluaciones nominales requieren confirmación.

El modo **ablación** crea cinco variantes controladas: A clásica; B sólo con inicialización; C sólo con búsqueda local; D sólo con mutación adaptativa; y E híbrida completa. Se deben usar las mismas semillas, escenario y presupuesto. Una diferencia observada en pocas semillas es descriptiva, no prueba causal ni superioridad general.

### Exportación

Cada ejecución terminada o cancelada se exporta automáticamente sin sobrescribir carpetas anteriores:

```text
experimentos/experimento_001/
├── configuracion.json
├── escenario.json
├── ejecuciones.csv
├── resumen_estadistico.csv
├── resumen.json
├── factibilidad.png
├── penalizaciones.png
├── tiempos.png
├── convergencia.png
├── convergencia_evaluaciones.png
├── operadores.png
└── reporte.html
```

El análisis de parámetros añade `parametros.png`. El reporte HTML incluye metodología, tablas, gráficas, interpretación descriptiva y limitaciones. Una cancelación queda marcada como parcial y nunca como completada.

## Ejecución por consola

La interfaz no sustituye ni rompe el flujo original:

```powershell
python main.py
```

Ejemplo con parámetros:

```powershell
python main.py --datos datos/ejemplo.json --salida resultados `
  --poblacion 150 --generaciones 300 --mutacion 0.08 --cruza 0.85 `
  --elitismo 4 --torneo 4 --semilla 42 --mutacion-dirigida 0.35 `
  --reparacion 0.25 --inmigrantes 0.03 --parada-sin-mejora 40 `
  --objetivo-blandas 80
```

Ejemplo híbrido:

```powershell
python main.py --modo hibrido --poblacion 40 --generaciones 40 `
  --inicializacion-heuristica --fraccion-heuristica 0.30 `
  --busqueda-local --frecuencia-local 5 --evaluaciones-locales 12 `
  --mutacion-adaptativa --presupuesto-evaluaciones 5000
```

La consola imprime el fitness inicial/final, el desglose de conflictos y los archivos generados. `resultados/` contiene `horario_sesiones.csv`, `horarios_por_grupo.html`, `evolucion.csv`, `evolucion.png` y `resumen.json`.

## Algoritmo y restricciones implementadas

- **Individuo:** un horario completo.
- **Gen:** `(día, bloque inicial, salón)` de una sesión fija.
- **Población:** genes aleatorios dentro de rangos y con salón compatible.
- **Selección:** torneo por prioridad lexicográfica.
- **Cruza:** uniforme, sin cambiar la identidad de la sesión.
- **Mutación:** día, hora, salón o gen completo; puede dirigirse a sesiones conflictivas.
- **Reparación:** muestrea reasignaciones locales y sólo acepta mejoras lexicográficas.
- **Elitismo:** preserva los mejores individuos.
- **Diversidad:** una fracción configurable de inmigrantes reemplaza descendientes no elitistas; el historial registra la proporción de cromosomas únicos.

### Modelo matemático de evaluación

Sea `D(H)` el número total de violaciones duras y `B(H)` la penalización blanda ponderada. La comparación es:

```text
Prioridad(H) = (−D(H), −B(H), Fitness(H))
```

El fitness legible se conserva como:

```text
Fitness(H) = 1000 − penalización_dura(H) − penalización_blanda(H)
```

La prioridad no permite que una mejora blanda compense una violación dura. Entre horarios con igual número de violaciones duras gana el de menor penalización blanda.

Restricciones críticas reales:

- un docente no puede impartir dos sesiones en el mismo bloque;
- un salón no puede recibir dos sesiones en el mismo bloque;
- un grupo no puede cursar dos sesiones en el mismo bloque;
- un docente no debe impartir en horas marcadas como no disponibles;
- un grupo no debe recibir clase en horas no disponibles;
- ninguna sesión puede ocupar una franja institucional no lectiva;
- todos los bloques de una sesión deben pertenecer a sus periodos permitidos, si se configuraron;
- se respetan máximos obligatorios de horas consecutivas por grupo y docente, globales o individuales;
- cada sesión usa bloques consecutivos y un salón de tipo/capacidad válidos.

Penalizaciones blandas y pesos predeterminados:

| Criterio | Unidad | Peso |
|---|---:|---:|
| Huecos internos de grupos | bloque | 20 |
| Exceso sobre el umbral de jornada | bloque | 8 |
| Sesión aislada en el último bloque | ocurrencia | 12 |
| Diferencia entre el día más y menos cargado | bloque | 6 |
| Salones adicionales usados por una misma clase | cambio | 10 |

El peso histórico de **bloques fuera de preferencia docente** es 4 y sólo se aplica cuando un documento establece `preferencias_docentes_activas: true` o cuando un JSON anterior se usa directamente fuera del flujo de migración. La configuración activa de la interfaz 7.2 lo establece en `false`, por lo que su desglose es cero y no existe una penalización oculta.

Cada tipo de violación dura usa peso visual 100 en el fitness, pero la factibilidad depende del conteo duro, no de ese peso. Un horario es **factible respecto al modelo actual** cuando `D(H) = 0`; puede seguir teniendo `B(H) > 0` y no ser óptimo.

## Dashboard de optimización

La pestaña **Optimización** conserva la ejecución asíncrona de las fases anteriores y organiza la información en dos zonas:

- un panel lateral plegable con parámetros generales, operadores genéticos, opciones avanzadas y parada anticipada;
- un dashboard con estado de ejecución, progreso, ocho indicadores, gráficas y detalle del resultado.

Los ocho indicadores muestran estado del horario, violaciones duras, penalización blanda ponderada, fitness del mejor individuo, diversidad poblacional, generaciones ejecutadas, tiempo y motivo de finalización. Los valores proceden del historial y del resultado real; mientras todavía no existen datos se muestran estados vacíos explícitos.

Se pueden alternar cuatro vistas del historial:

- **Factibilidad:** violaciones duras y primera generación factible observada.
- **Calidad:** penalización blanda y mejor valor factible observado.
- **Fitness:** mejor individuo y promedio poblacional, con la prioridad lexicográfica indicada en la propia gráfica.
- **Diversidad:** proporción de cromosomas únicos de la población.

La vista activa se puede exportar a PNG. El redibujado en pantalla se limita durante ejecuciones largas para mantener fluida la interfaz, pero el historial completo no se descarta y la exportación utiliza todos los registros disponibles.

El panel inferior separa el desglose de restricciones duras y blandas, la comparación inicial/final y el resumen de factibilidad. La comparación presenta diferencias absolutas —no porcentajes potencialmente engañosos— y una ejecución con cero conflictos críticos no se etiqueta automáticamente como óptima.

## Pruebas

Ejecutar:

```powershell
python -m unittest discover -s tests -v
```

Las 150 pruebas cubren el motor original, compatibilidad JSON, reproducibilidad, operadores, exportaciones, parámetros de interfaz, callback, cancelación cooperativa, sesiones multibloque, disponibilidades limitadas, dashboard, experimentación, escenarios y estadísticas. La Fase 5 añade generación 0, copias inmutables, frecuencia de captura, diferencias y exportaciones PNG/GIF. La corrección de evolución en vivo añade callbacks desde el trabajador, orden G0→Gn en clásico e híbrido, consumo acotado de eventos, confirmación de presentación didáctica, paso exacto, separación de tiempos y reutilización de celdas. La Fase 6 añade compatibilidad estricta del modo clásico, población mixta, vecindarios locales, cotas adaptativas, presupuesto global, métricas por fase, comparación clásico/híbrido y ablaciones A–E. La Fase 7 añade bloques variables, generación reproducible, perfiles, testigo oculto, validación con errores/advertencias, gestión segura y lotes cancelables. La Fase 7.1 añade carga canónica, escritura atómica, recuperación ante fallos de reemplazo, detección de cambios externos, estado sucio y descarte, persistencia tras reinicio, conversión de cuadrícula, periodos permitidos, poda temporal, instantáneas históricas, selección canónica en consola y verificación de siete secciones. La Fase 7.2 agrega estado binario, cálculo de horas con bloques variables, carga automática, cambio de entidad con borradores, guardado aislado de docentes/grupos, fusión segura ante conflictos externos, migración de preferencias sin borrado, persistencia al reiniciar e integración del mismo contrato con optimización y experimentación. La Fase 7.3 añade selección y cancelación, vista previa, compatibilidad heredada, referencias inválidas, límites de tamaño, fallos de lectura/escritura, conflictos externos, atomicidad, persistencia al reinicio, propagación a las vistas y ejecución clásica/híbrida sobre el escenario importado.

## Organización

```text
HorariosGeneticos/
├── app.py                         # entrada gráfica
├── main.py                        # entrada de consola
├── datos/
│   ├── ejemplo.json               # plantilla y compatibilidad
│   └── configuracion_academica.json # configuración activa creada por la UI
├── horarios_ga/
│   ├── modelo.py
│   ├── datos.py
│   ├── fitness.py
│   ├── genetico.py
│   ├── escenarios.py
│   ├── constructor_escenarios.py
│   ├── importacion.py
│   ├── baselines.py
│   ├── experimentos.py
│   ├── estadisticas.py
│   ├── evolucion.py
│   ├── exportaciones_evolucion.py
│   └── reportes.py
├── interfaz/
│   ├── aplicacion.py
│   ├── componentes.py
│   ├── estilos.py
│   ├── optimizacion.py
│   ├── experimentacion.py
│   ├── evolucion.py
│   ├── datos_academicos.py
│   ├── horarios.py
│   └── historial.py
└── tests/
```

El motor no depende de Tkinter. `ejecutar()` mantiene su firma compatible y añade únicamente callbacks opcionales de progreso, cancelación, conteo, instantáneas y espera didáctica.

## Limitaciones conocidas

No se modelan todavía descansos dependientes de carrera, máximo de carga diaria independiente de la jornada, distribución obligatoria de sesiones de una materia en días distintos, precedencias entre materias, aulas compartidas externas ni prioridades por semestre. El balance semanal usa el rango entre el día más y menos cargado; es una heurística, no una política institucional universal.

No existe un demostrador general de factibilidad. Si el algoritmo termina con violaciones, la aplicación informa cuáles persisten, pero no concluye que el problema sea matemáticamente imposible. La reparación es local y la búsqueda genética no garantiza el óptimo global.

Los pesos son iniciales y experimentales. Una sola ejecución no constituye evidencia estadística de desempeño: para un estudio conviene repetir con varias semillas y comparar fitness, conflictos, tiempo y variabilidad.

Los escenarios sintéticos son modelos académicos controlados, no réplicas certificadas de la carga real de la institución. El testigo demuestra que el escenario normal generado tiene al menos una solución válida, pero no prueba unicidad ni optimalidad. Los experimentos no aplican todavía pruebas inferenciales o correcciones por comparaciones múltiples; los resúmenes y conclusiones son descriptivos. Los métodos realizan operaciones internas diferentes aun cuando se iguala el número de evaluaciones completas, por lo que también se reporta tiempo y se documenta el trabajo adicional del AG.

El editor importa escenarios que ya cumplen el esquema JSON documentado; todavía no transforma planes de estudio institucionales, hojas de cálculo ni bases de datos externas. La disponibilidad de salones no se modela como calendario individual: se modelan tipo, capacidad y colisiones de ocupación. La cuadrícula permite clic individual, día completo y acciones globales, pero no selección rectangular por arrastre. Los perfiles del generador sintético y las advertencias de demanda son heurísticos. Un escenario de estrés puede ser inviable, pero el sistema no lo afirma sin una comprobación formal.

La captura completa consume memoria proporcional a `sesiones × instantáneas`; para escenarios grandes debe aumentarse el intervalo. El visor conserva el mejor individuo por captura, no poblaciones completas. El GIF rasteriza cada calendario y puede ser costoso, por lo que se limita a 200 fotogramas. No se exporta MP4. Los colores de materias son ayudas visuales y no codifican calidad o causalidad; un cambio del mejor individuo no se atribuye automáticamente a mutación.
