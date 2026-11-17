# Etapa 3B: juez semántico de faithfulness

- **Código:** `src/rag_lab/faithfulness/` (`judge_config`, `judge_client`, `judge_run`, `smoke_selection`, `judge_compare`).
- **Configs:**
  - `configs/judge_groq.toml`: smoke, piloto judge-v1;
  - `configs/judge_groq_full.toml`: corrida completa con 1536, abortada por OTPM;
  - `configs/judge_groq_otpm.toml`: **evaluación definitiva**.
- **Tests:** `tests/test_faith_judge_run.py` (48, todos offline).

**Reproducción de la evaluación definitiva** (la segunda línea consume API):

```
rag-lab faith-judge-select --full    # recrea data/stage3/judge_full_selection.json (debe dar cases_sha256 9fffef23…)
rag-lab faith-judge --config configs/judge_groq_otpm.toml --selection data/stage3/judge_full_selection.json
rag-lab faith-judge-compare --run runs/stage3/judge/judge-v1-otpm_qwen3.8-27b \
  --selection data/stage3/judge_full_selection.json \
  --pilot runs/stage3/judge/smoke_qwen3.8-27b --pilot runs/stage3/judge/full_qwen3.8-27b
```

El último `--pilot` necesita las predicciones locales del piloto parcial, que no se versionan.

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

## Límite OTPM y configuración `judge-v1-otpm` (2026-11-17)

**Piloto de judge-v1** (`max_completion_tokens = 1536`), conservado sin mezclar:
- El smoke: 8 casos.
- `full_qwen3.8-27b`: J01–J08 salieron de la caché y J09–J11 son nuevos.
- En J12, Groq respondió HTTP 429 *"Request too large … on output tokens per minute (OTPM): Limit 1000, Requested 1203"*. No vino Retry-After ni había reintentos, así que la corrida se detuvo.
- Las predicciones de esa corrida parcial **no se versionan** (`.gitignore`): el mensaje del proveedor contiene el identificador de la organización. El archivo local no se modificó y su hash coincide con el manifiesto (`7047b7c1…`).
- El juez ahora enmascara `org_…` en los errores que guarda.

**`configs/judge_groq_otpm.toml`** cambia solo `max_completion_tokens = 640` y el ritmo (`min_interval_s = 65`). El modelo, el prompt `judge-v1`, el esquema estricto, `temperature = 0`, `seed = 7` e `include_reasoning = false` no cambian.
- Las claves de caché difieren de las del piloto, así que no se reutiliza nada.
- Una salida truncada (`finish_reason = length`) cuenta como `format_error` y detiene la corrida.
- Las predicciones se escriben además de forma incremental en `predictions.progress.jsonl`.

## Evaluación completa: judge-v1-otpm, 47 casos

- **Selección:** `data/stage3/judge_full_selection.json` (`cases_sha256 = 9fffef23…`).
  - Incluye las 30 afirmaciones originales aceptadas y las 17 perturbaciones confirmadas, que son controles **sintéticos**.
  - Excluye las 4 perturbaciones reservadas sin revisión humana.
- **Corrida** `runs/stage3/judge/judge-v1-otpm_qwen3.8-27b/`:
  - 47 solicitudes y 47 respuestas `ok`, con `finish_reason = stop` en todas;
  - 0 errores de API o de formato y 0 aciertos de caché;
  - 84.698 tokens contabilizados: 77.343 de prompt y 7.355 de salida, con 0 de razonamiento;
  - salida de 103 a 254 tokens por caso;
  - latencia media de 1,33 s (máxima 3,51 s);
  - `predictions_sha256 = 73a6613c…`.
- **Comparación:** `reports/judge_judge-v1-otpm_qwen3.8-27b_comparison.json`, calculada después de guardar las predicciones y sin modificarlas.

| Grupo | Campo | n | Acuerdo | IC Wilson 95% | Kappa | Juez supported / humano no |
|---|---|---|---|---|---|---|
| Originales | `label_cited` | 30 | 28 | [0,79; 0,98] | 0,57 | J02 (1 de 3) |
| Originales | `label_context` | 30 | 29 | [0,83; 0,99] | 0,00 (*) | J02 (1 de 1) |
| Perturbaciones sintéticas | ambos | 17 | 16 | [0,73; 0,99] | no aplica (**) | J46 (1 de 17) |

(*) El juez dijo `supported` en las 30 y el humano en 29: la kappa no informa.
(**) La referencia tiene una sola clase (`unsupported`).
La kappa global (0,88 / 0,91) está inflada por mezclar originales con controles sintéticos de clase opuesta; no se usa como confiabilidad.

**Matrices de confusión** (filas: humano; columnas: juez), sobre los 47 casos:
- `label_cited`:
  - supported → supported ×27;
  - partially → partially ×1, supported ×1, `judge_unverifiable` ×1;
  - unsupported → unsupported ×16, supported ×1.
- `label_context`:
  - supported → supported ×29;
  - partially → supported ×1;
  - unsupported → unsupported ×16, supported ×1.

**Desacuerdos:**
- **J02 (e28-c1), error semántico en ambas etiquetas:** la misma generalización del smoke ("a un plan superior (por ejemplo, Pro)", cuando S3 solo documenta Starter → Pro y Pro → Pro Plus). Se repitió con 640 tokens.
- **J12 (e05-c1), `citation_error` en `label_cited`:**
  - La etiqueta cruda del juez fue `partially_supported`, la misma que la humana.
  - Su única cita es de S3, que no está entre los fragmentos citados de la respuesta (solo S1), así que el verificador la declara `judge_unverifiable`.
  - En `label_context` coincide (`supported`).
- **J46 (e28-c2-p-negation), control sintético, error semántico en ambas:**
  - El juez etiquetó `supported` una negación falsa.
  - Su propio razonamiento concluye que la afirmación "es falsa según los documentos". El modelo emite las etiquetas **antes** del razonamiento (orden de claves: evidence, labels, rationale), así que el texto no las fundamenta.
  - Es la misma respuesta (e28) que J02.

**Por subtipo** (`label_cited`; en originales los subtipos son humanos y se superponen):

| Subtipo | Acuerdo |
|---|---|
| numeric | 17/18 |
| derived | 7/8 |
| multi_hop | 10/12 |
| negation | 4/4 |
| version | 4/4 |
| extractive | 3/3 |
| sintéticas: number | 6/6 |
| sintéticas: unit | 4/4 |
| sintéticas: negation | 6/7 |

Los n por subtipo son demasiado chicos para comparar subtipos.

**Estabilidad frente al piloto judge-v1** (control aparte, sin entrar en los agregados): en los 11 casos con respuesta en ambas configuraciones, las etiquetas finales son idénticas (11/11 en cada campo).

**Razonamientos de 496 caracteres:** 4 razonamientos (J01, J06, J12 y J46) terminan exactamente en 496 caracteres, cortados a mitad de palabra. El detalle está en "Auditoría de cierre". Las etiquetas se emiten antes del razonamiento, así que el corte no las afecta, pero el razonamiento queda incompleto.

**Limitaciones:**
- n = 47, con selección no aleatoria: todas las afirmaciones salen de una sola corrida de generación.
- Solo hay 3 parcialmente respaldadas y ninguna original sin respaldo. El caso que más importa (`supported` cuando no lo está) tiene muy poca muestra: 1 de 3 parciales y 1 de 17 controles.
- Las perturbaciones dependen de sus afirmaciones originales: comparten la respuesta y el contexto, y cambian un solo dato.
- Una cita literal válida no prueba faithfulness: J46 trae dos citas válidas y la etiqueta es incorrecta.
- No hay perturbaciones de versión (reservadas).
- Estos resultados **no** estiman la confiabilidad general del juez.

## Auditoría de cierre (offline, sin llamadas a Groq)

### Separación de corridas y cambio operativo 1536 → 640

| Corrida | `max_completion_tokens` | Casos | Rol |
|---|---|---|---|
| `smoke_qwen3.8-27b` | 1536 | 8 | piloto judge-v1 |
| `full_qwen3.8-27b` | 1536 | 11 `ok` (8 de la caché del smoke y 3 nuevos), 1 con 429 y 35 sin enviar | piloto judge-v1, abortado |
| `judge-v1-otpm_qwen3.8-27b` | 640 | 47 `ok` | **evaluación definitiva** |

- El cambio a 640 fue **operativo**: Groq rechazó la solicitud por el límite de salida por minuto (OTPM 1000). No se ajustó nada para mejorar el acuerdo.
- Las salidas observadas usan como máximo 254 tokens, y ninguna respuesta terminó por longitud.
- Los agregados usan solo las 47 predicciones definitivas (`73a6613c…`). El piloto entra únicamente en el control de estabilidad: 11 casos únicos, con etiquetas idénticas en 11/11. El texto crudo es idéntico en 8; en J04, J08 y J11 cambia la redacción pero no las etiquetas, pese a `seed = 7`.
- Del piloto parcial se versiona el manifiesto. Sus predicciones quedan solo en local, porque contienen el identificador de la organización del proveedor; su sha256 está en el manifiesto.

### El juez no se optimizó

`judge-v1` (prompt y esquema) es el de la Etapa 3A. Después de observar J02 en el smoke, y J12 y J46 en la evaluación completa, no se cambiaron el prompt, el esquema, el verificador, las etiquetas ni la selección. Los 47 casos se fijaron antes de ejecutar.

### Los 17 negativos son sintéticos

Las 17 perturbaciones son controles construidos cambiando un solo dato (número, unidad o negación) de afirmaciones originales que las personas etiquetaron `supported`.
- No son observaciones independientes: comparten pregunta, respuesta y contexto con su original. Algunas comparten respuesta entre sí; J46 y J02, por ejemplo, salen de la misma respuesta e28.
- Su acuerdo (16/17) mide si el juez detecta contradicciones de un solo dato, no su desempeño ante errores reales del generador.
- No hay originales `unsupported` en el conjunto.

### Estudio de caso J02 (e28-c1): generalización

- **Afirmación:** "El cambio de una cuenta Starter a un plan superior (por ejemplo, Pro) se aplica de inmediato."
- **S3** dice solo "Un cambio de Starter a Pro, o de Pro a Pro Plus, se aplica de inmediato."
- **Referencia humana:** `partially_supported` en ambas etiquetas. "Plan superior" generaliza más allá de lo documentado.
- **Juez:** `supported` en ambas, con cita válida, tanto en el smoke (1536) como en la evaluación definitiva (640).
- `judge-v1` no tiene una regla explícita para generalizaciones.

### Estudio de caso J12 (e05-c1): respaldo fuera de lo citado

- **Afirmación:** "8 usuarios de la cuenta exceden lo incluido en el plan Pro."
  - La respuesta cita solo S1.
  - El dato "Pro incluye 10 usuarios" está en S3, que no fue citado.
  - El 18 viene de la pregunta.
- **Humano:** `partially_supported` (citado) y `supported` (contexto).
- **Juez:** etiquetas crudas `partially_supported` / `supported`, ambas coincidentes con el humano.
  - Su única evidencia es una cita literal de S3.
  - Como S3 no es un fragmento citado, el verificador convierte `label_cited` en `judge_unverifiable`: una etiqueta de respaldo exige una cita válida de un fragmento citado.
- **Se cuenta como desacuerdo** (`citation_error`), no como acuerdo, aunque la etiqueta cruda coincidía.

### Estudio de caso J46 (e28-c2-p-negation): etiqueta contradicha por su propio razonamiento

Verificado offline:
- La selección (J46 → `e28-c2-p-negation`, tipo `perturbation`), la predicción (`source_id`, `answer_id` y `prompt_sha256` recalculado) y la revisión humana (`si`) corresponden al mismo caso.
- El prompt contiene el texto **perturbado**: "Cambiar a un plan superior **no** permite a la cuenta Starter seguir emitiendo facturas en el mismo ciclo."
  - El texto original aparece 0 veces en el prompt, así que no hay confusión entre `original_text` y `perturbed_text`.
  - La original (e28-c2, sin "no") está etiquetada `supported` / `supported` con S1 y S3.
- **Evidencia del juez:** dos citas literales válidas.
  - S1: la emisión "queda bloqueada hasta el inicio del próximo ciclo … o hasta que la cuenta pase a un plan superior".
  - S3: el cambio "se aplica de inmediato".
  - Juntas contradicen la afirmación perturbada.
- **Etiquetas:** `supported` / `supported`, emitidas **antes** del razonamiento (orden de claves: `evidence`, `label_cited`, `label_context`, `rationale`).
- **El razonamiento contradice la etiqueta:** concluye que la afirmación "es falsa según los documentos", empieza a revisar ("Sin embargo, revisando la lógica: La afirmación dice 'no'") y se corta en 496 caracteres.
- La predicción no se modificó: cuenta como error semántico en ambas etiquetas.
- Muestra que una cita literal válida no prueba faithfulness.

### Corte de los razonamientos en 496 caracteres

**Hechos verificados:**
- Los razonamientos de J01, J06, J12 y J46 miden exactamente 496 caracteres (500, 511, 503 y 504 bytes UTF-8) y terminan a mitad de palabra: "premí", "erróne", "técñ", "dice 'no'".
- Ningún otro razonamiento supera 470 caracteres. Ninguna de las 79 citas de las 66 respuestas supera 198.
- **No hay recorte local:**
  - El JUDGE_SCHEMA no define `maxLength` en ningún campo, y el prompt no fija un largo.
  - El cliente guarda `choice.message.content` sin procesarlo.
  - El único recorte local (`[:500]`) aplica a mensajes de error, no a respuestas.
  - `raw_content` en las predicciones, la caché y el razonamiento parseado son idénticos.
- **Llegó así de Groq:** el JSON recibido es válido y está cerrado después del corte, con `finish_reason = stop`. Un recorte local del contenido habría roto el JSON.
- **No depende de `max_completion_tokens`:** J01 y J06 tienen respuestas crudas idénticas byte a byte con 1536 y con 640, y usan entre 186 y 254 tokens de salida.

**Causa no determinable offline.** Es compatible con un tope de longitud de cadena del lado del proveedor o del modelo en la decodificación con esquema estricto, pero no hay documentación ni encabezado que lo confirme. Queda como incertidumbre. Las etiquetas no se ven afectadas, porque se emiten antes del razonamiento.

### Verificación de métricas (recalculadas independientemente desde las predicciones)

- **`label_cited`:**
  - originales: n = 30, 28 acuerdos; partially → partially, supported y `judge_unverifiable`; supported → supported ×27;
  - sintéticas: n = 17, 16 acuerdos; unsupported → unsupported ×16 y supported ×1.
- **`label_context`:**
  - originales: n = 30, 29 acuerdos; partially → supported ×1;
  - sintéticas: n = 17, 16 acuerdos.
- **Denominadores:** los 47 casos tienen referencia y respuesta `ok`.
- `judge_unverifiable` entra en la matriz como columna propia y cuenta como desacuerdo (J12).
- **Hashes:**

| Archivo | sha256 |
|---|---|
| selección | `9fffef23…` (cases) / `ebe6c2fa…` (archivo) |
| predicciones | `73a6613c…` |
| etiquetas humanas | `500df4f8…` |
| revisión de perturbaciones | `734ddb7b…` |
