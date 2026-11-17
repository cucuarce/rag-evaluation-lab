# Guía de anotación — Etapa 3A

Tiempo estimado: entre 60 y 90 minutos para 30 afirmaciones, más unos 15 minutos para las perturbaciones.

## Archivos

| Archivo | Uso |
|---|---|
| `data/stage3/annotation/annotation_packet.md` | **Leer.** Para cada respuesta muestra la pregunta, la respuesta, las afirmaciones y **todos** los fragmentos del contexto, con su vigencia; los citados están marcados con **CITADO**. Se ve bien en la vista previa de Markdown de VS Code. |
| `data/stage3/annotation/annotation_sheet.csv` | **Completar.** Una fila por afirmación. Usa `;` como separador y UTF-8; se abre directamente en Excel. |
| `data/stage3/annotation/perturbation_review.csv` | **Completar después**, en una segunda pasada (§5). |

Las planillas son **ciegas**: no muestran la corrida (A/B), métricas, la respuesta de referencia ni los hechos esperados. No consultes `data/eval/labels.jsonl`, `claims_proposed.jsonl` (`selection_reason`), `docs/stage2_report.md` ni `docs/faithfulness.md` §3 mientras anotás: lo que se mide es el **respaldo documental**, no si la respuesta es correcta.

## 1. Procedimiento

1. Abrí el paquete y la planilla en paralelo. Los grupos del paquete siguen el mismo orden que las filas de la planilla.
2. En cada afirmación, leé la pregunta y la afirmación, y después **solo los fragmentos citados**. Decidí `label_cited`.
3. Después leé el resto de los fragmentos del contexto y decidí `label_context`.
4. Completá los demás campos y guardá. Podés hacerlo en varias sesiones: las filas vacías se importan como pendientes.
5. Importá:
   ```
   uv run rag-lab faith-import data/stage3/annotation/annotation_sheet.csv --round 1
   ```
   La importación valida todo. Si hay un solo error, **no importa nada** y lista cada problema con su `claim_id`. El resultado va a `data/stage3/human_labels_round1.jsonl`.

`rag-lab faith-prepare` **no sobrescribe** una planilla editada: se niega salvo que uses `--force`.

## 2. Columnas a completar

| Columna | Valores | Cuándo |
|---|---|---|
| `split_decision` | `aceptar` / `editar` / `rechazar` | Siempre. `editar` si la afirmación propuesta no representa bien lo que dice la respuesta o mezcla dos hechos que convendría separar. `rechazar` si no es verificable (opinión, relleno) o no corresponde a la respuesta. |
| `claim_text_final` | texto | Solo con `editar`: la versión corregida. Etiquetá esa versión. |
| `label_cited` | `supported` / `partially_supported` / `unsupported` / `insufficient_context` | Salvo con `rechazar`. |
| `label_context` | ídem | Salvo con `rechazar`. No puede ser más débil que `label_cited`. |
| `support_cite_ids` | p. ej. `S1` o `S1,S3` | Fragmentos que respaldan la afirmación, aunque sea parcialmente. Es obligatorio si `label_cited` es supported o partially_supported, y en ese caso tiene que incluir al menos un fragmento citado. |
| `version_issue` | `si` / `no` | `si` si el respaldo depende de usar la versión correcta o incorrecta de una política. |
| `subtypes_final` | opcional | Solo si los subtipos propuestos están mal, por ejemplo `numeric,derived`. Valores posibles: extractive, numeric, negation, derived, version, multi_hop. |
| `missing_premise` | texto | Con `partially_supported`: qué falta. Por ejemplo, "cuántos usuarios incluye Pro". |
| `notes` | texto | Dudas, casos límite o desacuerdos con la regla. Son muy útiles. |
| `annotator` | iniciales | Obligatorio. |

Mayúsculas y tildes se toleran (`Sí` = `si`). Cualquier otro valor se rechaza.

## 3. Cómo decidir la etiqueta

Hacete estas preguntas **en orden**:

1. ¿Los fragmentos tratan el tema de la afirmación? Si no → `insufficient_context`.
2. ¿Algún fragmento la contradice (otro número, otra unidad, la polaridad opuesta, otra versión cuando la pregunta es sobre lo vigente)? Si es así → `unsupported`.
3. ¿Cada parte de la afirmación está dicha en los fragmentos, o sale de una cuenta o paso trivial con premisas que están en los fragmentos o en la pregunta? Si es así → `supported`.
4. ¿Una parte sí y otra no, o falta una premisa? → `partially_supported`.
5. ¿Agrega algo que los fragmentos no dicen, aunque hablen del tema? → `unsupported`.

### Reglas, con ejemplos ilustrativos (no son de la muestra)

- **Números y unidades.** Si el fragmento dice "se responde en 2 días hábiles", entonces:
  - "se responde en 2 días hábiles" → supported;
  - "en 2 días" → partially_supported, porque falta "hábiles", que cambia el plazo;
  - "en 2 días corridos" → unsupported.
- **Negaciones.** Si el fragmento dice "las devoluciones no se aceptan", "no se aceptan devoluciones" → supported. Si el fragmento solo dice "las devoluciones se tramitan por ticket", "no se aceptan devoluciones por email" → unsupported: la falta de mención no prueba la negación. Una negación que se deduce de una lista ("disponible en los planes X e Y") es una inferencia: → supported solo si la lista es claramente exhaustiva; si no, partially_supported.
- **Cuentas.** Si la pregunta da "12 licencias", el fragmento 1 dice "incluye 5" y el fragmento 2 dice "cada adicional cuesta USD 3", entonces "pagará USD 21" → supported **contra el contexto**. Si la respuesta citó solo el fragmento 2 → `label_cited` partially_supported, con `missing_premise` = "licencias incluidas".
- **Datos de la pregunta.** Lo que la pregunta afirma cuenta como dado. Un adjetivo que solo aparece en la pregunta ("gratuito") no necesita respaldo en el fragmento si la afirmación lo usa para referirse a lo mismo. Si agrega un hecho nuevo, sí lo necesita.
- **Versiones.** Revisá el estado de cada fragmento (VIGENTE o HISTÓRICO) y el `temporal_scope` de la planilla:
  - con `current`, un dato que solo respalda un fragmento HISTÓRICO → unsupported, con `version_issue = si`;
  - con `historical_anchored`, el respaldo tiene que venir de la versión vigente en ese momento.
- **Generalizaciones.** Si el fragmento dice "el cambio de A a B o de B a C es inmediato", entonces "cualquier cambio a un plan superior es inmediato" → partially_supported.
- **Propósitos y consecuencias.** "X sirve para Y" o "lo que permite Z" → supported solo si el fragmento lo dice o es inmediato. Si es una deducción razonable pero no escrita → partially_supported. Anotá tu criterio en `notes`.
- **Ante la duda** entre dos etiquetas, elegí la **más estricta** y explicalo en `notes`. Una etiqueta generosa es el error que más daña la evaluación del juez.

## 4. Lo que NO hay que evaluar

- Si la respuesta es correcta o completa. Una omisión no es una afirmación: si la respuesta no menciona un dato, no hay nada que etiquetar.
- Si cita "bien" en el sentido de la Etapa 2. Que una cita sea válida no implica respaldo.
- El estilo, la redacción o el orden.

## 5. Revisión de perturbaciones (segunda pasada, después de la planilla principal)

`perturbation_review.csv` tiene 21 versiones alteradas de las afirmaciones. Cada fila trae el cambio y la etiqueta que se *espera* que reciba la versión alterada. Para cada una:

- `human_confirms_expected` = `si` si la versión alterada debería recibir esa etiqueta. Por ejemplo, al cambiar "30 días" por "60 días", lo esperable es `unsupported`.
- `human_confirms_expected` = `no` si la alteración no cambia el hecho, es ambigua, queda agramatical al punto de no ser evaluable, o la expectativa es incorrecta. Explicá por qué en `notes`.
- En las filas `requires_review`, leé la columna `reasons`. En las de tipo versión, `expected_label_context` dice "a decidir": escribí en `notes` la etiqueta que corresponde.

Importá con:
```
uv run rag-lab faith-import data/stage3/annotation/perturbation_review.csv --kind perturbations
```

Una perturbación se usa como control solo si se cumplen las tres condiciones:
1. la confirmaste;
2. aceptaste la afirmación original sin editarla;
3. la etiquetaste `supported`.

## 6. Segunda ronda (opcional, recomendada)

Para medir tu propia consistencia, al menos una semana después:
1. Recuperá la planilla en blanco del commit de la Etapa 3A:
   ```
   git show HEAD~0:data/stage3/annotation/annotation_sheet.csv > data/stage3/annotation/annotation_sheet_round2.csv
   ```
   Reemplazá `HEAD~0` por el commit de la Etapa 3A si ya hiciste otros commits.
2. Etiquetá de nuevo sin mirar la primera ronda. Alcanza con un 25%, unas 8 afirmaciones; las filas vacías quedan como pendientes.
3. Importá con `uv run rag-lab faith-import data/stage3/annotation/annotation_sheet_round2.csv --round 2`.
4. Compará:
   ```
   uv run rag-lab faith-agreement --reference data/stage3/human_labels_round1.jsonl --evaluated data/stage3/human_labels_round2.jsonl
   ```
