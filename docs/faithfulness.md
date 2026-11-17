# Etapa 3A: faithfulness por afirmación (offline)

Proceso reproducible para evaluar si cada afirmación de una respuesta del RAG está respaldada por los fragmentos que citó y por el contexto completo que recibió el generador.

En la Etapa 3A **no se llama a ningún modelo**. Quedan listos:
- los datos;
- la planilla de anotación humana;
- el contrato y el validador del futuro juez;
- las métricas de acuerdo;
- los controles con perturbaciones.

Ningún resultado de juez de este repositorio es real: los tests usan salidas simuladas escritas a mano.

Código: `src/rag_lab/faithfulness/`. Guía para anotar: [`annotation_guide.md`](annotation_guide.md).

## 1. Flujo

```
runs/eval/{A,B}/gen/groq_gpt-oss-120b/generations.jsonl   (Etapa 2, sin cambios)
        │  rag-lab faith-prepare (sin etiquetas, sin API)
        ▼
data/stage3/answers.jsonl            54 respuestas únicas + fragmentos + ocurrencias A/B
data/stage3/claims_proposed.jsonl    30 afirmaciones propuestas (status proposed_unreviewed)
data/stage3/perturbations.jsonl      55 perturbaciones generadas; 21 seleccionadas
data/stage3/annotation/              planilla ciega + paquete legible + revisión de perturbaciones
data/stage3/stage3a_manifest.json    procedencia, hashes, conteos, dimensionamiento del juez
        │  anotación humana (planilla)  →  rag-lab faith-import
        ▼
data/stage3/human_labels_round1.jsonl         (etiquetas humanas, archivo propio)
        │  Etapa 3B (no implementada): juez real → salida cruda → judge_verify
        ▼
runs/stage3/judge/<nombre>/...                (salidas del juez, separadas de las humanas)
        │  rag-lab faith-agreement --reference humano --evaluated juez
        ▼
reports/faith_agreement_*.json
```

## 2. Respuestas únicas y trazabilidad

Una **respuesta única** es la combinación de qid, texto, fragmentos citados y contexto completo, en orden.
- `answer_id` es sha256 de esa combinación, truncado a 16 caracteres.
- Si A y B produjeron lo mismo con el mismo contexto, es **una** respuesta con dos ocurrencias. Pasa en e02, e21 y e32.
- Si el texto coincide pero el contexto difiere, son respuestas distintas: el respaldo "en el contexto completo" puede cambiar.

| | n |
|---|---|
| Ocurrencias (respuestas emitidas: A 29 + B 28) | 57 |
| Respuestas únicas | 54 |
| Textos distintos | 42 |
| Compartidas por A y B | 3 (e02, e21, e32) |

Cada respuesta guarda:
- `occurrences` con la corrida, el directorio y el `prompt_sha256` de la generación original;
- el texto de cada fragmento, reconstruido con el mismo chunking determinístico del índice y verificado contra los offsets guardados.

Cada afirmación guarda `answer_id`, `qid` y `runs`. La cadena afirmación → respuesta → corrida se puede recorrer en ambos sentidos, y `tests/test_faith_annotation.py` la verifica.

## 3. Afirmaciones

Esquema de `claims_proposed.jsonl`:

```json
{"claim_id": "e05-c3", "answer_id": "ea636b1aa5f0e7cf", "qid": "e05", "runs": ["A_dense_k5"],
 "text": "El cliente pagará USD 96 por mes por los usuarios que exceden lo incluido en el plan Pro.",
 "answer_span": "Pagará USD 96 por mes por los usuarios que exceden lo incluido en el plan Pro",
 "subtypes": ["derived", "numeric", "multi_hop"],
 "proposed_by": "assistant (propuesta de división; no revisada por una persona)",
 "status": "proposed_unreviewed", "selection_reason": "..."}
```

- `claim_id` (`<qid>-c<n>`) es neutral: no revela la corrida, para que la planilla siga siendo ciega. La corrida está en `runs`.
- `answer_span` es un fragmento **literal** de la respuesta y se valida.
- `text` es la proposición en forma autocontenida.
- `subtypes` admite estos valores:
  - `extractive`: copiada o casi copiada de un fragmento;
  - `numeric`: contiene un número o una unidad;
  - `negation`;
  - `derived`: cuenta o inferencia;
  - `version`: depende de qué versión de una política aplica;
  - `multi_hop`: requiere combinar fragmentos.
- La división en afirmaciones es una **propuesta del asistente**, no una etiqueta. Por eso las afirmaciones no tienen etiqueta. La persona puede aceptarla, editarla o rechazarla en la planilla.
- `selection_reason` explica por qué se eligió cada una. **No** aparece en la planilla, para no sesgar a quien anota.

### Muestra inicial (30 afirmaciones, 20 respuestas, 18 preguntas)

Las afirmaciones se eligieron a mano para cubrir tipos y dificultades, no al azar. No representan la distribución del benchmark.

| Subtipo | n | Ejemplos |
|---|---|---|
| numeric | 18 | e01, e18, e29, e39 |
| multi_hop | 12 | e05, e14, e19, e28, e32, e36 |
| derived | 8 | e05 (cuenta), e19 y e28 (inferencias), e31 (propósito) |
| negation | 4 | e21, e27 (dos afirmaciones), e36 |
| version | 4 | e06 y e39 (pregunta vigente con la versión anterior en el contexto), e10 (histórica), e21 |
| extractive | 3 | e04, e21, e31 |

Incluye a propósito:
- **controles fáciles** (e01, e04);
- **casos difíciles**:
  - e05: la cuenta es correcta, pero A no citó la premisa de usuarios incluidos;
  - e19 y e28: inferencias;
  - e31: el propósito de la verificación no está escrito en el fragmento;
  - e36: negación que se deduce de una lista de planes, más un requisito formulado con un solo plan;
  - e23: "gratuito" viene de la pregunta;
  - e27: singular y plural;
- **contraste A/B** de la misma pregunta: e05 y e36.

Limitación: las respuestas reales de la Etapa 2 casi no tienen afirmaciones abiertamente falsas. Los controles negativos los aportan las perturbaciones (§7).

## 4. Etiquetas

Cada afirmación se evalúa **dos veces**:

| Campo | Contra qué | Para qué |
|---|---|---|
| `label_cited` | solo los fragmentos que citó la respuesta | faithfulness de la cita |
| `label_context` | todos los fragmentos entregados al generador | groundedness |

Si una afirmación tiene `label_context` supported y `label_cited` no, el problema es de **cita**, no una alucinación. Es el patrón esperable en e05 de A.

| Etiqueta | Definición |
|---|---|
| `supported` | Todo el contenido está dicho en los fragmentos, o se deduce con una operación explícita y trivial cuyos operandos están todos en los fragmentos o en la pregunta. |
| `partially_supported` | Una parte está respaldada y otra no, o falta una premisa necesaria para la deducción. |
| `unsupported` | Los fragmentos la contradicen, o agrega información que no contienen aunque traten el tema. |
| `insufficient_context` | Los fragmentos no tratan el tema: no permiten ni confirmar ni contradecir. |
| `judge_unverifiable` | **Solo la asigna el verificador**, nunca una persona ni el juez (§6). |

Coherencia: lo citado es parte del contexto, así que `label_cited` no puede ser más fuerte que `label_context`. La importación lo rechaza.

### Reglas

1. **Números y unidades:** tienen que coincidir valor y unidad. "5 días hábiles" no es "5 días corridos", y "por mes" no es "por año".
2. **Negaciones:** una negación ("no se devuelve") necesita un fragmento que la afirme. Que falte una mención positiva no alcanza. Si se deduce de una enumeración cerrada ("disponible en Pro Plus y Enterprise"), es una inferencia: `supported` solo si la lista es explícitamente exhaustiva; si no, `partially_supported`.
3. **Inferencias y cuentas:** `supported` solo si todas las premisas están en los fragmentos o en la pregunta y el paso es explícito. Si falta una premisa, `partially_supported`, aunque el resultado sea correcto.
4. **Datos de la pregunta:** lo que la pregunta establece (por ejemplo "18 usuarios activos") cuenta como dado.
5. **Versiones:** si la pregunta es sobre lo vigente, un dato respaldado solo por un fragmento HISTÓRICO es `unsupported` (y `version_issue = si`). Si la pregunta es histórica, el respaldo tiene que venir de la versión vigente en ese período.
6. **Afirmaciones compuestas:** si se pueden dividir, se dividen (`split_decision = editar` o una nota). Si no, y solo una parte está respaldada, son `partially_supported`.
7. **Generalizaciones:** una afirmación más general que el fragmento ("cualquier plan superior" cuando el fragmento nombra dos cambios concretos) es `partially_supported`.
8. **Cita válida no es respaldo:** que la respuesta cite un fragmento entregado (la validez de citas de la Etapa 2) no dice nada sobre si ese fragmento respalda la afirmación.

## 5. Contrato del juez (para la Etapa 3B)

Código en `judge_prompt.py`:
- `prompt_version = judge-v1`;
- hash del template y del esquema en `stage3a_manifest.json`;
- una solicitud por respuesta, que cubre todas sus afirmaciones;
- salida estructurada estricta (`JUDGE_SCHEMA`).

```json
{"claims": [{"claim_id": "...", "label_cited": "<enum>", "label_context": "<enum>",
             "evidence": [{"cite_id": "S1", "quote": "<texto literal del fragmento>"}],
             "rationale": "..."}]}
```

**Qué recibe el juez:**
- la pregunta;
- el alcance temporal (calculado en la Etapa 2 solo a partir del texto de la pregunta);
- la fecha de referencia;
- el texto de las afirmaciones;
- los fragmentos, con documento, versión y estado VIGENTE/HISTÓRICO;
- cuáles fueron citados.

**Qué no recibe nunca:**
- `labels.jsonl`, `reference_answer`, `required_facts`, `forbidden_facts`, notas ni evidencia gold;
- métricas de la Etapa 2;
- etiquetas humanas;
- la corrida (A/B);
- los subtipos propuestos.

`tests/test_faith_judge.py` lo verifica de tres formas:
- revisa la firma de la función;
- comprueba con un análisis del código fuente que ningún módulo de `faithfulness/` importa etiquetas;
- construye los 20 prompts reales y busca datos de referencia.

**Instrucciones incrustadas.** Todo texto no confiable (pregunta, afirmaciones, fragmentos) va entre marcadores `<<<... nonce>>>`.
- El nonce es un hash del contenido.
- Si algún texto contiene `<<<`, `>>>` o el nonce, la construcción falla: el texto no puede cerrar su bloque.
- El prompt declara que ese material no es una instrucción.

Esto **reduce** el riesgo, pero no lo elimina. La defensa estructural es la verificación de §6: una instrucción incrustada no puede fabricar respaldo sin una cita literal que exista en el fragmento.

**Dimensionamiento**, sin ejecutar nada:
- 20 solicitudes para las 30 afirmaciones;
- unos 65K tokens según la regla conservadora de la Etapa 2: caracteres / 2,5 más 1024 tokens de salida por solicitud;
- el detalle está en `stage3a_manifest.json`.

## 6. Verificación de la salida del juez

Código en `judge_verify.py`. No confía en el juez:

1. **Formato:**
   - JSON con las claves exactas;
   - etiquetas dentro del enum;
   - evidencia con `cite_id` y `quote`.

   Si falla, se invalida la respuesta entera. No se repara.
2. **Cobertura:**
   - una entrada por `claim_id`;
   - los faltantes, extras y duplicados se registran (se usa el primero).
3. **Evidencia:**
   - `quote` tiene que ser un substring **exacto** del texto del fragmento `cite_id`, sin el encabezado;
   - el fragmento tiene que estar en el contexto;
   - la cita necesita al menos 8 caracteres no blancos.

   Un cambio de tilde o de espacio ya invalida la cita.
4. **Etiqueta final:** si el juez dice `supported` o `partially_supported` y no hay ninguna cita válida en el conjunto que corresponde, la etiqueta final es `judge_unverifiable` y cuenta como **no respaldada**. Los conjuntos son:
   - para `label_cited`, los fragmentos citados;
   - para `label_context`, cualquier fragmento del contexto.

   Se conserva también lo que dijo el juez (`judge_label_*`).
5. **Lo que el verificador no hace:**
   - no sube nunca una etiqueta a `supported` porque la cita exista;
   - no comprueba que la cita respalde la afirmación.

   Que la cita exista es condición **necesaria, no suficiente**. Si respalda o no la afirmación lo mide el acuerdo con la anotación humana.

## 7. Perturbaciones (controles negativos)

Código en `perturbations.py`. Se generan a partir de las afirmaciones propuestas:

| Tipo | Cambio | Comprobaciones automáticas |
|---|---|---|
| `number` | Un número presente en lo citado pasa a un valor ausente de todo el contexto. | Que el texto cambie, que el valor original esté en lo citado y que el nuevo no esté en el contexto. Se salta el límite inferior de rangos ("5 a 10"). |
| `negation` (remove) | "no se devuelve" → "se devuelve" | Que la negación esté escrita en lo citado; si no, `requires_review`. |
| `negation` (add) | "puede" → "no puede", "lo reintenta" → "no lo reintenta" | Que el verbo esté afirmado en lo citado. Una negación delante de "hasta" pasa a `requires_review` porque su alcance es ambiguo. |
| `unit` | días hábiles ↔ corridos, minutos ↔ horas, por mes → por año, días → meses | Que la frase "número + unidad" original esté en lo citado y la nueva no esté en el contexto. |
| `version` | Un valor reemplazado por el de la otra versión del documento en la misma sección (v3 ↔ v2) | Siempre `requires_review`: la etiqueta esperada en el contexto completo depende del alcance temporal. |

Estado de cada perturbación:
- `candidate`: las comprobaciones pasan;
- `requires_review`: hace falta juicio;
- `invalid`: no modifica el hecho evaluado.

Se generaron 55: 41 `candidate`, 12 `requires_review` y 2 `invalid`. Las dos inválidas son el "96 por mes" de e05: el 96 no está en ningún fragmento.

Una selección determinística y chica de **21** va a revisión humana: 2 de versión, 5 que quitan una negación, 6 numéricas, 4 de unidad y 4 que agregan una negación. El resto queda registrado con `selected = false`.

**Una perturbación no es una etiqueta de referencia.** Se usa como control solo si se cumplen las tres condiciones (`usable_perturbations`):
1. una persona confirmó la expectativa en `perturbation_review.csv`;
2. la afirmación original fue aceptada sin editar;
3. la persona la etiquetó `supported`.

## 8. Métricas de acuerdo

Código en `agreement.py`; comando `rag-lab faith-agreement --reference <humano> --evaluated <juez|otra persona>`. Calcula, por separado para `label_cited` y `label_context`:

- **Matriz de confusión:** filas = referencia humana (4 etiquetas); columnas = evaluado (4 etiquetas + `judge_unverifiable`).
- **Acuerdo observado,** con intervalo de Wilson al 95%.
- **Kappa de Cohen:**
  - en 4 clases y en binario (`supported` frente al resto);
  - solo si n ≥ 10 y hay más de una categoría; si no, `null` con el motivo.
- **Casos críticos, listados uno por uno:** el evaluado dice `supported` y la persona no. Es el error más peligroso de un juez. Incluye la tasa sobre las no respaldadas y su intervalo de Wilson.
- **El caso inverso:** el evaluado no dice `supported` y la persona sí.
- **Advertencia** en el reporte: con n < 100 el acuerdo **no demuestra** que el evaluador sea confiable. Con unas 30 afirmaciones, un acuerdo de 0,9 tiene un intervalo de Wilson de aproximadamente [0,74; 0,97].

## 9. Límites de la validación

- **Un solo anotador**, que además conoce el corpus, el benchmark y los errores de la Etapa 2. Una segunda ronda propia (`--round 2`, una semana después) mide su consistencia, pero no reemplaza a una segunda persona.
- **n chico:** 30 afirmaciones elegidas a mano. Sirve para probar el proceso y encontrar errores groseros del juez, no para estimar tasas con precisión ni para generalizar al benchmark.
- **La división en afirmaciones** la propuso el asistente y condiciona lo que se evalúa: un juez que divida distinto no es comparable.
- **Perturbaciones sintéticas:** son fáciles comparadas con los errores reales (cambian un solo token). Que el juez las detecte es necesario, pero no basta.
- **El juez no es la verdad.** Aunque el acuerdo resulte alto, las etiquetas humanas siguen siendo la referencia.
- **La verificación literal** puede rechazar respaldos legítimos si el juez parafrasea la cita. Eso aparece como `judge_unverifiable` y se cuenta en contra del juez, no a favor.
- **Las reglas de etiquetado** (inferencias, generalizaciones, negaciones por enumeración) son decisiones de diseño discutibles. Si la anotación muestra casos ambiguos, conviene ajustar la guía **antes** de correr el juez, no después.

## 10. Anotación humana, ronda 1 (cerrada)

Una sola persona (`h1`) anotó las 30 afirmaciones y revisó las 21 perturbaciones. No se llamó a ningún modelo.

### Afirmaciones

| Archivo | sha256 |
|---|---|
| `data/stage3/annotation/annotation_sheet_completed.csv` (planilla anotada) | `d2f85a70…5bb36` |
| `data/stage3/human_labels_round1.jsonl` (30 etiquetas importadas; `sheet_sha256` apunta a la planilla) | `500df4f8…f57c1` |

- Las 30 se aceptaron sin editar y ninguna se rechazó. En todas, `version_issue` es `no`.
- `label_cited`: 27 `supported` y 3 `partially_supported` (e05-c1, e05-c3, e28-c1).
- `label_context`: 29 `supported` y 1 `partially_supported` (e28-c1).
- No hay `unsupported` ni `insufficient_context`: la muestra real casi no tiene afirmaciones sin respaldo, así que los negativos dependen de las perturbaciones (§7, §9).

**Correcciones que pidió la persona antes de importar,** después de validar la planilla contra esta guía y el importador:
- completó `split_decision` y `version_issue`, que estaban vacíos en las 30 filas;
- en e05-c1 y e05-c3 cambió `label_cited` de `insufficient_context` a `partially_supported`. Lo citado (S1) trata el tema pero no trae la premisa "Pro incluye 10 usuarios": es la regla "Cuentas" de la guía;
- en e05-c1 cambió `support_cite_ids` de `S3` a `S1,S3`, porque una etiqueta `partially_supported` exige incluir un fragmento citado.

### Perturbaciones

| Archivo | sha256 |
|---|---|
| `data/stage3/annotation/perturbation_review.csv` (planilla revisada) | `ec57069d…34a3` |
| `data/stage3/perturbation_review.jsonl` (17 confirmaciones importadas) | `734ddb7b…53f2` |

- **17 confirmadas** (`human_confirms_expected = si`, con expectativa `unsupported` / `unsupported`): 7 de negación, 6 numéricas y 4 de unidad. Las 17 cumplen las tres condiciones de `usable_perturbations`.
- **4 reservadas**, que quedan vacías (pendientes) y no se importaron. El esquema solo admite `si` y `no`, y `no` significaría que la expectativa es incorrecta, así que los motivos se registran acá:

| Perturbación | Motivo |
|---|---|
| `e06-c1-p-version` | Reservada para una evaluación específica de versiones. |
| `e10-c1-p-version` | Reservada para una evaluación específica de versiones. |
| `e28-c1-p-negation` | La afirmación original tiene respaldo parcial (además, `usable_perturbations` la excluiría). |
| `e36-c1-p-negation` | El respaldo de la negación original es indirecto (se deduce de una lista de planes). |

Consecuencia: **ningún control confirmado prueba errores de versión.**

`rag-lab faith-prepare` no sobrescribe las planillas anotadas; solo lo haría con `--force`. Las versiones en blanco siguen en el commit de la Etapa 3A (`a222dbb`).
