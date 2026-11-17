"""Etapa 3A: faithfulness semántica por afirmación (offline). Ver docs/faithfulness.md.

- `answers`: respuestas únicas de las corridas A/B guardadas (sin regenerar), con sus
  fragmentos de contexto y la correspondencia con cada corrida.
- `schema`: etiquetas, subtipos, contratos de afirmaciones, etiquetas humanas y salida del juez.
- `annotation`: exportación de la planilla de anotación humana e importación de etiquetas.
- `judge_prompt` / `judge_verify`: contrato del futuro juez LLM y validador de su salida.
- `agreement`: matriz de confusión, kappa y casos críticos juez vs humano.
- `perturbations`: controles sintéticos (números, negaciones, unidades, versiones).

Nada en este paquete llama a una API. El juez recibe solo pregunta, afirmaciones y fragmentos:
nunca etiquetas, `reference_answer`, `required_facts` ni `forbidden_facts`.
"""
