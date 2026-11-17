# Definiciones: relevancia, ranking y métricas de retrieval

Este documento es la referencia normativa de la Etapa 1. El código que lo implementa está en
`src/rag_lab/evaluation/metrics.py`, `src/rag_lab/retrieval.py` y `src/rag_lab/chunking.py`.

## 1. Offsets y spans de evidencia

- Todos los offsets son índices de caracteres `[start, end)` sobre `Document.body`: el texto del
  archivo Markdown **después** del front-matter `+++ … +++`, con finales de línea `\n`.
- La evidencia se etiqueta como **cita textual** (`quote`) en un documento, no como ID de chunk.
  Al cargar las etiquetas, cada cita se resuelve a `[start, end)` y debe aparecer **exactamente
  una vez** en el documento (si no aparece o es ambigua, la carga falla).
- Por eso las etiquetas sobreviven a cambios de chunking: el mismo dataset sirve para cualquier
  configuración de fragmentación.

## 2. De span a relevancia de chunk

Sea τ = `span_coverage_threshold` (configurado en 0,5).

- Un chunk *c* **cubre** un span *s* si están en el mismo documento y
  `|[c.start, c.end) ∩ [s.start, s.end)| / |s| ≥ τ`.
- Casos límite (cubiertos por tests en `tests/test_metrics.py`):
  - cobertura exactamente igual a τ → cubre;
  - un chunk que termina justo donde empieza el span (intervalos que se tocan) → no cubre;
  - mismo rango en otro documento → no cubre;
  - con τ = 1 se exige que el span esté contenido entero.
- `rag-lab validate` falla si algún span no queda cubierto por ningún chunk e informa los
  spans que no entran en un único chunk.

## 3. Requisitos de evidencia (multi-hop)

Cada pregunta respondible tiene una lista de **requisitos** `G = {g1, g2, …}`. Cada requisito
tiene una o más citas **alternativas** (por ejemplo, el mismo dato en el documento de límites
y en el changelog). Un requisito se satisface si algún chunk recuperado cubre alguna de sus
alternativas. Las preguntas multi-hop tienen ≥ 2 requisitos y **todos** son necesarios.

- Un chunk es **gold** si satisface algún requisito.
- Un chunk es **distractor** si cubre algún span distractor etiquetado **y no es gold**. Si un
  mismo chunk contiene la evidencia correcta y la incorrecta, cuenta como gold: el retrieval no
  puede separarlas y el problema pasa a la generación.

## 4. Métricas por pregunta (solo preguntas respondibles)

`R_k` = los k chunks recuperados, en orden (k = 5).

| Métrica | Definición | Rango / sentido |
|---|---|---|
| `hit@k` | 1 si algún chunk de `R_k` es gold | {0,1}, ↑ |
| `recall@k` | requisitos satisfechos en `R_k` / total de requisitos | [0,1], ↑ |
| `complete@k` | 1 si `recall@k = 1` (toda la evidencia necesaria recuperada) | {0,1}, ↑ |
| `rr@k` | 1 / rango del primer chunk gold en `R_k`; 0 si no hay | [0,1], ↑ |
| `distractor@k` | 1 si hay un chunk distractor en `R_k` con rango menor que el primer gold, o si hay un distractor y ningún gold. **Solo aplica** a preguntas con distractores etiquetados (de cualquier categoría) | {0,1}, ↓ |
| `deprecated_in_topk` | 1 si `R_k` contiene algún chunk de un documento deprecated. **Solo aplica** si toda la evidencia gold está en documentos vigentes | {0,1}, ↓ (informativa) |

Agregados: promedio sobre las preguntas en que la métrica aplica (`*_n` informa cuántas).
`MRR@k` = promedio de `rr@k`. Se reportan globales y por categoría.

Las preguntas **no respondibles** no tienen métricas de retrieval en la Etapa 1: no hay
evidencia que recuperar. Se registran sus resultados y el score top-1 para calibrar la
abstención en la Etapa 2 (con el split `calibration`, nunca con `eval`).

## 5. Reglas de ranking y desempate

**Dense (configuración A)**
1. Embeddings `intfloat/multilingual-e5-small` con revisión fijada, prefijos `query: ` y
   `passage: `, normalizadas a norma 1 (`normalize_embeddings=True`), float32.
2. Chroma (HNSW, espacio coseno) propone `candidate_pool = 50` candidatos (búsqueda aproximada).
3. Cada candidato se re-puntúa de forma exacta: coseno = producto punto en float64 contra la
   matriz propia `embeddings.npy`. No se usan las embeddings que devuelve Chroma, que pueden
   diferir en los últimos bits (medido: hasta 7,5e-9).
4. Orden: score redondeado a 6 decimales, descendente; desempate por `chunk_id` ascendente.

**BM25 (componente léxico de B)**
- `rank_bm25.BM25Okapi(k1=1.5, b=0.75, epsilon=0.25)` sobre el mismo texto que se embebe
  (título + sección + chunk).
- Tokenización: NFKD sin diacríticos, minúsculas, números con separadores (`5.000`, `99,9`),
  lista fija de stopwords, **sin stemming**.
- Solo entran al ranking chunks con score > 0. Mismo orden y desempate que dense.

**Hybrid RRF (configuración B)**
- Los scores dense (coseno) y BM25 no son comparables, así que **solo se fusionan rangos**:
  `rrf(c) = Σ_listas 1 / (rrf_k + rango(c))`, con `rrf_k = 60`, rangos 1-based, sobre el
  top-50 de cada lista. Un chunk ausente de una lista no suma por ella.
- Orden: rrf redondeado a 6 decimales, descendente → mejor rango individual ascendente →
  `chunk_id` ascendente.

## 6. Versiones históricas (deprecated)

- El índice **incluye** los documentos deprecated, con metadatos explícitos
  (`status`, `effective_date`, `end_date`, `superseded_by` / `supersedes`), validados en
  `corpus.validate_versioning`. Cada chunk lleva `status` y `superseded_by`.
- Motivo: algunas preguntas legítimas son históricas (e10: "¿cuál era el plazo antes de marzo
  de 2026?"). En ellas la versión deprecated es la evidencia gold.
- En preguntas sobre la política vigente, la versión deprecated se etiqueta como
  **distractor**: recuperarla por encima de la vigente se penaliza en `distractor@k`.
- A y B **no** filtran por `status`. La decisión de filtrar, penalizar o solo mostrar el estado
  al generador queda para la Etapa 2, con evidencia de esta etapa.

## 7. Comparación pareada

`rag-lab compare` exige que ambas corridas compartan `index_id` (corpus + chunking +
embeddings), hash de preguntas, hash de etiquetas, split, k y τ; si no, falla. Por cada métrica
cuenta en cuántas preguntas gana A, gana B o empatan, y calcula un test de signo exacto
bilateral sobre los pares no empatados. Con n = 30 preguntas respondibles, esto **no** es
evidencia fuerte de nada: el reporte lo dice explícitamente.

## 8. Limitaciones conocidas

- Dataset pequeño y escrito por la misma persona que diseñó el sistema: riesgo de preguntas
  "fáciles" para el retriever (efecto techo con k = 5 sobre 68 chunks).
- `hit@k` no distingue multi-hop incompleto; por eso se reportan `recall@k` y `complete@k`.
- `distractor@k` no puede activarse cuando gold y distractor comparten chunk (informado por
  `rag-lab validate` en `distractor_shares_chunk_with_gold`).
- La estabilidad del ranking se verifica en el entorno donde se ejecuta. No se afirma igualdad
  entre distinto hardware, SO o versiones de BLAS/torch; `rag-lab stability` informa los
  márgenes de score más chicos (casi-empates) que serían los primeros en invertirse.
