# RAG Evaluation Lab

Laboratorio local y reproducible para medir la calidad de un sistema RAG sobre la base de
conocimiento de **Kestrel Billing**, una SaaS de facturación **ficticia**. Todos los
documentos, preguntas y datos son inventados para este proyecto.

> **Estado: Etapa 1 — evaluación de retrieval.** No hay generación con LLM, prompts,
> abstención, Ragas, jueces ni dashboard todavía. No requiere LLM, API externa ni credenciales.

## Qué hace hoy

1. Fragmenta 12 documentos Markdown (uno de ellos es una política **deprecated**) en chunks con
   offsets trazables al texto original.
2. Indexa embeddings locales (`intfloat/multilingual-e5-small`, revisión fijada) en ChromaDB.
3. Ejecuta dos configuraciones de retrieval sobre las mismas 40 preguntas de evaluación:
   - **A** — dense, k = 5
   - **B** — hybrid BM25 + dense con Reciprocal Rank Fusion, k = 5
4. Calcula Hit@k, Recall@k, Complete@k (multi-hop), MRR@k, Distractor@k y presencia de
   documentos deprecated, a partir de evidencia etiquetada por **citas textuales**.
5. Compara A y B pregunta por pregunta y deja constancia de modelos, parámetros, versiones y
   hashes en cada corrida.

Las definiciones exactas de relevancia, métricas y desempates están en
[`docs/metrics.md`](docs/metrics.md).

## Requisitos

- [uv](https://docs.astral.sh/uv/) (probado con 0.12.23)
- Python 3.12 (uv lo selecciona por `.python-version`)
- ~1 GB de disco para dependencias (torch CPU) y ~0,5 GB para el modelo de embeddings, que se
  descarga de Hugging Face en la primera ejecución.

## Instalación

```bash
uv sync
```

`uv.lock` fija todas las versiones. `pyproject.toml` usa `exclude-newer` para que la resolución
ignore releases posteriores al 2026-11-01, y torch se instala desde el índice CPU de PyTorch.

## Reproducir el experimento

```bash
# 1. Validar corpus, preguntas y etiquetas (no usa modelo)
uv run rag-lab validate --config configs/a_dense_k5.toml

# 2. Construir el índice (compartido por A y B: mismo corpus, chunking y embeddings)
uv run rag-lab index --config configs/a_dense_k5.toml

# 3. Evaluar ambas configuraciones
uv run rag-lab eval --config configs/a_dense_k5.toml --split eval
uv run rag-lab eval --config configs/b_hybrid_k5.toml --split eval

# 4. Comparación pareada
uv run rag-lab compare runs/eval/A_dense_k5 runs/eval/B_hybrid_k5

# 5. Estabilidad del ranking en este entorno (recarga el modelo en cada repetición)
uv run rag-lab stability --config configs/a_dense_k5.toml --repeats 3
uv run rag-lab stability --config configs/b_hybrid_k5.toml --repeats 3

# Tests y lint
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

El split `calibration` (10 preguntas separadas) se evalúa con `--split calibration`. Está
reservado para calibrar umbrales en la Etapa 2; no debe usarse para elegir configuraciones.

## Salidas

| Ruta | Contenido |
|---|---|
| `artifacts/index/<index_id>/` | `chunks.jsonl`, `embeddings.npy`, `index_manifest.json` (regenerable, no versionado) |
| `runs/<split>/<run>/manifest.json` | config completa, `index_id`, hashes de corpus y preguntas, versiones de paquetes, hash de `uv.lock`, plataforma |
| `runs/<split>/<run>/retrieval_results.jsonl` | top-k por pregunta con scores y rangos por componente |
| `runs/<split>/<run>/per_question.jsonl` | métricas por pregunta |
| `runs/<split>/<run>/summary.json` | agregados globales y por categoría |
| `reports/compare_*.json` | comparación pareada A vs B |
| `reports/stability_*.json` | estabilidad, diagnóstico ANN vs búsqueda exacta, casi-empates |

## Dataset

- `data/corpus/`: 12 documentos con front-matter TOML (`status`, `effective_date`,
  `supersedes` / `superseded_by`).
- `data/eval/`: 40 preguntas: 14 de un solo fragmento, 8 multi-hop, 8 con distractor y 10 sin
  evidencia.
- `data/calibration/`: 10 preguntas separadas (4 / 2 / 2 / 2).
- Cada split tiene `questions.jsonl` (solo `qid` y `question`, lo único que ve el retrieval) y
  `labels.jsonl` (evidencia, distractores y respuesta de referencia; lo lee solo la evaluación).
  Tests en `tests/test_leakage.py` verifican esa separación.

## Estructura

```
configs/            a_dense_k5.toml, b_hybrid_k5.toml (difieren solo en name y method)
data/               corpus/, eval/, calibration/
docs/metrics.md     definiciones normativas
src/rag_lab/
  corpus.py         carga y validación de versiones
  chunking.py       fragmentación con offsets
  embeddings.py     Sentence Transformers
  index.py          Chroma + embeddings.npy, índice direccionado por contenido
  retrieval.py      DenseRetriever, BM25Ranker, HybridRetriever (RRF)
  questions.py      carga estricta de preguntas
  runner.py         fase 1 (retrieval, sin etiquetas) y fase 2 (scoring)
  evaluation/       labels.py, metrics.py
  compare.py        comparación pareada
  stability.py      verificación de estabilidad
  validate.py       validación de datos
  cli.py            rag-lab
tests/
```

## Limitaciones

Ver la sección 8 de [`docs/metrics.md`](docs/metrics.md). Resumen: dataset chico y sintético,
efecto techo con k = 5, estabilidad verificada solo en el entorno donde se corre, y BM25 sin
stemming.
