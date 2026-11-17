"""Dashboard local de resultados del RAG Evaluation Lab (Etapa 4A). Solo lectura.

Ejecutar:  uv run --group dashboard streamlit run src/rag_lab/dashboard/app.py

No llama a modelos ni escribe archivos: muestra reportes, corridas y datos congelados a través
de `rag_lab.dashboard.data`. El formato de los números es solo de presentación.
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from rag_lab.dashboard import data as D

st.set_page_config(page_title="RAG Evaluation Lab", page_icon="📊", layout="wide")

SECTIONS = ("Retrieval", "Generación", "Faithfulness", "Failure explorer")
MISSING = "—"
HEADERS = {"metric": "métrica"}
MAX_STATIC_COLS = 5
SCROLL_HINT = "Tabla ancha: desplazá horizontalmente para ver todas las columnas."


@st.cache_data(show_spinner=False)
def _store() -> D.Store:
    return D.load_store()


# --- Formato (solo presentación) -----------------------------------------------------------


def _fmt(v) -> str:
    if v is None:
        return MISSING
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


_MD_SPECIAL = re.compile(r"([\\`*_\[\]#$<>|~])")


def _md(text: str | None) -> str:
    """Escapa markdown/LaTeX en textos de datos para mostrarlos tal cual."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def _pct(x: float | None) -> str:
    return MISSING if x is None else f"{x * 100:.1f}%"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _table(rows: list[dict]) -> None:
    """Tabla estática para hasta MAX_STATIC_COLS columnas (ajusta el texto). Las más anchas
    van a una tabla desplazable, porque una tabla estática las recortaría en móvil."""
    if not rows:
        st.caption("Sin filas.")
        return
    if len(rows[0]) > MAX_STATIC_COLS:
        _grid(rows, pinned=next(iter(rows[0])))
        return
    st.table(pd.DataFrame([{HEADERS.get(k, k): _fmt(v) for k, v in r.items()} for r in rows]))


def _grid(rows: list[dict], pinned: str, height: int | None = None) -> None:
    """Tabla navegable para listas largas, con la primera columna fija y faltantes como —."""
    df = pd.DataFrame([{HEADERS.get(k, k): _fmt(v) for k, v in r.items()} for r in rows])
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        height=height or min(420, 36 * (len(df) + 1) + 4),
        column_config={HEADERS.get(pinned, pinned): st.column_config.Column(pinned=True)},
    )
    st.caption(SCROLL_HINT)


def _text_block(label: str, text: str, badge: str | None = None) -> None:
    """Contenido principal en texto normal y alto contraste, dentro de un recuadro."""
    with st.container(border=True):
        st.markdown(f"**{label}**" + (f" &nbsp; {badge}" if badge else ""))
        st.markdown(text)  # el llamador escapa los datos con _md


def _missing(what: str) -> None:
    st.warning(f"No se encontró el reporte de {what}. La sección no muestra datos.")


# --- Barra lateral ------------------------------------------------------------------------

store = _store()
checks = D.integrity(store)

with st.sidebar:
    st.title("RAG Evaluation Lab")
    st.caption("Resultados congelados · solo lectura · sin llamadas a modelos")
    section = st.radio("Sección", SECTIONS, label_visibility="collapsed")
    st.divider()
    n_ok = sum(c["ok"] for c in checks)
    if checks and n_ok == len(checks):
        st.success(f"Integridad: {n_ok}/{len(checks)} hashes coinciden")
    else:
        st.error(f"Integridad: {n_ok}/{len(checks)} hashes coinciden")
    with st.expander("Detalle de integridad"):
        _table(
            [
                {"control": c["check"], "esperado": c["expected"], "actual": c["actual"]}
                for c in checks
            ]
        )
    if store.issues:
        st.warning("Archivos ausentes o ilegibles:\n\n" + "\n".join(f"- {i}" for i in store.issues))
    st.caption("Corpus ficticio · 40 preguntas de evaluación · documentación en docs/")


# --- Retrieval ----------------------------------------------------------------------------


def render_retrieval() -> None:
    st.header("Retrieval: dense (A) vs. hybrid (B)")
    v = D.retrieval_view(store)
    if v is None:
        _missing("retrieval")
        return
    st.caption(
        f"top-{v['k']} · {v['n_questions']} preguntas de evaluación, de las cuales "
        f"{v['n_answerable']} son respondibles (las métricas se calculan solo sobre ellas)."
    )
    paired = {p["metric"]: p for p in v["paired"]}
    cols = st.columns(len(v["metrics"]))
    for col, m in zip(cols, v["metrics"], strict=True):
        p = paired.get(m["metric"], {})
        with col, st.container(border=True):
            st.markdown(f"**{m['metric']}**")
            a, b = st.columns(2)
            a.metric("A · dense", f"{m['A (dense)']:.3f}")
            b.metric("B · hybrid", f"{m['B (hybrid)']:.3f}")
            st.caption(
                f"Diferencia B − A: {m['delta B − A']:+.4f} · A mejor en "
                f"{_plural(p.get('A mejor', 0), 'pregunta', 'preguntas')}, B mejor en "
                f"{_plural(p.get('B mejor', 0), 'pregunta', 'preguntas')}, "
                f"{p.get('empates', 0)} empates · p = {_fmt(p.get('p (test de signo)'))}"
            )
    st.info(
        "Las diferencias entre A y B son pequeñas: cambian 1 o 2 preguntas sobre 30 y el test "
        "de signo da p = 1,0 en las tres métricas. **No son concluyentes.** El test ignora "
        "empates y no corrige por comparaciones múltiples."
    )
    left, right = st.columns([3, 2])
    with left:
        chart = pd.DataFrame(v["metrics"]).set_index("metric")[["A (dense)", "B (hybrid)"]]
        st.bar_chart(
            chart, stack=False, horizontal=True, height=260, x_label="valor (0–1)", y_label=""
        )
    with right:
        st.markdown("**Comparación pareada por pregunta**")
        _table(v["paired"])
    with st.expander("Por categoría"):
        _table(v["by_category"])

    st.subheader("Por pregunta")
    rows = v["per_question"]
    cats = sorted({r["categoría"] for r in rows})
    chosen = st.multiselect("Categorías", cats, default=cats)
    only_changed = st.toggle(
        "Solo preguntas con cambio de métrica",
        help="Preguntas donde A y B difieren: " + ", ".join(v["changed_qids"]),
    )
    shown = [
        r
        for r in rows
        if r["categoría"] in chosen and (not only_changed or r["qid"] in v["changed_qids"])
    ]
    _grid(shown, pinned="qid")
    st.caption(
        f"{MISSING} = sin métrica de retrieval (pregunta no respondible); su manejo se evalúa "
        "en Generación (abstención)."
    )


# --- Generación ---------------------------------------------------------------------------


def render_generation() -> None:
    st.header("Generación con citas y abstención")
    v = D.generation_view(store)
    if v is None:
        _missing("generación")
        return
    st.caption("Modelo generador: openai/gpt-oss-120b vía Groq · respuestas ya congeladas.")
    st.warning(
        "**Normalización léxica: v1 (oficial) y v2 (corrección de medición).** "
        + (v["lexical_design_note"] or "")
    )
    t1, t2, t3, t4 = st.tabs(
        ["Hechos requeridos (v1 / v2)", "Abstención", "Citas", "Comparación pareada"]
    )
    with t1:
        st.markdown("**Métricas oficiales (v1), sobre respondibles respondidas**")
        _table(v["official"][:2])
        st.markdown("**v1 frente a v2** (mismo denominador)")
        _table(v["lexical"])
        if v["lexical"]:
            lex = pd.DataFrame(v["lexical"])
            chart = lex[lex["metric"] == "Todos los required_facts"].set_index("corrida")[
                ["v1 (oficial Etapa 2)", "v2"]
            ]
            st.bar_chart(
                chart,
                stack=False,
                horizontal=True,
                height=200,
                x_label="todos los required_facts (fracción)",
                y_label="",
            )
        st.markdown("**Preguntas cuyo resultado cambia con v2**")
        _table(v["lexical_changed"])
    with t2:
        _table(v["abstention"])
        g = v["gates"]
        same = g["A"] == g["B"]
        st.markdown(
            f"**Umbral del gate de abstención:** A = {g['A']:.6f}, B = {g['B']:.6f}"
            + (" (el mismo valor numérico)" if same else "")
            + f". Se aplican a **scores distintos**: A usa `{g['A_score']}` (similitud del "
            f"primer resultado) y B usa `{g['B_score']}` (máxima similitud densa dentro del "
            "top-k). Cada umbral se calibró por separado sobre su propio score, así que el "
            "mismo número no significa la misma regla."
        )
    with t3:
        _table(v["official"][2:])
        e = v["errors"]
        st.caption(
            "Errores técnicos — A: "
            + ", ".join(f"{k}={x}" for k, x in e["A"].items())
            + " · B: "
            + ", ".join(f"{k}={x}" for k, x in e["B"].items())
        )
    with t4:
        _table(v["paired"])
        st.info(v["note"])
        st.caption(
            f"{MISSING} = el reporte no calcula ese valor para la métrica (p. ej., sin pares "
            "que difieran no hay test de signo)."
        )


# --- Faithfulness -------------------------------------------------------------------------


def _kappa_text(s: dict) -> str:
    if s["kappa_lectura"]:
        return s["kappa_lectura"]
    return MISSING if s["kappa"] is None else f"{s['kappa']:.2f}"


def _wrap_label(x):
    """Separa los guiones bajos de las etiquetas para que el texto pueda partirse en líneas
    angostas (solo presentación; la etiqueta es la misma)."""
    return x.replace("_", " ") if isinstance(x, str) else x


def _matrix(s: dict) -> None:
    _table([{_wrap_label(k): _wrap_label(v) for k, v in r.items()} for r in s["matriz"]])
    # Lectura compacta por fila: legible en cualquier ancho (la tabla puede recortarse en móvil).
    corner = D.MATRIX_CORNER
    lines = []
    for r in s["matriz"]:
        parts = [f"{c} {r[c]}" for c in r if c not in (corner, "total") and r[c]]
        lines.append(f"**{r[corner]}** (total {r['total']}): " + " · ".join(parts))
    st.caption("  \n".join(lines))
    if s["omitidas"]:
        st.caption("Clases sin ningún caso en este grupo (se omiten): " + ", ".join(s["omitidas"]))


def render_faithfulness() -> None:
    st.header("Faithfulness: juez semántico vs. revisión humana")
    v = D.faithfulness_view(store)
    if v is None:
        _missing("faithfulness")
        return
    run = v["run"]
    if run:
        st.caption(
            f"Evaluación definitiva judge-v1-otpm · {run['modelo']} · prompt {run['prompt']} · "
            f"max_completion_tokens {run['max_completion_tokens']} · temperature "
            f"{run['temperature']} · seed {run['seed']} · {run['casos']} casos · "
            f"{run['solicitudes']} solicitudes · {run['tokens']:,} tokens · estado "
            f"{run['estado']}".replace(",", ".")
        )
    st.error(
        "Esto es acuerdo con una referencia humana en un conjunto pequeño y no aleatorio "
        "(afirmaciones de una sola corrida de generación). **No** es la precisión del juez en "
        "producción. Los 17 negativos son controles sintéticos derivados de las mismas "
        "afirmaciones, no observaciones independientes."
    )
    for name, fields in v["groups"].items():
        st.subheader(v["group_labels"].get(name, name))
        cols = st.columns(2)
        for col, f in zip(cols, D.FIELDS, strict=True):
            s = fields[f]
            lo, hi = s["wilson95"] or (None, None)
            with col, st.container(border=True):
                st.metric(f"Acuerdo en {f}", f"{s['acuerdos']}/{s['n']}")
                st.caption(
                    f"IC Wilson 95%: {_pct(lo)} – {_pct(hi)} · Cohen's kappa: {_kappa_text(s)}"
                )
                _matrix(s)
                if s["supported_indebido"]:
                    st.caption(
                        "Juez supported cuando la referencia no: "
                        f"{', '.join(s['supported_indebido'])} (de "
                        f"{_plural(s['n_referencia_no_supported'], 'caso', 'casos')} "
                        "no supported)"
                    )
    st.caption(
        "Filas: referencia (humana o expectativa confirmada); columnas: etiqueta del juez tras "
        "verificar citas; total = casos de esa referencia. judge_unverifiable = el juez declaró "
        "respaldo sin una cita literal válida de un fragmento citado; cuenta como desacuerdo."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("judge_unverifiable", len(v["unverifiable"]))
    c1.caption(", ".join(v["unverifiable"]) or MISSING)
    c2.metric("Citas no literales", len(v["invalid_quotes"]))
    stab = v["stability"]
    if stab["n"]:
        c3.metric("Estabilidad vs. piloto judge-v1", f"{stab['same']['label_cited']}/{stab['n']}")
        c3.caption("Etiquetas idénticas con max_completion_tokens 1536 (piloto, no mezclado).")
    with st.expander("Limitaciones"):
        st.markdown(
            "- n = 47 (30 originales + 17 sintéticos); solo 3 originales parcialmente "
            "respaldadas y ninguna original sin respaldo.\n"
            "- Selección no aleatoria: todas las afirmaciones salen de una sola corrida.\n"
            "- Las perturbaciones cambian un solo dato de una afirmación original y comparten "
            "su respuesta y contexto.\n"
            "- Una cita literal válida no demuestra faithfulness (ver J46).\n"
            "- El juez no se ajustó después de observar errores.\n"
            "- El cambio de max_completion_tokens de 1536 a 640 fue operativo (límite OTPM de "
            "Groq); el piloto con 1536 queda separado.\n"
            f"- {v['note']}"
        )
    with st.expander("Todos los casos"):
        _grid(v["per_case"], pinned="caso")


# --- Failure explorer ---------------------------------------------------------------------

OUTCOME_TEXT = {
    "agree": "✅ acuerdo",
    "semantic_error": "❌ error semántico",
    "citation_error": "⚠️ error de cita",
    "technical_failure": "⛔ fallo técnico",
}


def _yes_no(ok: bool) -> str:
    return ":green-badge[sí]" if ok else ":red-badge[no]"


def _highlight_change(text: str, change: list[str] | None) -> str:
    """Resalta en negrita el fragmento modificado de la perturbación (solo presentación)."""
    new = _md(change[1]) if change and len(change) > 1 else ""
    if not new or new not in text:
        return text
    return text.replace(new, f"**{new}**", 1)


def render_failures() -> None:
    st.header("Failure explorer")
    ids = D.case_ids(store)
    if not ids or not store.get("judge_predictions"):
        _missing("predicciones del juez")
        return
    featured = st.radio(
        "Estudios de caso", (*D.FEATURED_CASES, "Otro caso"), horizontal=True, index=0
    )
    others = [i for i in ids if i not in D.FEATURED_CASES]
    case_id = (
        st.selectbox("Caso", others, format_func=_case_label)
        if featured == "Otro caso"
        else featured
    )
    d = D.case_detail(store, case_id)
    if d is None:
        st.warning("Caso sin predicción o sin comparación.")
        return

    st.subheader(f"{d['case_id']} · {d['source_id']}")
    st.markdown(
        ":orange-badge[control sintético (perturbación)]"
        if d["afirmacion_original"]
        else ":blue-badge[afirmación original]"
    )
    if d["nota"]:
        st.info(d["nota"])

    cols = st.columns(len(d["etiquetas"]))
    for col, lab in zip(cols, d["etiquetas"], strict=True):
        with col, st.container(border=True):
            st.markdown(f"**{lab['campo']}** · {OUTCOME_TEXT.get(lab['resultado'], MISSING)}")
            st.markdown(
                f"Referencia: `{lab['referencia']}` ({lab['origen referencia']})  \n"
                f"Juez, etiqueta cruda: `{lab['juez (cruda)']}`  \n"
                f"Juez, tras verificar citas: `{lab['juez (verificada)']}`"
            )

    _text_block(f"Pregunta ({d['qid']})", _md(d["pregunta"]))
    if d["afirmacion_original"]:
        a, b = st.columns(2)
        with a:
            _text_block(
                "Afirmación original",
                _md(d["afirmacion_original"]),
                ":gray-badge[no enviada al juez]",
            )
        with b:
            _text_block(
                "Afirmación perturbada",
                _highlight_change(_md(d["afirmacion_juzgada"]), d["cambio"]),
                f":orange-badge[enviada al juez · {d['tipo_perturbacion']}]",
            )
        st.caption(
            f"Cambio: {' → '.join(d['cambio'] or [])} · expectativa confirmada por revisión "
            f"humana: {d['revision_humana_perturbacion']}"
        )
    else:
        _text_block("Afirmación enviada al juez", _md(d["afirmacion_juzgada"]))

    if d["humano_original"] and d["afirmacion_original"]:
        h = d["humano_original"]
        st.caption(
            f"Etiqueta humana de la afirmación original: cited={h['label_cited']}, "
            f"context={h['label_context']}, respaldo={', '.join(h['support_cite_ids'] or [])}"
        )
    elif d["humano_original"] and d["humano_original"]["nota"]:
        st.caption(f"Nota humana: {d['humano_original']['nota']}")
    with st.expander("Respuesta del generador"):
        st.markdown(_md(d["respuesta"]))
        st.caption(f"Fragmentos citados por la respuesta: {', '.join(d['fragmentos_citados'])}")

    st.markdown("#### Evidencia citada por el juez")
    if not d["evidencia_juez"]:
        st.caption("El juez no citó evidencia.")
    for e in d["evidencia_juez"]:
        with st.container(border=True):
            st.markdown(
                f"**{e['cite_id']}** &nbsp; fragmento citado por la respuesta "
                f"{_yes_no(e['fragmento citado'])} &nbsp; cita literal "
                f"{_yes_no(e['cita literal'])} &nbsp; válida {_yes_no(e['válida'])}"
            )
            st.markdown(_md(e["quote"]))

    st.markdown("#### Razonamiento del juez")
    st.caption("Emitido después de las etiquetas (orden de claves de la respuesta).")
    with st.container(border=True):
        st.markdown(_md(d["razonamiento"]))
    if d["razonamiento_cortado"]:
        st.caption(
            f"El razonamiento termina exactamente en {D.RATIONALE_CUT_CHARS} caracteres: llegó "
            "así del proveedor (finish_reason=stop); la causa no se pudo determinar offline. "
            "No afecta las etiquetas."
        )

    st.markdown("#### Contexto recuperado")
    for c in d["contexto"]:
        tag = "citado" if c["citado"] else "no citado"
        with st.expander(f"{c['cite_id']} · {c['documento']} · v{c['versión']} · {tag}"):
            st.caption(f"Estado del documento: {c['estado']}")
            st.markdown(_md(c["texto"]))


def _case_label(case_id: str) -> str:
    rows = {r["caso"]: r for r in (D.faithfulness_view(store) or {}).get("per_case", [])}
    r = rows.get(case_id)
    if not r:
        return case_id
    bad = r["cited resultado"] != "agree" or r["context resultado"] != "agree"
    return f"{case_id} · {r['tipo']} · {r['fuente']}" + (" · desacuerdo" if bad else "")


RENDER = {
    "Retrieval": render_retrieval,
    "Generación": render_generation,
    "Faithfulness": render_faithfulness,
    "Failure explorer": render_failures,
}
RENDER[section]()
