# Guía para facilitadores — *"Cómo mentir con mapas de calor"*

> Idioma: **Español** · English: [`FACILITATOR-GUIDE.md`](FACILITATOR-GUIDE.md)

Un taller práctico de 90 minutos para periodistas, voluntarios de datos cívicos,
personas defensoras de la comunidad y estudiantes sobre por qué un mapa de calor
de conteo crudo engaña y cómo la estadística espacial honesta — normalización por
exposición, intervalos de confianza y puntos calientes con control de la tasa de
falsos descubrimientos — lo corrige. Está construido sobre los **datos sintéticos
de Davis** de `nearmiss`, una cuadrícula de calles con respuesta conocida, con un
punto caliente plantado y un *señuelo concurrido* deliberado, para que quienes
participan practiquen el razonamiento sin ningún dato real ni sensible.

Este módulo es la expresión en "modo enseñanza" del modelo de amenazas del
proyecto **T4 — un consumidor ingenuo que malinterpreta un mapa de conteo crudo
como peligro** ([`docs/THREAT-MODEL.md`](../THREAT-MODEL.md)). Todo el arco del
taller es la mitigación central de T4: *hacer que la lectura honesta sea la
lectura fácil.*

---

## Objetivos de aprendizaje

Al finalizar la sesión, quienes participan podrán:

1. **Explicar la mentira.** Decir con precisión por qué un mapa de calor de
   conteo crudo (o de densidad de núcleo sin normalizar) apunta al lugar más
   *concurrido* y lo etiqueta erróneamente como el más *peligroso*.
2. **Normalizar por exposición.** Calcular una tasa como reportes por unidad de
   exposición y explicar qué es el denominador y por qué cambia la clasificación.
3. **Leer la incertidumbre.** Interpretar un intervalo de confianza del 95% sobre
   una tasa y usar los intervalos que se solapan para resistir la sobrelectura de
   diferencias pequeñas.
4. **Distinguir "caliente por peligroso" de "caliente por concurrido".**
   Describir qué prueba el estadístico local Getis-Ord Gi\* y por qué se ejecuta
   sobre la tasa, no sobre el conteo.
5. **Respetar las comparaciones múltiples.** Explicar por qué se aplica una
   corrección de la tasa de falsos descubrimientos (FDR) de Benjamini-Hochberg y
   contra qué protege.
6. **Detectar el problema de la unidad de área modificable (MAUP).** Mostrar cómo
   volver a trazar los límites de los segmentos puede fabricar o disolver un punto
   caliente "significativo", y nombrar las defensas (pre-registro, reporte de
   sensibilidad, conservar todo el conjunto de comparación).
7. **Aplicar las mitigaciones de T4** a un mapa o gráfico real que encuentren en
   la vida diaria: etiquetar el volumen como volumen; publicar tasas, intervalos y
   significancia; nombrar el sesgo.

---

## Audiencia y requisitos previos

- **Audiencia:** talleres de periodismo / datos cívicos / incidencia; no se asume
  formación estadística. Sirve desde estudiantes de grado hasta equipos de datos
  de redacciones.
- **Familiaridad con:** leer una tabla; la idea de una tasa (p. ej. "por 1,000").
  Algo de Python ayuda para el cuaderno de ejercicios pero no es obligatorio — la
  persona facilitadora puede conducir el cuaderno mientras el grupo razona en voz
  alta.
- **Tamaño del grupo:** 4–30. Por encima de ~12, use grupos pequeños de 3–4 para
  los ejercicios.

---

## Preparación (facilitador, antes de la sesión)

```bash
git clone https://github.com/ChelseaKR/nearmiss && cd nearmiss
python -m pip install -e ".[teaching]"   # stack de ejecución de Jupyter (extra aislado)
make teach                                # ejecuta los tres cuadernos en notebooks/_build/
```

Los cuadernos están en [`notebooks/teaching/`](../../notebooks/teaching/). Son
deterministas y sin conexión: sin RNG, sin red, sin datos reales. Puede
presentarlos en vivo (celda por celda) o entregar las copias ya ejecutadas de
`notebooks/_build/`. Si proyecta, el mapa de calor SVG del cuaderno 01 escala sin
pérdida.

**Nota de honestidad de datos para decir en voz alta:** los datos de Davis son
*datos sintéticos de demostración, no reportes reales.* El objetivo es el
razonamiento, no Davis.

---

## El plan de 90 minutos

| Tiempo | Segmento | Qué sucede |
| ---: | --- | --- |
| 0:00–0:10 | **Plantear la mentira** | Muestre un mapa de calor de conteo crudo sin leyenda. Pida al grupo que señale "la calle más peligrosa". Revele que es simplemente la más *concurrida*. Presente T4 en una línea: el mal uso más común de los hallazgos de este proyecto no es un ataque, es una lectura honesta pero equivocada. |
| 0:10–0:30 | **Cuaderno 01 — El mapa ingenuo** | Ejecútelo en vivo. Deténgase en la figura de dos paneles: el señuelo `seg-03` es el más brillante en el mapa de conteo crudo (izquierda) y se disuelve en el mapa normalizado por exposición (derecha); emerge el corredor plantado `seg-06`. Termine en la tabla ordenada publicada: el artefacto honesto es una tabla con tasas, intervalos y un grupo significativo marcado en texto, no una mancha de color. |
| 0:30–0:55 | **Cuaderno 02 — Encuentra el señuelo (ejercicio)** | En grupos pequeños: ordenar por conteo crudo (Paso 1), calcular tasas + IC del 95% con la función real de la tubería (Paso 2), medir la caída de posición (Paso 3). Los grupos se comprometen a una respuesta *antes* de la celda de Solución. Puesta en común: ¿quién encontró `seg-03`? ¿Qué en la columna de exposición lo delató? |
| 0:55–1:20 | **Cuaderno 03 — Rompe el IC** | Ejecute el grupo base, luego la *división* que fabrica un punto caliente en el limítrofe `seg-05`, luego la *fusión* que disuelve el corredor real `seg-06`. Enfatice: mismos reportes, misma estadística, tres "verdades". Resalte que el IC y la corrección FDR son reales pero no pueden salvarlo de una unidad de análisis manipulada. |
| 1:20–1:30 | **Cierre — los valores por defecto honestos** | Repase las mitigaciones de T4 como una lista de verificación que el grupo pueda aplicar a cualquier mapa que encuentre la próxima semana. Asigne la consigna para llevar a casa. |

¿Va con poco tiempo? Omita la demostración de *fusión* del cuaderno 03 (conserve
la *división*). ¿Va con tiempo de sobra o es un grupo avanzado? Agregue las
consignas de "amplíelo" más abajo.

---

## Consignas de discusión (vinculadas al modelo de amenazas T4)

Cada consigna corresponde a una **mitigación de T4** específica en
[`docs/THREAT-MODEL.md`](../THREAT-MODEL.md). Úselas en las pausas entre
segmentos.

- **Tras el cuaderno 01 — "Etiquetar el volumen como volumen".** *¿Dónde ha visto
  un mapa de conteo crudo o "de calor" presentado como peligro, riesgo o delito?
  ¿Qué única etiqueta habría hecho de la lectura honesta la lectura fácil?*
  (Mitigación: las superficies sin normalizar se etiquetan como *intensidad de
  reportes*, nunca como *peligro*; la etiqueta viaja con el artefacto.)
- **Tras el cuaderno 01 — "Publicar tasas, intervalos y significancia, no solo
  una superficie".** *¿Por qué una tabla ordenada con intervalos es más difícil de
  capturar fuera de contexto que un mapa de color? ¿Qué le aporta eso a la versión
  honesta?*
- **Tras el cuaderno 02 — "Nombrar el sesgo en la página".** *¿Quién está sobre y
  subrepresentado en un conjunto de datos de casi-accidentes por colaboración
  abierta? Una tasa fija el denominador — ¿qué sigue sin arreglar?* (Mitigación:
  cada informe declara quién está sobre/subrepresentado y qué efecto tiene en la
  conclusión.)
- **Tras el cuaderno 02 — "La tabla equivalente lleva las salvedades".** *Una
  persona usuaria de lector de pantalla nunca ve la mancha de color. ¿Qué debe
  contener la tabla para que llegue a la misma conclusión honesta?*
- **Tras el cuaderno 03 — MAUP y los límites de la estadística.** *El intervalo de
  confianza y la corrección FDR son protecciones reales. Nombre algo contra lo que
  cada uno NO protege.* (Respuesta: el IC atiende el ruido de muestreo, no una
  unidad elegida; el FDR atiende la suerte de comparaciones múltiples, no una
  unidad elegida después de ver los datos.)
- **Tras el cuaderno 03 — "Hacer que la versión honesta sea la citable".** *T4
  "se detiene" en el recorte: una vez que alguien captura una superficie y le
  quita la leyenda, el proyecto no puede controlar el título. Si no puede evitar
  el mal uso, ¿cuál es el objetivo realista?* (Respuesta: hacer que el artefacto
  honesto y etiquetado sea el más prominente y citable.)

**Consigna para llevar a casa.** Traiga un mapa de calor real de las noticias o
del tablero de una agencia. Responda: (a) ¿son conteos o una tasa? (b) ¿cuál es el
denominador, o falta uno? (c) ¿qué tendría que saber para confiar en el "punto
caliente"?

---

## Clave de respuestas

**Cuaderno 01 — El mapa ingenuo.**
- Calle "peor" por conteo crudo: **`seg-03`, "3rd St (B–C)"** — simplemente tiene
  la mayor cantidad de reportes (12 rebases cercanos + 5 peligros de superficie +
  3 escombros = 20).
- Calle peor normalizada por exposición: **`seg-06`, "5th St (C–D)"** — el punto
  caliente plantado (poca exposición, tasa alta).
- Por qué se invierte: el denominador de exposición de `seg-03` (8,000 viajes) es
  ~27× el del punto caliente (300), así que su tasa (2.50 /1,000) queda muy por
  debajo de la de `seg-06` (20.0 /1,000). Es exactamente el comportamiento que fija
  `tests/test_hotspot.py::test_busy_decoy_has_most_raw_reports_but_low_rate`.

**Cuaderno 02 — Encuentra el señuelo.**
- El señuelo es **`seg-03`, "3rd St (B–C)"**: encabeza la clasificación por conteo
  crudo pero es el que más cae, hasta cerca del fondo de la clasificación por tasa;
  **no** está entre los tres primeros por tasa y **no** se marca como grupo Gi\*
  significativo.
- El verdadero punto caliente es **`seg-06`, "5th St (C–D)"**: la tasa más alta y
  el centro del único grupo significativo.
- Dígale al grupo que la celda de revelación *afirma* estos hechos contra la
  tubería, así que la respuesta no es la opinión del facilitador — es el mismo
  código que controla las pruebas del proyecto.

**Cuaderno 03 — Rompe el IC.**
- Puntos calientes significativos base: **`seg-02`, `seg-06`, `seg-07`, `seg-10`**
  (el corredor de 5th St y sus calles transversales). `seg-05` es *limítrofe*: su
  valor p bilateral crudo es ~0.029 (menor a 0.05), pero el FDR lo retiene
  correctamente.
- **Fabricar (dividir):** cortar `seg-05` en dos bloques en el mismo lugar hace
  que ambas mitades crucen a "significativo" — un punto caliente conjurado
  puramente por la re-segmentación, sin ningún reporte nuevo.
- **Disolver (fusionar):** fusionar el corredor real (`seg-02/05/06/07/10`) en un
  solo bloque promediado deja **cero** segmentos significativos — Gi\* necesita
  vecinos de tasa alta para detectar un grupo, y la fusión los borra.
- Defensas: pre-registrar la segmentación; reportar la sensibilidad a la unidad;
  conservar todo el conjunto de comparación (descartar segmentos "aburridos"
  reduce `m` y afloja el umbral FDR); anclar la significancia a los reportes, no a
  la geometría.

**Ideas erróneas comunes que corregir.**
- *"Un número más grande significa más peligro".* Solo después de dividir por la
  exposición.
- *"La significancia estadística significa que es real".* La significancia
  depende de la unidad elegida y del conjunto de pruebas; una estrella Gi\* que
  sobrevive solo a una segmentación dibujada a mano es un artefacto MAUP.
- *"Un intervalo de confianza me dice que el mapa es correcto".* Cuantifica el
  ruido de muestreo para una segmentación fija; no dice nada sobre un denominador
  manipulado ni un límite manipulado.

---

## Amplíelo (para sesiones más largas o avanzadas)

- Pida al grupo cambiar `fdr_alpha` o la banda de Gi\* (`gi_band_m`) en
  `config/davis-demo.toml` y predecir, luego observar, el efecto en el conjunto
  significativo.
- Apunte insumos reales a los mismos cuadernos vía
  [`docs/REAL-DATA.md`](../REAL-DATA.md) y discuta qué se rompe cuando desaparece
  la respuesta conocida.
- Compare con los otros cuadernos de reproducibilidad del proyecto en
  [`notebooks/`](../../notebooks/README.md) y `make reproduce`.

## Lecturas adicionales (en este repositorio)

- [`docs/THREAT-MODEL.md`](../THREAT-MODEL.md) — T4 completo, con todas las
  mitigaciones.
- [`docs/METHODOLOGY.md`](../METHODOLOGY.md) — tasas, IC, Gi\* y FDR tal como los
  usa el proyecto.
- [`docs/LIMITATIONS.md`](../LIMITATIONS.md) — lo que el análisis no afirma.
- [`tools/make_fixtures.py`](../../tools/make_fixtures.py) — cómo se construyen el
  punto caliente plantado y el señuelo concurrido.
