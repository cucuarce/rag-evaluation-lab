# Etapa 4A: dashboard local de resultados

Dashboard Streamlit de **solo lectura**. Presenta los resultados congelados de las Etapas 1–3B. No llama a Groq ni a ningún otro modelo, no escribe archivos y no recalcula resultados: cada número sale tal cual de un reporte o de una predicción versionada.

## Ejecución

```bash
uv sync --group dashboard          # instala streamlit (grupo opcional; no afecta al núcleo)
uv run --group dashboard streamlit run src/rag_lab/dashboard/app.py
```

- Abre `http://localhost:8501`.
- `.streamlit/config.toml` limita el servidor a `localhost`, lo arranca sin abrir el navegador, desactiva la telemetría de uso de Streamlit (`gatherUsageStats = false`) y oculta "Deploy" y las opciones de desarrollador (`toolbarMode = "minimal"`).
- **Presentación:**
  - Las tablas de hasta 5 columnas son estáticas; las más anchas se pueden desplazar, con un aviso.
  - Cada matriz de confusión muestra todas las clases que tienen casos, más `judge_unverifiable` y el total por fila. Debajo, una lectura compacta por fila deja todos los valores legibles en móvil.
  - Los textos del corpus se escapan para mostrarse literalmente, sin interpretar markdown ni LaTeX.

## Arquitectura

| Archivo | Rol |
|---|---|
| `src/rag_lab/dashboard/data.py` | Adaptador de lectura y validación, sin Streamlit. Lee los archivos, verifica hashes contra manifiestos y reportes, y arma vistas simples. |
| `src/rag_lab/dashboard/app.py` | Interfaz con componentes nativos de Streamlit (`metric`, `dataframe`, `bar_chart`, `tabs`, `expander`). |
| `tests/test_dashboard.py` | Tests offline del adaptador y recorrido de la app con `streamlit.testing.AppTest`. Estos últimos se omiten si Streamlit no está instalado. |

## Datos que necesita

Todos están versionados:

| Sección | Archivos |
|---|---|
| Retrieval | `reports/compare_eval_A_dense_k5_vs_B_hybrid_k5.json`, `data/eval/questions.jsonl` |
| Generación | `reports/compare_gen_groq_gpt-oss-120b_A_dense_k5_vs_B_hybrid_k5.json`, `reports/lexical_v2_groq_gpt-oss-120b_{A_dense_k5,B_hybrid_k5}.json` |
| Faithfulness | `reports/judge_judge-v1-otpm_qwen3.8-27b_comparison.json`, `runs/stage3/judge/judge-v1-otpm_qwen3.8-27b/judge_manifest.json` |
| Failure explorer | `runs/stage3/judge/judge-v1-otpm_qwen3.8-27b/predictions.jsonl`, `data/stage3/{judge_full_selection.json, answers.jsonl, claims_proposed.jsonl, perturbations.jsonl, human_labels_round1.jsonl, perturbation_review.jsonl}` |

- Si falta un archivo, la barra lateral lo informa y la sección queda vacía, con un aviso. Nunca se completa con datos inventados.
- La barra lateral muestra 7 controles de integridad: las predicciones coinciden con el manifiesto y con el reporte, las entradas del juez y la selección coinciden con lo registrado, y el `cases_sha256` es el congelado.

## Secciones

- **Retrieval:** Recall@5, Complete@5 y MRR de A (dense) y B (hybrid), con la diferencia entre ambas.
  - Gráfico de barras, comparación pareada (test de signo), métricas por categoría.
  - Tabla de las 40 preguntas, con filtro por categoría y por preguntas con cambio. Las no respondibles no tienen métricas de retrieval y sus celdas quedan vacías.
- **Generación:** aviso destacado del cambio de normalización v1 → v2. La v1 es la oficial de la Etapa 2; la v2 se diseñó después de observar los falsos negativos e29 y e31.
  - Cobertura de `required_facts` y de todos los facts, en v1 y v2 por corrida, con las preguntas que cambian.
  - Abstención (gate y LLM; respondibles y no respondibles) y umbrales del gate.
  - Citas: precisión, recall de evidencia citada y validez.
  - Comparación pareada A/B.
- **Faithfulness:** las 30 originales y los 17 controles sintéticos van por separado.
  - Acuerdo k/n con IC de Wilson, matrices de confusión por `label_cited` y `label_context`, y casos con `supported` indebido.
  - La kappa se muestra solo cuando es interpretable. Si no lo es, se explica por qué: "no aplica" cuando la referencia tiene una sola clase y "no informativa" cuando el juez usó una sola. La interpretación lee la matriz; no recalcula nada.
  - Aviso explícito de que esto no es precisión en producción. También se muestran `judge_unverifiable`, citas no literales, estabilidad frente al piloto y limitaciones.
- **Failure explorer:** estudios de caso J02, J12 y J46, y cualquier otro de los 47 casos.
  - Pregunta, afirmación enviada al juez (y la original no enviada, si es perturbación) y respuesta del generador.
  - Etiquetas de referencia, cruda y verificada del juez, con su resultado.
  - Citas del juez con su verificación, razonamiento (con nota si está cortado en 496 caracteres) y fragmentos del contexto, marcando cuáles cita la respuesta.
  - Las explicaciones de J02, J12 y J46 resumen la auditoría de `docs/judge.md`.

## Privacidad

- Las vistas nunca incluyen `request_id`, encabezados de rate limit, claves de caché, contenido crudo ni mensajes de error del proveedor.
- `assert_no_private_data` verifica en los tests todas las vistas y los 47 casos, buscando claves privadas y patrones `org_…`, `gsk_…` y `req_…`.
- El dashboard no importa clientes de modelos ni de HTTP (también verificado por un test).
- No lee `.env`, la caché ni la predicción parcial que contiene el identificador de la organización.

## Limitaciones

- Muestra solo lo que ya está en los reportes. No hay intervalos ni métricas que no hayan sido calculados antes; por ejemplo, Retrieval no tiene IC.
- Los resultados son de conjuntos pequeños: 30 preguntas respondibles y 47 casos de faithfulness. Las advertencias de cada reporte se muestran junto a los números.
- El texto explicativo de los estudios de caso es fijo, tomado de la auditoría. Si las predicciones cambiaran, los tests lo detectarían, pero el texto no se actualiza solo.
- El dashboard no tiene autenticación ni está pensado para publicarse; solo escucha en `localhost`.
