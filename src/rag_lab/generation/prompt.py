"""Prompt y esquema de salida estructurada.

El prompt se arma SOLO con: texto de la pregunta, alcance temporal (regla léxica sobre la
pregunta), fecha de referencia y fragmentos recuperados con sus metadatos. Las instrucciones
van en un único mensaje de usuario (recomendación de Groq para modelos de razonamiento).
"""

from __future__ import annotations

from rag_lab.generation.context import ContextChunk
from rag_lab.generation.temporal import TemporalScope

PROMPT_VERSION = "v1"

ABSTAIN_REASONS = ("none", "insufficient_evidence", "needs_temporal_context")

# Compatible con strict mode de Groq: todo `required`, additionalProperties=false.
# `citations` es un string libre a propósito: así se pueden detectar citas inválidas.
ANSWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
        "abstain": {"type": "boolean"},
        "abstain_reason": {"type": "string", "enum": list(ABSTAIN_REASONS)},
    },
    "required": ["answer", "citations", "abstain", "abstain_reason"],
    "additionalProperties": False,
}

_TEMPORAL_RULES = {
    "current": (
        "ALCANCE TEMPORAL: la pregunta es sobre lo VIGENTE (no menciona un período pasado). "
        "Fecha de referencia: {ref}. Respondé solo con fragmentos en estado VIGENTE. Los "
        "fragmentos HISTÓRICOS describen reglas que ya no aplican: no los uses para la "
        "respuesta ni los cites."
    ),
    "historical_anchored": (
        "ALCANCE TEMPORAL: la pregunta es HISTÓRICA (menciona un momento pasado: "
        '"{evidence}"). Fecha de referencia: {ref}. Usá la versión cuyo período de vigencia '
        "incluye ese momento, aunque esté marcada como HISTÓRICA, y decí a qué versión o "
        "período corresponde la respuesta."
    ),
    "historical_unanchored": (
        'ALCANCE TEMPORAL: la pregunta parece referirse al pasado ("{evidence}") pero no '
        "indica una fecha o período. Fecha de referencia: {ref}. Si los fragmentos tienen "
        "versiones con respuestas distintas, no elijas una: respondé con abstain=true, "
        'abstain_reason="needs_temporal_context" y pedí la fecha o el período en answer.'
    ),
}

_TEMPLATE = """Sos el asistente de soporte de Kestrel Billing. Respondé la PREGUNTA usando \
únicamente los FRAGMENTOS de la base de conocimiento que aparecen abajo.

REGLAS
1. Usá solo información presente en los fragmentos. No uses conocimiento externo ni completes \
datos que no estén escritos.
2. Cada dato de la respuesta debe estar respaldado por al menos un fragmento. En "citations" \
poné los IDs (por ejemplo "S2") de todos los fragmentos que respaldan la respuesta. Citá solo \
IDs que aparezcan abajo.
3. Cada fragmento indica su estado de vigencia (VIGENTE o HISTÓRICO) y su período.
4. {temporal_rule}
5. Si los fragmentos no contienen la información necesaria para responder, devolvé \
abstain=true, abstain_reason="insufficient_evidence", citations=[] y en answer explicá en una \
oración que la base de conocimiento no tiene esa información. No adivines.
6. Si respondés, usá abstain=false y abstain_reason="none".
7. Respondé en español, en un máximo de 3 oraciones.

FRAGMENTOS
{fragments}

PREGUNTA
{question}

Devolvé solo el objeto JSON con las claves answer, citations, abstain y abstain_reason."""


def build_prompt(
    question: str, context: list[ContextChunk], scope: TemporalScope, reference_date: str
) -> str:
    rule = _TEMPORAL_RULES[scope.kind].format(ref=reference_date, evidence=scope.evidence or "")
    fragments = "\n\n".join(c.render() for c in context) if context else "(ninguno)"
    return _TEMPLATE.format(temporal_rule=rule, fragments=fragments, question=question.strip())


def build_messages(
    question: str, context: list[ContextChunk], scope: TemporalScope, reference_date: str
) -> list[dict]:
    return [{"role": "user", "content": build_prompt(question, context, scope, reference_date)}]
