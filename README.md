# RAG Evaluation Lab

Laboratorio local y reproducible para **medir** un sistema RAG por partes: retrieval, generación
con citas y abstención, y faithfulness por afirmación evaluada con un juez LLM contrastado con
etiquetas humanas. Incluye un dashboard local de solo lectura para explorar los resultados.

El corpus es la base de conocimiento de **Kestrel Billing**, una SaaS de facturación
**ficticia**. Todos los documentos, preguntas, respuestas de referencia y etiquetas se
crearon para este proyecto.

## Qué problema resuelve

Un RAG suele evaluarse con un único número ("accuracy") que mezcla tres fallas distintas:
- no recuperar la evidencia;
- recuperarla y responder mal, o no abstenerse cuando falta;
- responder algo plausible que los fragmentos citados no respaldan.

Este laboratorio separa esas fallas y deja cada resultado trazable:
- **Evidencia trazable.** Está etiquetada con citas textuales y offsets sobre el corpus.
- **Etiquetas aisladas.** Están en archivos separados de lo que ve el sistema, y los tests verifican que no haya fuga.
- **Umbral sin espiar eval.** El de abstención se calibra con un split propio, nunca con el de evaluación.
- **Corridas verificables.** Cada una registra configuración, modelos, versiones y hashes de entradas y salidas.
- **Juez auditado.** El juez semántico se compara contra anotación humana y sus errores se documentan como estudios de caso, no se ajustan después de verlos.

## Estado

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Retrieval: A dense vs B hybrid (BM25 + dense, RRF), k = 5 | completada |
| 2 | Generación con citas y abstención (`openai/gpt-oss-120b` en Groq) | completada |
| 3A | Faithfulness offline: normalización léxica v2, afirmaciones, anotación humana, perturbaciones | completada |
| 3B | Juez semántico `judge-v1-otpm` (`qwen/qwen3.8-27b` en Groq), 47 casos | completada |
| 4A | Dashboard Streamlit local, de solo lectura | completada |

No hay Ragas ni una configuración C. El proyecto no está desplegado.

## Resultados

> **Exploratorios y no generalizables.** El corpus tiene 12 documentos ficticios. La
> evaluación usa 40 preguntas (30 con evidencia y 10 sin ella) y 47 casos de faithfulness:
> 30 afirmaciones de una sola corrida de generación y 17 controles **sintéticos**. Los tests
> de signo dan p = 1,0 o no aplican: no hay evidencia estadística para declarar un ganador.
> Los números describen este conjunto, no el desempeño esperado de estos modelos en otro
> dominio.

### Retrieval: A (dense) vs B (hybrid), split eval, 30 preguntas con evidencia

| Métrica (k = 5) | A dense | B hybrid |
|---|---|---|
| Hit@5 | 1,000 | 1,000 |
| Recall@5 | 0,989 | 0,983 |
| Complete@5 (toda la evidencia requerida) | 0,967 | 0,967 |
| MRR@5 | 0,933 | 0,950 |
| Distractor@5 (n = 11; menor es mejor) | 0,182 | 0,273 |
| Documento deprecated en el top-5 (n = 29) | 0,172 | 0,172 |

- Las métricas difieren solo en 5 de 40 preguntas: e05, e14, e16, e33 y e39.
- Hay efecto techo con k = 5.
- Reporte: [`reports/compare_eval_A_dense_k5_vs_B_hybrid_k5.json`](reports/compare_eval_A_dense_k5_vs_B_hybrid_k5.json).

### Generación con citas y abstención (40 preguntas)

| | A dense | B hybrid |
|---|---|---|
| Respondibles respondidas | 29 / 30 | 28 / 30 |
| Respuestas indebidas a preguntas sin evidencia | 0 / 10 | 0 / 10 |
| Sobre-abstención (toda la evidencia estaba en el contexto) | 1 (e33) | 1 (e33) |
| Cobertura de `required_facts`, léxica v1 (oficial) | 0,879 | 0,911 |
| Cobertura de `required_facts`, léxica v2 | 0,948 | 0,946 |
| Precisión de citas vs evidencia etiquetada | 1,0 | 1,0 |
| Validez de citas (citan fragmentos entregados) | 1,0 | 1,0 |
| Errores de formato / API | 0 / 0 | 0 / 0 |

**Lectura:** A y B rinden prácticamente igual en generación.
- La ventaja aparente de B en v1 viene de un falso negativo de formato en A (e29: "25 %" vs "25%").
- La v2 se diseñó **después** de observar esos falsos negativos (e29 y e31). Corrige la medición, no el sistema. Se reporta aparte y la v1 sigue siendo la oficial.
- e33 muestra la fragilidad del gate: obtuvo un score de 0,8635 frente al umbral de 0,868271, y el gate bloqueó una pregunta que tenía la evidencia en el contexto. El umbral no se tocó usando eval.
- Detalle: [`docs/stage2_report.md`](docs/stage2_report.md) y [`docs/lexical_v2.md`](docs/lexical_v2.md).

### Faithfulness: juez `judge-v1-otpm` vs etiquetas humanas

Las 30 afirmaciones originales y los 17 controles sintéticos se reportan **por separado**.

| Grupo | Campo | Acuerdo | IC Wilson 95 % |
|---|---|---|---|
| Originales | `label_cited` | 28 / 30 | [0,79; 0,98] |
| Originales | `label_context` | 29 / 30 | [0,83; 0,99] |
| Perturbaciones sintéticas | ambos | 16 / 17 | [0,73; 0,99] |

**Cómo leer estas cifras:**
- La kappa global (0,88 / 0,91) no se usa como medida de confiabilidad: está inflada por mezclar originales con controles de clase opuesta.
- No hay originales `unsupported`. Los 17 negativos se construyeron cambiando un solo dato (número, unidad o negación) de afirmaciones respaldadas.
- **Corrida:** 47/47 respuestas válidas, 0 errores, 84.698 tokens.
- **Cambio operativo:** `max_completion_tokens` pasó de 1536 a 640 por el límite de tokens de salida por minuto de Groq. Es el único cambio respecto de `judge-v1`.
- **Detalle:** [`docs/judge.md`](docs/judge.md).

### Los tres errores del juez

| Caso | Qué pasó | Qué muestra |
|---|---|---|
| **J02** (e28-c1), generalización | La afirmación dice "a un plan superior (por ejemplo, Pro)". El fragmento solo documenta Starter → Pro y Pro → Pro Plus. El humano etiquetó `partially_supported`; el juez dijo `supported` con una cita válida, en el smoke y en la evaluación definitiva. | `judge-v1` no tiene una regla explícita para generalizaciones. |
| **J12** (e05-c1), respaldo fuera de lo citado | Las etiquetas crudas del juez coincidían con las humanas, pero su única evidencia venía de S3, un fragmento que la respuesta no citó. El verificador convirtió `label_cited` en `judge_unverifiable`. | Se cuenta como desacuerdo (`citation_error`): una etiqueta de respaldo exige una cita válida de un fragmento citado. |
| **J46** (e28-c2-p-negation), control sintético | Se le agregó un "no" a una afirmación respaldada. El juez citó dos fragmentos válidos que la contradicen, pero etiquetó `supported`. Su propio razonamiento concluye que la afirmación "es falsa". | Una cita literal válida no prueba faithfulness. Las etiquetas se emiten antes del razonamiento. |

El juez no se reajustó después de ver estos errores, y las predicciones no se modificaron.

## Arquitectura y metodología

```
data/corpus/ (12 .md, 1 deprecated)
  └─ chunking con offsets ─ embeddings multilingual-e5-small ─ ChromaDB
                          └─ BM25 ───────────────────────────── RRF ─┐
data/eval/questions.jsonl ─ retrieval A (dense) / B (hybrid), k = 5 ─┤
                                                                     ├─ métricas de retrieval  ◄─ labels.jsonl (aparte)
                            gate de abstención (umbral del split calibration)
                            └─ gpt-oss-120b, JSON estricto con citas ─ métricas de generación
                               └─ afirmaciones + etiquetas humanas + perturbaciones
                                  └─ juez qwen3.8-27b ─ verificador de citas ─ acuerdo juez vs humano
                                                                     └─ dashboard Streamlit (solo lectura)
```

| Componente | Elección |
|---|---|
| Embeddings | `intfloat/multilingual-e5-small`, revisión fijada; locales, en CPU |
| Índice | ChromaDB, direccionado por el contenido del corpus y la configuración |
| Retrieval B | BM25 + dense, fusionados con Reciprocal Rank Fusion (`rrf_k = 60`, 50 candidatos) |
| Generador | `openai/gpt-oss-120b` en Groq: `temperature 0.2`, `seed 7`, salida JSON con esquema estricto |
| Juez | `qwen/qwen3.8-27b` en Groq, de otra familia que el generador: `temperature 0`, `seed 7`, una afirmación por solicitud |

**Principios de método:**
- **Retrieval sin etiquetas.** Las preguntas (`questions.jsonl`) y las etiquetas (`labels.jsonl`) viven en archivos distintos; el retrieval nunca lee las etiquetas.
- **Umbral solo con calibración.** El gate se calibra con un split propio de 10 preguntas, nunca con eval.
- **Juez a ciegas.** No recibe etiquetas humanas, estratos ni el texto original de una perturbación. Un test sobre el AST lo verifica.
- **Predicciones congeladas.** Se guardan con su sha256 antes de compararlas, y la comparación verifica el hash antes y después.
- **Cambios de métrica a la vista.** Una métrica nueva, como la normalización léxica v2, se reporta junto a la oficial, sin reemplazarla.

## Dashboard local (sin API ni modelos)

El dashboard lee solo archivos versionados. No necesita `GROQ_API_KEY`, no descarga modelos y
no escribe archivos.

```bash
git clone <url-del-repo> && cd rag-evaluation-lab
uv sync --group dashboard
uv run --group dashboard streamlit run src/rag_lab/dashboard/app.py
# -> http://localhost:8501 (solo localhost, sin telemetría: .streamlit/config.toml)
```

`uv sync` instala también las dependencias del núcleo, entre ellas torch para CPU (~1 GB),
aunque el dashboard no las usa.

El dashboard tiene cuatro secciones:
- **Retrieval:** A vs B, por categoría y por pregunta.
- **Generación:** métricas v1 y v2, abstención, citas y comparación pareada.
- **Faithfulness:** acuerdo, matrices de confusión y limitaciones.
- **Failure explorer:** J02, J12, J46 y cualquiera de los 47 casos.

La barra lateral verifica los hashes de predicciones, selección y entradas del juez contra sus
manifiestos.

Más detalle en [`docs/dashboard.md`](docs/dashboard.md).

## Reproducción completa de los experimentos

### Requisitos

- [uv](https://docs.astral.sh/uv/) (probado con 0.12.23) y Python 3.12 (uv lo selecciona por `.python-version`).
- Para la instalación: `uv sync`. `uv.lock` fija todas las versiones, `exclude-newer` ignora releases posteriores al 2026-11-01 y torch se instala desde el índice CPU de PyTorch.

| Paso | Red | Clave |
|---|---|---|
| Dashboard, tests, `validate`, `compare`, `compare-gen`, `rescore-lexical`, `faith-agreement`, `faith-judge-compare` | no | no |
| `index`, `eval`, `stability`, `generate` (incluso con el generador simulado), `scripts/verify_stage2.py` | descarga única del modelo de embeddings de Hugging Face (~0,5 GB) para construir el índice local | no |
| `gen-check --online`, `generate` con `configs/gen_groq.toml`, `faith-judge` | API de Groq | `GROQ_API_KEY` en `.env` |

**Notas:**
- **Tests:** sin el índice local, 5 tests de integración de retrieval se omiten.
- **Clave:** copiá `.env.example` a `.env` (ignorado por git) y completá `GROQ_API_KEY`.
- **Caché:** las respuestas de la API se guardan en `cache/`, que tampoco se versiona. Con la caché poblada, repetir una generación no hace llamadas.
- **Sin caché, los resultados no son idénticos:** una nueva llamada a Groq puede devolver otra salida aunque se fije `seed`. Por eso los resultados oficiales son las salidas versionadas en `runs/` y no una nueva ejecución.

### Etapa 1: retrieval (ver [`docs/metrics.md`](docs/metrics.md))

```bash
uv run rag-lab validate --config configs/a_dense_k5.toml          # corpus, preguntas y etiquetas
uv run rag-lab index --config configs/a_dense_k5.toml             # índice compartido por A y B
uv run rag-lab eval --config configs/a_dense_k5.toml --split eval
uv run rag-lab eval --config configs/b_hybrid_k5.toml --split eval
uv run rag-lab compare runs/eval/A_dense_k5 runs/eval/B_hybrid_k5
uv run rag-lab stability --config configs/a_dense_k5.toml --repeats 3
uv run rag-lab stability --config configs/b_hybrid_k5.toml --repeats 3
```

El split `calibration` (10 preguntas) se evalúa con `--split calibration`. Está reservado para
calibrar el gate y no debe usarse para elegir configuraciones.

### Etapa 2: generación (ver [`docs/generation.md`](docs/generation.md))

```bash
# Calibrar el gate (SOLO con el split calibration)
uv run rag-lab eval --config configs/a_dense_k5.toml --split calibration
uv run rag-lab eval --config configs/b_hybrid_k5.toml --split calibration
uv run rag-lab calibrate-gate runs/calibration/A_dense_k5
uv run rag-lab calibrate-gate runs/calibration/B_hybrid_k5

# Pipeline offline con generador simulado y determinístico (sin red)
uv run rag-lab generate runs/eval/A_dense_k5 --gen-config configs/gen_fake.toml
uv run rag-lab generate runs/eval/B_hybrid_k5 --gen-config configs/gen_fake.toml

# Con Groq (requiere GROQ_API_KEY)
uv run rag-lab gen-check --gen-config configs/gen_groq.toml --online
uv run rag-lab generate runs/eval/A_dense_k5 --gen-config configs/gen_groq.toml
uv run rag-lab generate runs/eval/B_hybrid_k5 --gen-config configs/gen_groq.toml
uv run rag-lab compare-gen runs/eval/A_dense_k5/gen/groq_gpt-oss-120b runs/eval/B_hybrid_k5/gen/groq_gpt-oss-120b

# Verificación sin API de los artefactos versionados (requiere el índice local)
uv run python scripts/verify_stage2.py   # reescribe reports/verify_stage2.json
```

Los comandos del smoke previo y los topes de llamadas y tokens están en
[`docs/generation.md`](docs/generation.md). Los resultados están en
[`docs/stage2_report.md`](docs/stage2_report.md).

### Etapa 3A: faithfulness offline (ver [`docs/faithfulness.md`](docs/faithfulness.md))

```bash
uv run rag-lab rescore-lexical runs/eval/A_dense_k5/gen/groq_gpt-oss-120b runs/eval/B_hybrid_k5/gen/groq_gpt-oss-120b
uv run rag-lab faith-prepare      # respuestas únicas, perturbaciones y planillas (no pisa planillas editadas)
uv run rag-lab faith-import data/stage3/annotation/annotation_sheet_completed.csv --round 1
uv run rag-lab faith-import data/stage3/annotation/perturbation_review.csv --kind perturbations
uv run rag-lab faith-agreement --reference <etiquetas_a.jsonl> --evaluated <etiquetas_b.jsonl>
```

La guía de anotación está en [`docs/annotation_guide.md`](docs/annotation_guide.md).

### Etapa 3B: juez semántico (ver [`docs/judge.md`](docs/judge.md))

```bash
uv run rag-lab faith-judge-select --full        # debe reproducir cases_sha256 9fffef23…
uv run rag-lab faith-judge --config configs/judge_groq_otpm.toml --selection data/stage3/judge_full_selection.json   # API
uv run rag-lab faith-judge-compare --run runs/stage3/judge/judge-v1-otpm_qwen3.8-27b \
  --selection data/stage3/judge_full_selection.json --pilot runs/stage3/judge/smoke_qwen3.8-27b
```

Las predicciones del piloto parcial `full_qwen3.8-27b` no se versionan, porque su mensaje de
error contiene un identificador del proveedor. Solo se versiona su manifiesto.

Sin ese archivo, el comando regenera el reporte con las mismas métricas. Solo cambia
`pilot_stability`, que compara 8 casos en lugar de 11.

Los comandos de comparación reescriben los archivos de `reports/` que ya están versionados.
Para no tocarlos, conviene correrlos sobre una copia del repositorio.

### Tests y lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Salidas versionadas

| Ruta | Contenido |
|---|---|
| `runs/<split>/<run>/` | `manifest.json` (config, `index_id`, hashes, versiones, plataforma), `retrieval_results.jsonl`, `per_question.jsonl`, `summary.json` |
| `runs/<split>/<run>/gen/<gen>/` | `generations.jsonl` (respuesta cruda y validada, citas, gate, tokens), `gen_manifest.json`, `gen_summary.json`, `gen_per_question.jsonl` |
| `runs/stage3/judge/<run>/` | `predictions.jsonl` y `judge_manifest.json` con el sha256 de las predicciones |
| `reports/` | comparaciones A/B, estabilidad, gate, léxica v2, juez vs humano, `verify_stage2.json` |
| `data/stage3/` | respuestas únicas, afirmaciones, perturbaciones, etiquetas humanas (anotador seudonimizado) y selecciones del juez |

No se versionan:
- `artifacts/`: el índice, que se puede regenerar;
- `cache/`: las respuestas de la API;
- `.env`;
- los respaldos de planillas, los registros incrementales del juez y las predicciones del piloto parcial.

## Estructura

```
configs/            retrieval (A, B), generación (fake, groq), juez (smoke, full, otpm)
data/               corpus/, eval/, calibration/, stage3/
docs/               metrics, generation, stage2_report, lexical_v2, faithfulness,
                    annotation_guide, judge, dashboard, provenance
scripts/            verify_stage2.py
src/rag_lab/
  corpus.py, chunking.py, embeddings.py, index.py, retrieval.py, runner.py, compare.py,
  stability.py, validate.py, cli.py
  evaluation/       métricas de retrieval y generación, gate, léxica v2
  generation/       contexto, prompt, proveedores, caché, gate
  faithfulness/     afirmaciones, anotación, perturbaciones, juez, verificador, acuerdo
  dashboard/        data.py (lectura y validación), app.py (Streamlit)
tests/
```

## Limitaciones

**Datos:**
- El corpus es chico y sintético.
- El efecto techo con k = 5 deja poco margen para diferenciar A de B.
- BM25 funciona sin stemming.
- La estabilidad del ranking se verificó solo en el entorno donde se corrió.

**Faithfulness:**
- Hay un solo anotador humano y una sola ronda de anotación, así que no hay acuerdo entre anotadores.
- Los negativos son sintéticos y no hay afirmaciones originales `unsupported`.
- Cuatro razonamientos del juez llegaron cortados en 496 caracteres desde el proveedor. La causa no se pudo determinar, aunque las etiquetas no se ven afectadas.

**Reproducibilidad:**
- Los resultados con LLM dependen de un proveedor externo. Los modelos o sus límites pueden cambiar, y repetir la ejecución no garantiza salidas idénticas.

**Dashboard:**
- No tiene autenticación y está pensado solo para `localhost`.
- En pantallas angostas, la tabla de la matriz recorta la columna `total`; la lectura por fila de debajo muestra todos los valores.

Más detalle en la sección 8 de [`docs/metrics.md`](docs/metrics.md), en
[`docs/judge.md`](docs/judge.md) y en [`docs/dashboard.md`](docs/dashboard.md).

## Procedencia

Antes de publicar se reescribió el historial para cambiar solo el email de los commits. El
contenido de cada commit (su hash de tree) no cambió, pero los hashes de commit sí.

Los campos `git_commit` de los manifiestos de `runs/` conservan los hashes originales. La
correspondencia con los commits publicados y el procedimiento para verificarla están en
[`docs/provenance.md`](docs/provenance.md).

## Licencia

[MIT](LICENSE). Copyright (c) 2026 Alberto Arce.

El corpus, las preguntas, las etiquetas y los demás datos son material ficticio creado para
este proyecto y se distribuyen bajo la misma licencia.
