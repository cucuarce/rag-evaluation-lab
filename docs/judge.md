# Etapa 3B: juez semántico de faithfulness (smoke)

Código: `src/rag_lab/faithfulness/` (`judge_config`, `judge_client`, `judge_run`, `smoke_selection`, `judge_compare`). Config: `configs/judge_groq.toml`. Tests: `tests/test_faith_judge_run.py` (35, todos offline).

## Flujo

```
rag-lab faith-judge-select     usa etiquetas humanas SOLO para elegir casos  -> data/stage3/judge_smoke_selection.json
rag-lab faith-judge --dry-run  dimensiona sin red
rag-lab faith-judge            NO lee etiquetas; escribe predicciones       -> runs/stage3/judge/<nombre>/
rag-lab faith-judge-compare    después: juez vs humano (no toca predicciones) -> reports/judge_<nombre>_comparison.json
```

## Modelo y solicitud

- `qwen/qwen3.8-27b` en Groq, de una familia distinta del generador (`openai/gpt-oss-120b`).
  - Disponible para la clave según `GET /models`.
  - Los metadatos de la API **no** listan `structured_outputs` en `supported_features`, pero la documentación de Groq lo incluye entre los modelos con `strict: true`.
  - La primera solicitud real lo confirmó: `json_schema` con `strict: true` y `JUDGE_SCHEMA` fue aceptado, y las 8 salidas validaron.
- Parámetros:
  - `temperature = 0`, `seed = 7`;
  - `max_completion_tokens = 1536`;
  - `include_reasoning = false`; `reasoning_effort` no se envía, así que rige el valor por defecto del proveedor.
- Prompt `judge-v1` (Etapa 3A, sin cambios) y esquema `JUDGE_SCHEMA` (sin cambios). Va **una afirmación por solicitud**, con ID neutro `A1`.
- Política técnica:
  - `max_retries = 0`: un caso es como máximo una solicitud HTTP.
  - Hay tope duro de solicitudes y de tokens: se reserva la estimación conservadora antes de enviar.
  - Un 400/422, un 429 que agota la cuota, una salida fuera del esquema o dos fallos transitorios seguidos **detienen** la corrida. No hay cambio de modo ni de modelo.
  - Caché en `cache/judge/`, ignorada por git; los errores no se cachean. Una corrida repetida reutiliza la caché y no sobrescribe predicciones sin `--force`.

## Independencia

- `judge_run` recibe solo la selección (tipo e id), las afirmaciones o perturbaciones (únicamente su texto) y `answers.jsonl`: pregunta, alcance temporal, contexto y citas.
- Un test sobre el AST prohíbe que los módulos del lado del juez mencionen etiquetas humanas, revisiones, expectativas, estratos o la comparación.
- Otro test verifica que los prompts reales del smoke no contienen IDs de caso, estratos, notas ni premisas humanas, ni el texto original de una perturbación.
- Las predicciones se escriben con su sha256 en el manifiesto antes de comparar. La comparación verifica ese hash antes y después.

## Clasificación de resultados

| Resultado | Significado |
|---|---|
| `technical_failure` | `api_error`, `not_run`, `format_error` o `incomplete`: no hay etiqueta. |
| `citation_error` | El juez declaró respaldo sin una cita literal válida (`judge_unverifiable`). |
| `semantic_error` | Etiqueta verificada distinta de la referencia humana. |
| `agree` | Coincide. |

Una cita válida no hace correcta la etiqueta: el verificador nunca sube una etiqueta.

## Smoke (2026-11-17)

**Selección congelada** (`cases_sha256 = f7f6251f…`), con semilla `stage3b-smoke-v1` y sin repetir qid:
- 2 originales `partially_supported`: e05-c3 y e28-c1;
- 2 originales `supported`: e21-c2 y e10-c1 (este último, histórico);
- 4 perturbaciones confirmadas: e18-c1 y e14-c1 numéricas, e27-c1 de negación y e19-c2 de unidad.

**Corrida:**
- 8 solicitudes, 8 `ok`, sin errores de API ni de formato.
- 14.474 tokens contabilizados: 13.146 de prompt y 1.328 de salida, con 0 de razonamiento informados.
- Latencia media de 1,33 s (máxima 2,34 s). El control de ritmo esperó 60 s en total por el límite de 8.000 TPM.
- Límites observados en los encabezados: 1.000 solicitudes por día y 8.000 tokens por minuto.

| Caso | Fuente | Humano (citado / contexto) | Juez (citado / contexto) | Resultado |
|---|---|---|---|---|
| J01 | e05-c3 | partially / supported | partially / supported | acuerdo |
| J02 | e28-c1 | partially / partially | **supported / supported** | error semántico (ambas) |
| J03 | e18-c1-p-number | unsupported / unsupported | unsupported / unsupported | acuerdo |
| J04 | e14-c1-p-number | unsupported / unsupported | unsupported / unsupported | acuerdo |
| J05 | e27-c1-p-negation | unsupported / unsupported | unsupported / unsupported | acuerdo |
| J06 | e19-c2-p-unit | unsupported / unsupported | unsupported / unsupported | acuerdo |
| J07 | e21-c2 | supported / supported | supported / supported | acuerdo |
| J08 | e10-c1 | supported / supported | supported / supported | acuerdo |

- **Acuerdo:** 7/8 en cada etiqueta, con IC Wilson 95% de [0,53; 0,98]. La kappa no se calcula porque n < 10.
- **Citas:** las 8 respuestas trajeron citas literales válidas; no hubo ningún `judge_unverifiable`.
- **J02:** es una generalización. La afirmación dice "a un plan superior (por ejemplo, Pro)", pero el fragmento solo documenta Starter → Pro y Pro → Pro Plus. La guía humana manda `partially_supported`, y el prompt `judge-v1` no tiene una regla explícita de generalización. **No se ajustó nada después de observarlo.**

**Límites:**
- n = 8, elegido por estratos: es descriptivo y no estima confiabilidad.
- Las 4 perturbaciones cambian un solo token y son controles fáciles.
- Ningún caso prueba conflictos de versión en el contexto completo; las perturbaciones de versión quedaron reservadas.
