# Normalización léxica v2 (Etapa 3A)

Código: `src/rag_lab/evaluation/lexical_v2.py`. Comando:

```
uv run rag-lab rescore-lexical runs/eval/A_dense_k5/gen/groq_gpt-oss-120b runs/eval/B_hybrid_k5/gen/groq_gpt-oss-120b
```

Escribe `reports/lexical_v2_<generación>_<corrida>.json`. No escribe nada en `runs/`.

## Por qué existe y qué no es

La v2 se diseñó **después de observar** los falsos negativos de la Etapa 2:
- en e29 la respuesta escribe "25 %" con un espacio fino U+202F;
- en e31 escribe "HMAC‑SHA256" y "Kestrel‑Signature" con un guion U+2011.

Es una corrección de la **medición**, no del sistema. Al estar hecha a la medida de casos conocidos, no es una validación ciega.

- La **v1 sigue siendo la métrica oficial** de la Etapa 2. Su código (`gen_metrics.normalize_text` y `fact_present`) no se modificó.
- `gen_summary.json` y `gen_per_question.jsonl` no se tocan.
- v1 y v2 se publican siempre en columnas separadas (`*_v1` y `*_v2`).
- El comando recalcula la v1 y verifica que coincida exactamente con lo guardado (`v1_reproduces_saved`). Si no coincide, falla.

## Pasos

Se aplican antes de la normalización v1 (sin acentos, minúsculas, números escritos a dígitos y espacios colapsados):

1. Unicode NFKC.
2. Guiones tipográficos a `-`: U+2010–2015, U+2212, U+FE58, U+FE63 y U+FF0D.
3. Espacios especiales a un espacio común: U+00A0, U+2007, U+2009, U+200A, U+202F, U+205F y U+3000. Los caracteres de ancho cero (U+200B–200D, U+2060, U+FEFF) se eliminan.
4. Comillas tipográficas y angulares a comillas ASCII.
5. `N %` pasa a `N%`.

Los límites de palabra son los mismos que en la v1.

**No incluye** sinónimos, morfología ni paráfrasis. Por ejemplo, "no tienen SLA contractual" y "no tiene SLA contractual" siguen sin coincidir (e27). Las omisiones reales tampoco cambian (e04: Retry-After).

## Resultados sobre el benchmark de la Etapa 2

Las métricas se calculan sobre las preguntas respondibles que el sistema respondió, con el mismo denominador que en `gen_summary.json`.

| | A v1 | A v2 | B v1 | B v2 |
|---|---|---|---|---|
| Cobertura de `required_facts` | 0,8793 | 0,9483 | 0,9107 | 0,9464 |
| Con todos los `required_facts` | 0,8621 | 0,9310 | 0,8929 | 0,9286 |
| Con algún `forbidden_fact` (n = 9) | 0 | 0 | 0 | 0 |
| Preguntas que cambian | | e29, e31 | | e31 |

Con la v2, la diferencia de cobertura entre A y B (antes 0,8793 frente a 0,9107) desaparece y se invierte levemente. Es coherente con la revisión manual de la Etapa 2, que atribuyó la ventaja de B a un falso negativo en e29 (A). Con n = 28–29 respuestas, esta diferencia tampoco es interpretable.

## Limitación detectada en la v1 (sin efecto en la Etapa 2)

`docs/generation.md` dice que `"5"` no coincide con `"5,5"`. Esa afirmación es **incorrecta**:
- el límite derecho evita coincidir con el `5` inicial de "5,5";
- pero el límite izquierdo no excluye la parte decimal de otro número, así que "5" sí coincide con el `5` final de "5,5" o de "2,5".

La v2 conserva esos mismos límites a propósito, para que v1 y v2 difieran solo en la normalización Unicode.

Se verificó que **ninguna** de las 104 comprobaciones de hechos de la Etapa 2 cambia con un límite más estricto (`tests/test_lexical_v2.py::test_known_limitation_decimal_tail_and_zero_impact_on_stage2`). La corrección queda propuesta para una versión futura, que tendría que volver a medir v1 y v2 por separado.

## Tests

`tests/test_lexical_v2.py` cubre:
- variantes Unicode;
- límites (`5` frente a `15`, `USD 99` frente a `USD 99,9`);
- que no haya paráfrasis;
- monotonía en datos reales: todo hecho que la v1 encuentra en las respuestas de la Etapa 2, la v2 también lo encuentra. No es una garantía general: borrar un carácter de ancho cero podría unir dos palabras;
- que la v1 recalculada reproduce lo guardado y que no se escribe en `runs/`.
