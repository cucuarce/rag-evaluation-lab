# Etapa 2 — Reporte de cierre: generación con citas y abstención

Benchmark online de generación sobre las 40 preguntas de eval con dos configuraciones de
retrieval (A: dense k=5, B: hybrid BM25+dense RRF k=5) y el mismo generador
(`openai/gpt-oss-120b` en Groq). Definiciones de métricas: [`generation.md`](generation.md).
Todos los números de este documento salen de los artefactos versionados y se pueden
re-verificar sin API con `uv run python scripts/verify_stage2.py` (ver §8).

## 1. Conclusiones

- **A y B rinden prácticamente igual en generación.** Las métricas difieren en 4 de 40
  preguntas; los tests de signo pareados dan p = 1,0 o no aplican.
- **No hay evidencia estadística suficiente para declarar un ganador.** Con 30 preguntas
  respondibles y 10 sin evidencia, diferencias de 1 pregunta no son interpretables.
- **Las diferencias observadas se explican principalmente por retrieval**, no por el
  generador: e14 (B no recuperó el fragmento con los formatos de exportación, ya visto en la
  Etapa 1); e05 difiere en qué fragmentos se citan con contextos distintos; e29 es un falso
  negativo de la métrica léxica (§3).
- **Respuestas indebidas: 0 de 10** en ambas configuraciones (7 abstenciones por gate y 3 por
  el LLM).
- **e33 muestra la fragilidad del gate:** score 0,8635 frente a un umbral de 0,868271; la
  evidencia estaba en el contexto y el gate la bloqueó (única sobre-abstención en A y en B).
  **El umbral no debe modificarse usando eval**: solo con el split de calibración.
- **e05 muestra que correctness ≠ groundedness/faithfulness:** A respondió el valor correcto
  (USD 96) sin tener en el contexto toda la evidencia etiquetada como requerida
  (complete@5 = 0) y citando 1 de los 3 requisitos.
- **e10 eligió correctamente la versión histórica (v2, 14 días)**, pero la respuesta quedó
  parcialmente incompleta respecto de lo pedido: el prompt pide indicar el período o la
  versión y la respuesta no lo hace.
- **Las métricas léxicas tienen falsos negativos** por Unicode, paráfrasis y formato (e27, e29,
  e31).
- **Validez y precisión de citas no equivalen a faithfulness:** indican que la cita apunta a un
  fragmento entregado que contiene evidencia etiquetada, no que cada afirmación esté respaldada
  por ese fragmento.

## 2. Métricas de generación A/B (eval, 40 preguntas)

| Métrica | A dense | B hybrid |
|---|---|---|
| Estado de la corrida | completa (40/40) | completa (40/40) |
| Respondidas / abstenciones (total) | 29 / 11 | 28 / 12 |
| **Respondibles (n = 30)** | | |
| Respondidas | 29 | 28 |
| Abstenciones por gate / por LLM | 1 (e33) / 0 | 1 (e33) / 1 (e14) |
| Sobre-abstención (toda la evidencia en contexto) | 1 (e33) | 1 (e33) |
| Abstención con evidencia incompleta en contexto | 0 | 1 (e14) |
| Respondió con evidencia incompleta en contexto | 1 (e05) | 0 |
| **Sin evidencia en el corpus (n = 10)** | | |
| Abstenciones por gate / por LLM | 7 / 3 | 7 / 3 |
| Respuestas indebidas | 0 / 10 | 0 / 10 |
| **Respondibles respondidas** | n = 29 | n = 28 |
| Cobertura de `required_facts` (léxica) | 0,8793 | 0,9107 |
| Con todos los `required_facts` (léxica) | 0,8621 | 0,8929 |
| Con algún `forbidden_fact` (n = 9 en cada una) | 0 / 9 (0,0) | 0 / 9 (0,0) |
| Precisión de citas vs evidencia etiquetada | 1,0 | 1,0 |
| Requisitos de evidencia cubiertos por lo citado | 0,9598 | 0,9702 |
| **Todas las respuestas emitidas** | n = 29 | n = 28 |
| Validez de citas (citan fragmentos entregados) | 1,0 | 1,0 |
| Respuestas con citas inválidas / sin citas | 0 / 0 | 0 / 0 |
| **Errores** | | |
| Formato / API / no ejecutadas / inconsistencias | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Selección de versión: errores / preguntas verificadas | 0 / 6 | 0 / 5 |

Notas:
- Las 9 preguntas con `forbidden_facts` respondidas son las mismas en A y B: e02, e06, e10,
  e11, e16, e25, e27, e29, e39. Ninguna respuesta contiene un hecho prohibido.
- La verificación de versión aplica a preguntas cuyo contexto incluye un chunk deprecated o
  cuya evidencia es histórica: A = e06, e10, e14, e18, e21, e39; B = e06, e10, e18, e21, e39
  (B se abstuvo en e14).
- Las métricas de retrieval de la Etapa 1 no cambian (A: Recall@5 0,989, MRR@5 0,933;
  B: Recall@5 0,983, MRR@5 0,950). Las métricas de esta tabla miden lo que hace el generador
  con esos mismos fragmentos.

## 3. Revisión manual de hechos faltantes (no es una métrica oficial)

El contador léxico marcó `required_facts` faltantes en 4 preguntas. La revisión manual de esas
respuestas **no modifica las métricas reportadas** arriba:

| Pregunta | Marcado como faltante | Lectura manual |
|---|---|---|
| e04 (A y B) | `Retry-After` | Omisión real: menciona el código 429 pero no el encabezado. |
| e27 (A y B) | `no tienen SLA contractual` | Paráfrasis: la respuesta dice "no tiene SLA contractual". |
| e29 (solo A) | `25%` | Formato: la respuesta escribe "25 %" (con espacio). |
| e31 (A y B) | `HMAC-SHA256`, `Kestrel-Signature` | Unicode: guion U+2011 y espacio fino U+202F en la respuesta. |

Conclusión conservadora: entre las preguntas marcadas, la única omisión real identificada es
e04, en A y en B. La ventaja aparente de B en cobertura de hechos proviene de e29, que es un
falso negativo de formato en A. No se revisaron manualmente las respuestas que el contador dio
por correctas.

## 4. Diferencias pregunta por pregunta

| Pregunta | Diferencia | Origen |
|---|---|---|
| e14 (multi-hop) | A responde completo (30 días; CSV y JSON). B se abstiene: "no indica en qué formatos". | Retrieval: B no recuperó el fragmento con los formatos (Etapa 1). La abstención de B evita inventar, pero tampoco responde la parte que sí estaba respaldada (30 días). |
| e05 (multi-hop) | Ambas responden USD 96. B cita 2 de 3 requisitos; A cita 1 de 3. | Contextos distintos (A no tenía la evidencia de la guía de migración). |
| e29 | Mismo contenido ("25 %" vs "25%"). | Falso negativo de la métrica léxica en A. |
| e12 | Mismas métricas; A cita además `novedades-2026`. | Sin efecto en métricas. |

## 5. Políticas vigentes e históricas

| Pregunta | Regla temporal | Posición de v2 | Respuesta (A y B) | Cita | Versión |
|---|---|---|---|---|---|
| e06 | vigente | 1.º en A y B | 30 días corridos desde el primer cobro | v3 | correcta |
| e21 | vigente | 1.º en A y B | No; se acredita como saldo a favor | v3 | correcta |
| e39 | vigente | 1.º en B, 2.º en A | 5 a 10 días hábiles | v3 | correcta |
| e10 | histórica ("antes de marzo de 2026") | — | era de 14 días corridos | v2 | correcta; no indica período/versión (cubre 1 de 2 requisitos citados) |

El riesgo de la Etapa 1 (v2 rankeada por encima de v3) no produjo errores de selección de
versión en estas preguntas, sin filtrar ni penalizar documentos. Son 4 casos: es evidencia de
que los metadatos de vigencia y la regla temporal funcionaron aquí, no una garantía general.

## 6. Llamadas, tokens y latencia

| | A | B | Benchmark A+B |
|---|---|---|---|
| Generaciones reales | 29 | 29 | 58 (autorizado: 80) |
| Respuestas de caché | 3 (e06, e10, e21: smoke) | 3 (e21: smoke; e02, e32: corrida A) | 6 |
| Sin llamada (gate) | 8 | 8 | 16 |
| Tokens prompt / salida / razonamiento | 32.037 / 3.224 / 988 | 32.264 / 3.104 / 912 | |
| Tokens totales | 35.261 | 35.368 | 70.629 (autorizado: 110.000) |
| Latencia media / mediana / máx. (reales) | 0,77 / 0,71 / 1,74 s | 0,89 / 0,78 / 1,98 s | |
| Espera del limitador | 172 s | 175 s | |
| 429 / reintentos / errores | 0 / 0 / 0 | 0 / 0 / 0 | |

- Topes efectivos: A con `--max-calls 40 --max-tokens 55000`; B con `--max-calls 40
  --max-tokens 74739` (remanente del global). Registrados en cada `gen_manifest.json`.
- Límites reales observados en los encabezados: 1000 requests/día y 8000 tokens/minuto.
- Smoke previo: 4 generaciones y 4.709 tokens (+1 consulta de modelos). Total Etapa 2:
  62 generaciones, 75.338 tokens.
- Caché por contenido: e02, e21 y e32 tuvieron el mismo top-5 en A y B, por lo que comparten
  prompt y respuesta. En esas preguntas A y B no son muestras independientes.

## 7. Limitaciones

- Dataset pequeño (30 respondibles, 10 sin evidencia) escrito por el diseñador del sistema.
- Gate calibrado con 10 preguntas (8 respondibles, 2 sin evidencia). Los scores de gate
  fueron idénticos en A y B en las 40 preguntas (mismo coseno máximo en el contexto).
- e06, e10 y e21 (eval) se usaron en el smoke; sus respuestas se reutilizaron desde la caché.
  El prompt no se modificó después del smoke.
- Una sola muestra por pregunta. Temperatura 0,2 y `seed` no garantizan salidas idénticas en
  nuevas llamadas: la reproducibilidad es sobre las respuestas guardadas.
- Métricas léxicas con falsos negativos (§3). Validez/precisión de citas no es faithfulness;
  la faithfulness semántica queda para la Etapa 3.

## 8. Artefactos y verificación

| Ruta | Contenido |
|---|---|
| `runs/eval/{A_dense_k5,B_hybrid_k5}/gen/groq_gpt-oss-120b/` | `generations.jsonl` (respuesta cruda y validada, contexto, gate, tokens, latencia, encabezados de rate limit), `gen_manifest.json` (config, hashes, presupuesto, consumo), `gen_per_question.jsonl`, `gen_summary.json` |
| `runs/smoke/{calibration_A,eval_A}/` | corridas del smoke (c01, c09, e06, e10, e21) |
| `reports/gate_{A_dense_k5,B_hybrid_k5}.json` | umbral del gate calibrado con el split calibration |
| `reports/compare_gen_groq_gpt-oss-120b_A_dense_k5_vs_B_hybrid_k5.json` | comparación pareada |
| `reports/verify_stage2.json` | salida de `scripts/verify_stage2.py` |

`scripts/verify_stage2.py` (sin API; requiere el índice local) verifica que las entradas
coinciden con los hashes de los manifiestos, que A y B son comparables, que re-puntuar las
respuestas guardadas reproduce exactamente las métricas guardadas, que los 64 prompts enviados
(32 por configuración, incluidos los de caché) se reconstruyen con el mismo sha256 sin datos de
referencia, que las respuestas validan contra el esquema, que no hay secretos en `runs/`,
`reports/` ni `docs/`, y que el consumo está dentro de lo autorizado.

No se versiona `cache/llm/` (62 respuestas, ~254 KB): su contenido está duplicado en
`generations.jsonl` (`raw_content`, uso y latencia), que es lo que usan el scoring y la
verificación. Sin la caché, volver a ejecutar `rag-lab generate` haría llamadas nuevas.
