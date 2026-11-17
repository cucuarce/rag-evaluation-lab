# Etapa 2: generación, citas y abstención

Referencia normativa de la Etapa 2. Código: `src/rag_lab/generation/` (lado producción, sin
etiquetas) y `src/rag_lab/evaluation/gen_metrics.py`, `gen_scoring.py`, `gate_calibration.py`
(lado evaluación).

## 1. Flujo

```
runs/<split>/<A|B>/retrieval_results.jsonl   (Etapa 1, sin cambios)
        │  chunk_ids en orden + scores
        ▼
gate (score de evidencia vs umbral calibrado) ──► score < umbral: abstención "gate", sin LLM
        │
        ▼
context builder: S1..Sk + doc_id, título, versión, estado VIGENTE/HISTÓRICO, período, texto
regla temporal (solo texto de la pregunta) ──► current | historical_anchored | historical_unanchored
        │
        ▼
prompt (1 mensaje) ──► Groq (structured outputs, strict) ──► JSON {answer, citations, abstain, abstain_reason}
        │                      caché por hash · presupuesto · reintentos acotados
        ▼
validación: JSON/esquema, citas ⊆ fragmentos suministrados ──► generations.jsonl + gen_manifest.json
        │
        ▼  (fase 2, recién acá se leen etiquetas)
gen_per_question.jsonl + gen_summary.json ──► compare-gen A vs B
```

El modelo recibe **solo** la pregunta, los fragmentos recuperados con sus metadatos, el
alcance temporal y la fecha de referencia. Nunca recibe `labels.jsonl`, `reference_answer`,
`required_facts`, `forbidden_facts` ni notas (`tests/test_gen_leakage.py`).

## 2. Modelo

`openai/gpt-oss-120b` en Groq (configurable en `configs/gen_groq.toml`). Criterios:
modelo de producción en Groq; soporta *structured outputs* con `strict: true` (decodificación
restringida al esquema JSON); multilingüe. `llama-3.3-70b-versatile`, Llama 4 y Kimi K2 figuran
como dados de baja en la página de deprecaciones de Groq (consultada 2026-11-16).
Parámetros: `temperature=0.2`, `reasoning_effort="low"`, `include_reasoning=false`,
`max_completion_tokens=1024` (incluye razonamiento), `seed=7`. Groq recomienda 0.5–0.7 para
modelos de razonamiento; se usa 0.2 por pedido explícito de temperatura baja. Un `seed` y una
temperatura baja **no** garantizan salidas idénticas entre llamadas: por eso se cachea la
respuesta y las métricas se calculan sobre la respuesta guardada.

## 3. Regla temporal (vigente vs histórico)

`generation/temporal.py`, determinística, sobre el texto de la pregunta:

| Resultado | Disparadores (sin acentos, minúsculas) | Instrucción al modelo |
|---|---|---|
| `historical_anchored` | "antes de [día de] [mes de] AAAA" con fecha ≤ referencia; "en/durante/hasta/desde [mes de] AAAA" con año < año de referencia; "versión N", "política anterior/previa/vieja", "vN" | usar la versión vigente en ese momento aunque sea deprecated, y decirlo |
| `historical_unanchored` | "era", "eran", "regía", "solía", "anteriormente", "estuvo vigente"… sin fecha | si las versiones discrepan, abstenerse con `needs_temporal_context` y pedir la fecha |
| `current` | todo lo demás | usar solo fragmentos VIGENTES; no citar históricos |

Fecha de referencia fija (`reference_date = 2026-11-01`) para reproducibilidad.
Limitaciones: es léxica (no entiende "el año pasado" ni "cuando me suscribí en 2024" si la
frase no matchea); "era" puede aparecer en preguntas no temporales. En el benchmark solo e10
dispara la regla (`historical_anchored`); el resto se clasifica `current`. La regla se escribió
sabiendo que e10 existía (lo señaló la revisión de la Etapa 1): no es una validación ciega.

No se filtran ni penalizan versiones viejas: A y B entregan al generador los mismos chunks que
en la Etapa 1, con su estado visible.

## 4. Gate de abstención

**Score** (no comparable entre métodos):
- A (dense): coseno exacto del chunk top-1 (e5-small; en este corpus ~0,82–0,95).
- B (hybrid): el score RRF solo codifica rangos (≈ 2/61 para casi cualquier pregunta) y no
  mide fuerza de evidencia. Se usa el **máximo coseno dense** entre los k chunks que recibe el
  generador (`details.dense_score`).

**Calibración** (`rag-lab calibrate-gate runs/calibration/<run>`), solo split calibration:
umbral = punto medio entre el máximo score de no respondibles y el mínimo de respondibles si
son separables; si no lo son, el mínimo de respondibles. Abstención si score < umbral. El
reporte queda en `reports/gate_<run>.json` con hashes de etiquetas y resultados de calibración;
la generación rechaza un umbral de otra configuración, índice o split.

Con 10 preguntas (8 respondibles, 2 no respondibles) el umbral es frágil. No se ajusta mirando
eval: sus efectos se miden como sobre-abstención y respuestas indebidas.

**Abstención del LLM**: el prompt exige `abstain=true` si los fragmentos no alcanzan
(`insufficient_evidence`) o si falta contexto temporal (`needs_temporal_context`). Cada
abstención registra su causa: `gate` o `llm`.

## 5. Validación de la salida

- JSON inválido, claves distintas, tipos o `abstain_reason` fuera del enum → `format_error`
  (no se reintenta ni se repara).
- Citas: se normaliza solo `"[S1]"` → `"S1"`. Una cita a un ID no suministrado se guarda en
  `invalid_citations` y no cuenta como evidencia.
- Inconsistencias (respuesta sin citas válidas, abstención sin motivo, etc.) se registran en
  `consistency_issues`.

## 6. Métricas (determinísticas)

Por pregunta, sobre la respuesta guardada. Ninguna es *faithfulness*.

| Métrica | Definición | Aplica a |
|---|---|---|
| `citation_validity` | citas a fragmentos suministrados / citas emitidas | respuestas (no abstenciones) con ≥1 cita |
| `citation_precision` | chunks citados que cubren un span gold (τ=0,5) / chunks citados válidos | respondibles respondidas |
| `cited_evidence_recall` | requisitos gold satisfechos por los chunks **citados** / requisitos | respondibles respondidas |
| `required_facts_coverage` | `required_facts` presentes en la respuesta / total | respondibles respondidas |
| `all_required_facts` | 1 si están todos | respondibles respondidas |
| `forbidden_present` | 1 si aparece algún `forbidden_fact` | respondidas con forbidden_facts |
| `improper_answer` | 1 si respondió una pregunta sin evidencia en el corpus | no respondibles |
| `over_abstention` | 1 si se abstuvo teniendo **toda** la evidencia en el contexto (complete@k=1) | respondibles |
| `answered_with_incomplete_evidence` | respondió sin tener toda la evidencia en el contexto | respondibles |
| `version_error` | vigente: cita un chunk deprecated (si hubo alguno en el contexto); histórica: no cita ningún chunk deprecated | respondibles respondidas |
| errores | `format_error`, `api_error`, `not_run` (abortos/presupuesto), `consistency_issues` | todas |

Coincidencia de hechos: sin acentos, minúsculas, números escritos 0–20/30 → dígitos, espacios
colapsados; coincidencia con límites (`"5"` no matchea `"15"` ni `"5,5"`; `"USD 99"` no matchea
`"USD 99,9"`). Es **léxica**: una paráfrasis correcta ("no tiene SLA contractual" vs "no tienen
SLA contractual") cuenta como faltante, y mencionar un dato prohibido para contrastarlo
("antes eran 14 días") cuenta como presente. Por eso se publican las respuestas completas.

> **Corrección (Etapa 3A):** la frase "`"5"` no matchea `"5,5"`" es inexacta. El límite izquierdo no excluye la parte decimal de otro número, así que `"5"` sí coincide con el `5` final de `"5,5"` o `"2,5"`. Ninguna de las 104 comprobaciones de hechos del benchmark cambia con un límite más estricto, así que las métricas reportadas no se ven afectadas. Ver [`lexical_v2.md`](lexical_v2.md).

`citation_precision` subestima si el modelo cita un chunk relevante no etiquetado como gold, y
una cita correcta no prueba que la afirmación esté en el chunk: verificarlo es la faithfulness
semántica de la Etapa 3 (juez + revisión humana).

## 7. Llamadas, costos y fallos

- Caché persistente en `cache/llm/` (no versionada): clave = sha256(parámetros del modelo,
  mensajes, esquema). Solo se cachean respuestas HTTP exitosas. Un hit no consume presupuesto.
- Presupuesto por comando (`max_calls`, `max_total_tokens`): al agotarse, la corrida se marca
  `aborted` y las preguntas restantes quedan `not_run`. No se comparan corridas incompletas.
- Estimación previa conservadora de cada llamada: `ceil(caracteres del prompt / 2,5)` +
  `max_completion_tokens` (1024, incluye razonamiento). En este corpus se midió ~3,2
  caracteres/token, así que la estimación sobreestima.
- El presupuesto reserva esa estimación **antes** de enviar: si `usados + estimación` supera
  el tope, la corrida se frena. `generate --max-calls/--max-tokens` solo pueden achicar los
  topes de la config (para repartir un presupuesto global entre A y B); el valor efectivo
  queda en `gen_manifest.json` (`budget`) y la config no cambia.
- Ritmo: `min_interval_s` entre llamadas (≤ 24 RPM) y cubeta de tokens a partir de
  `x-ratelimit-limit-tokens` / `x-ratelimit-remaining-tokens` de la última respuesta:
  disponibles(t) = min(L, R + Δt·L/60); se espera hasta tener estimación × 1,15. Si
  `x-ratelimit-remaining-requests` < 5 (cuota diaria), la corrida se frena.
- Reintentos (máx. 3) solo ante timeout, conexión, 5xx o 429 con `retry-after` ≤ 60 s.
  429 con `retry-after` mayor, 401/403/404 o 3 fallos consecutivos frenan la corrida.
  400/422 se registran por pregunta sin reintento. El SDK se usa con `max_retries=0`.
- No se repiten llamadas para promediar ni se usa juez LLM.

## 8. Secretos

`GROQ_API_KEY` se lee del entorno o de `.env` (ignorado por git; ver `.env.example`). La clave
no se imprime ni se guarda en manifiestos, caché o reportes; los mensajes de error pasan por
`redact`. `rag-lab gen-check` informa solo si la clave está presente y su origen.
