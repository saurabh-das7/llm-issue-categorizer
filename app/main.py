# app/main.py
# llm-issue-categorizer — Streamlit UI

import time
from collections import Counter

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    parse_file,
    run_categorisation,
    run_consolidation,
    run_multi_tag,
    run_auto_suggest,
)
from samples import SAMPLES, get_sample_df, get_sample_context

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="llm-issue-categorizer",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Design system ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    color: #111827;
    background-color: #f3f4f6;
}
.block-container {
    padding-top: 1rem;
    padding-bottom: 3rem;
    max-width: 900px;
    background: #f3f4f6;
}
header[data-testid="stHeader"] { display: none; }
#MainMenu { display: none; }
footer { display: none; }

/* Slightly faded disabled state — not completely grey */
button:disabled { opacity: 0.45 !important; }
.stRadio [data-baseweb="radio"] label { transition: opacity 0.2s; }
[aria-disabled="true"] { opacity: 0.6 !important; }

.tool-tagline { font-size: 15px; color: #374151; margin: 6px 0 3px 0; line-height: 1.6; }
.attr-line { font-size: 13px; color: #6b7280; margin: 0; }
.attr-line a { color: #0f766e; text-decoration: none; font-weight: 500; margin-right: 14px; }
.attr-line a:hover { text-decoration: underline; }
.section-title { font-size: 16px; font-weight: 600; color: #111827; margin: 0 0 4px 0; }
.section-subtitle { font-size: 13px; color: #6b7280; margin: 0 0 14px 0; }

.box-warning {
    background: #fffbeb; border: 1px solid #fcd34d;
    border-radius: 6px; padding: 10px 14px;
    font-size: 13px; color: #92400e; margin-bottom: 12px;
}
.box-info {
    background: #f0fdf9; border: 1px solid #99f6e4;
    border-radius: 6px; padding: 10px 14px;
    font-size: 13px; color: #134e4a; margin-bottom: 12px;
}
.summary-label {
    font-size: 11px; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #0f766e; margin: 16px 0 8px 0;
}
.box-merge {
    background: #f0fdf9; border-left: 3px solid #0f766e;
    border-radius: 0 6px 6px 0; padding: 8px 12px;
    font-size: 13px; color: #134e4a; margin-bottom: 6px;
}
.box-flag {
    background: #fffbeb; border-left: 3px solid #f59e0b;
    border-radius: 0 6px 6px 0; padding: 8px 12px;
    font-size: 13px; color: #92400e; margin-bottom: 6px;
}
.box-uc { font-size: 14px; color: #374151; padding: 6px 0;
    border-bottom: 1px solid #f3f4f6; line-height: 1.5; }
.box-uc:last-child { border-bottom: none; }
.box-mt {
    background: #f0fdf9; border-left: 3px solid #0f766e;
    border-radius: 0 6px 6px 0; padding: 8px 12px;
    font-size: 14px; color: #111827; margin-bottom: 6px;
}

/* Mandatory field */
div[data-testid="stTextInput"][data-key="ctx_input"] input {
    border: 1.5px solid #ef4444 !important; font-size: 15px !important;
}
div[data-testid="stTextInput"][data-key="ctx_input"] input:focus {
    border: 2px solid #dc2626 !important;
    box-shadow: 0 0 0 3px rgba(220,38,38,0.15) !important;
}
div[data-testid="stTextInput"] input:disabled {
    border: 1px solid #e5e7eb !important;
    background: #f9fafb !important; color: #9ca3af !important;
}

div[data-testid="column"] {
    padding-left: 4px !important; padding-right: 4px !important;
}
</style>
""", unsafe_allow_html=True)

TEAL_START = (0x0f, 0x76, 0x6e)
TEAL_END = (0xcc, 0xfb, 0xf1)
GREY = "#d1d5db"


# ── Session state ──────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "stage": "input",
        "uploader_key": 0,
        "sample_key": None,
        "df": None,
        "context": "",
        "cat_mode": "no_suggestions",
        "depth": "primary",
        "manual_cats": "",
        "as_cats": [],
        "as_done": False,
        "result_df": None,
        "mt_df": None,
        "consolidation": None,
        "show_low_conf": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def reset_all():
    key = st.session_state.get("uploader_key", 0)
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()
    st.session_state.uploader_key = key + 1


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_chart(categories, counts, x_label="Ticket count"):
    total = sum(counts)
    pcts = [f"{c} ({round(c/total*100)}%)" if total else str(c)
            for c in counts]
    named = sum(1 for c in categories if c != "Uncategorised")
    colors, ti = [], 0
    for cat in categories:
        if cat == "Uncategorised":
            colors.append(GREY)
        else:
            ratio = ti / max(named - 1, 1)
            r = int(TEAL_START[0] + ratio * (TEAL_END[0] - TEAL_START[0]))
            g = int(TEAL_START[1] + ratio * (TEAL_END[1] - TEAL_START[1]))
            b = int(TEAL_START[2] + ratio * (TEAL_END[2] - TEAL_START[2]))
            colors.append(f"#{r:02x}{g:02x}{b:02x}")
            ti += 1
    fig = go.Figure(go.Bar(
        x=counts, y=categories, orientation="h",
        marker_color=colors, text=pcts, textposition="outside",
        hovertemplate="%{y}: %{x}<extra></extra>"
    ))
    fig.update_layout(
        xaxis_title=x_label, yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=130, t=8, b=36),
        height=max(260, len(categories) * 44),
        plot_bgcolor="white", paper_bgcolor="white", font=dict(size=13)
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f3f4f6")
    return fig


def get_template_csv():
    return pd.DataFrame(columns=[
        "ticket_id", "issue_description", "current_label", "resolution_notes"
    ]).to_csv(index=False).encode("utf-8")


# ── Derived state ──────────────────────────────────────────────────────────────

stage = st.session_state.stage
frozen = stage != "input"


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

title_col, reset_col = st.columns([5, 1])
with title_col:
    st.title("🗂️ llm-issue-categorizer")
with reset_col:
    st.write("")
    st.write("")
    st.write("")
    if st.button("↺ Start over", key="reset_top"):
        reset_all()
        st.rerun()

st.markdown(
    "<p class='tool-tagline'>Your ops tickets say \"quality issue.\" "
    "This tool tells you what that actually means — and how often.</p>",
    unsafe_allow_html=True
)
st.markdown(
    "<p class='attr-line'>Built by <strong>Saurabh Das</strong> — "
    "Senior TPM & Designated PM at Microsoft AI, documenting an AI learning journey in public.&nbsp;"
    "<a href='https://linkedin.com/in/saurabhdas7' target='_blank'>LinkedIn</a>"
    "<a href='https://github.com/saurabh-das7/llm-issue-categorizer' target='_blank'>GitHub</a>"
    "<a href='https://github.com/saurabh-das7/llm-issue-categorizer' target='_blank'>Project repo</a>"
    "</p>",
    unsafe_allow_html=True
)

with st.expander("How to use this tool", expanded=False):
    st.markdown("""
**Choose your data** — Pick a sample dataset or upload your own CSV / Excel / TXT (up to 100 rows).
Only `issue_description` is required.

**Configure your run** — Choose how categories are created *(Category source)* and how deeply
each ticket is analysed *(Analysis depth)*. For Manual list or Auto-suggest, enter or review
your taxonomy before running.

**Review results** — Every ticket gets a category, confidence score, and one-line reasoning.
The Results Summary explains merges, overlaps, and what's hiding in the Uncategorised bucket.

**Download** — Export the full annotated dataset as CSV.
    """)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Choose your data
# (always rendered at same height — disabled when frozen so page height stays
#  consistent and Processing appears right below Run after clicking it)
# ══════════════════════════════════════════════════════════════════════════════

c_title = "#9ca3af" if frozen else "#111827"
c_sub = "#d1d5db" if frozen else "#6b7280"

st.markdown(
    f"<p class='section-title' style='color:{c_title}'>Choose your data</p>",
    unsafe_allow_html=True
)
st.markdown(
    f"<p class='section-subtitle' style='color:{c_sub}'>Try a sample dataset or upload your own file</p>",
    unsafe_allow_html=True
)

# Sample tiles — always shown, disabled when frozen
c1, c2, c3 = st.columns(3)
for col, key in zip([c1, c2, c3], list(SAMPLES.keys())):
    s = SAMPLES[key]
    with col:
        selected = st.session_state.sample_key == key
        if st.button(
            f"{s['icon']} {s['label'].split()[0]}\n{s['row_count']} rows",
            key=f"tile_{key}",
            help=s["label"],
            type="primary" if selected else "secondary",
            use_container_width=True,
            disabled=frozen
        ):
            st.session_state.sample_key = key
            st.session_state.df = get_sample_df(key)
            st.session_state.context = get_sample_context(key)
            st.session_state.result_df = None
            st.session_state.consolidation = None
            st.session_state.mt_df = None
            st.session_state.as_done = False
            st.rerun()
        if selected:
            st.caption("✅ Selected")

st.markdown(
    f"<p style='text-align:center;color:{'#e5e7eb' if frozen else '#9ca3af'};font-size:13px;margin:10px 0'>— or upload your own —</p>",
    unsafe_allow_html=True
)

# Upload section — shown always, but only interactive when not frozen
if not frozen:
    st.markdown("""
<div class='box-warning'>
⚠️ <strong>Do not upload files containing personal data, customer PII, or confidential
business information.</strong> Data is processed by the Google Gemini API.
</div>
""", unsafe_allow_html=True)

    st.markdown(
        "<p style='font-size:14px;color:#374151;margin:0 0 4px 0'>"
        "Only <code>issue_description</code> is required. Add <code>ticket_id</code>, "
        "<code>current_label</code>, and <code>resolution_notes</code> for richer output.</p>"
        "<p style='font-size:13px;color:#6b7280;margin:0 0 10px 0'>"
        "Accepted: CSV · Excel (.xlsx) · TXT (pipe-delimited) · Max 100 rows</p>",
        unsafe_allow_html=True
    )

    up_col, tmpl_col = st.columns([3, 1])
    with up_col:
        uploaded_file = st.file_uploader(
            "Upload", type=["csv", "xlsx", "txt"],
            key=f"file_uploader_{st.session_state.uploader_key}",
            label_visibility="collapsed"
        )
    with tmpl_col:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        st.download_button(
            label="⬇ Download Template",
            data=get_template_csv(),
            file_name="ticket_template.csv",
            mime="text/csv",
            key="tmpl_dl",
            use_container_width=True
        )

    upload_error = None
    if uploaded_file is not None:
        df_parsed, error = parse_file(uploaded_file)
        if error:
            upload_error = error
            st.error(error)
        else:
            if st.session_state.df is None or len(df_parsed) != len(st.session_state.df):
                st.session_state.sample_key = None
                sample_contexts = [get_sample_context(k) for k in SAMPLES]
                if st.session_state.context in sample_contexts:
                    st.session_state.context = ""
                st.session_state.df = df_parsed
                st.session_state.result_df = None
                st.session_state.consolidation = None
                st.session_state.mt_df = None

    if st.session_state.df is not None:
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<p style='font-size:15px;font-weight:600;color:#111827;margin:0 0 4px 0'>"
            "What kind of data is this? <span style='color:#ef4444'>*</span>"
            " <span style='font-size:13px;font-weight:400;color:#6b7280'>"
            "(required — helps the LLM categorise accurately)</span></p>",
            unsafe_allow_html=True
        )
        ctx = st.text_input(
            "context",
            value=st.session_state.context,
            placeholder="e.g. Closure notes from an Ads monitoring system",
            label_visibility="collapsed",
            key="ctx_input"
        )
        st.session_state.context = ctx
        if len(ctx.strip()) < 10:
            st.caption("Press Enter after typing to enable the Run button")
        st.success(
            f"✅ {len(st.session_state.df)} rows loaded — ready to proceed")

else:
    # Frozen — show a subtle read-only summary of what's loaded
    if st.session_state.df is not None:
        row_count = len(st.session_state.df)
        data_name = SAMPLES[st.session_state.sample_key]["label"] if st.session_state.sample_key else "Uploaded file"
        ctx_short = st.session_state.context[:80] + "..." if len(
            st.session_state.context) > 80 else st.session_state.context
        st.markdown(
            f"<p style='font-size:13px;color:#9ca3af;margin:6px 0'>"
            f"📁 <strong style='color:#6b7280'>{data_name}</strong> — {row_count} rows"
            f"&nbsp;·&nbsp; {ctx_short}</p>",
            unsafe_allow_html=True
        )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Configure your run
# (always rendered — disabled when frozen to preserve page height)
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.df is not None:

    st.markdown(
        f"<p class='section-title' style='color:{c_title}'>Configure your run</p>",
        unsafe_allow_html=True
    )

    row_count = len(st.session_state.df)

    # Group 1: Category source
    st.markdown(
        f"<p style='font-size:14px;font-weight:600;color:{c_title};margin:0 0 4px 0'>Category source</p>"
        f"<p style='font-size:13px;color:{c_sub};margin:0 0 10px 0'>How should categories be created?</p>",
        unsafe_allow_html=True
    )

    cat_mode = st.radio(
        "Category source",
        options=["No suggestions", "Manual list", "Auto-suggest"],
        index=["no_suggestions", "manual_list", "auto_suggest"].index(
            st.session_state.cat_mode),
        key="cat_mode_radio",
        label_visibility="collapsed",
        disabled=frozen
    )
    cat_mode_key = {
        "No suggestions": "no_suggestions",
        "Manual list": "manual_list",
        "Auto-suggest": "auto_suggest"
    }[cat_mode]

    if not frozen:
        if cat_mode_key != st.session_state.cat_mode:
            st.session_state.as_done = False
            st.session_state.as_cats = []
        st.session_state.cat_mode = cat_mode_key

    mode_descs = {
        "no_suggestions": "The LLM reads all rows and invents category names from the data.",
        "manual_list": "You define the starting taxonomy. The LLM maps to it and can create new buckets if needed.",
        "auto_suggest": "We sample 25% of your rows, propose a taxonomy for you to review, then run."
    }
    st.caption(mode_descs[st.session_state.cat_mode])

    # Manual list expansion — only interactive when not frozen
    if st.session_state.cat_mode == "manual_list" and not frozen:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        manual_input = st.text_area(
            "Your categories — one per line",
            value=st.session_state.manual_cats,
            height=140,
            placeholder="Payment failure\nApp crash\nRefund dispute\nKYC issue\nFraud / unauthorized",
            key="manual_textarea"
        )
        st.session_state.manual_cats = manual_input
        cat_lines = [l.strip() for l in manual_input.split("\n") if l.strip()]
        cat_count = len(cat_lines)
        if cat_count < 2:
            st.caption(
                f"{cat_count} {'category' if cat_count == 1 else 'categories'} — minimum 2 required")
        elif cat_count > 15:
            st.warning(f"{cat_count} categories — maximum is 15.", icon="⚠️")
        else:
            st.caption(f"✅ {cat_count} categories entered")

    elif st.session_state.cat_mode == "manual_list" and frozen:
        # Show what was entered, read-only
        if st.session_state.manual_cats:
            cats_preview = st.session_state.manual_cats[:120] + "..." if len(
                st.session_state.manual_cats) > 120 else st.session_state.manual_cats
            st.markdown(
                f"<p style='font-size:13px;color:#9ca3af;font-family:monospace;margin:4px 0'>{cats_preview}</p>",
                unsafe_allow_html=True
            )

    # Auto-suggest expansion — only interactive when not frozen
    elif st.session_state.cat_mode == "auto_suggest" and not frozen:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if row_count <= 50:
            st.markdown(
                "<div class='box-info'>Auto-suggest requires more than 50 rows. Use No suggestions or Manual list.</div>",
                unsafe_allow_html=True
            )
        elif not st.session_state.as_done:
            st.markdown(
                "<p style='font-size:13px;color:#374151'>We'll sample 25% of your rows and propose a starting taxonomy (~15–20 seconds).</p>",
                unsafe_allow_html=True
            )
            if st.button("Generate suggestions", key="gen_btn"):
                with st.spinner("Sampling and generating taxonomy..."):
                    suggestions = run_auto_suggest(
                        st.session_state.df, st.session_state.context)
                if suggestions:
                    st.session_state.as_cats = suggestions
                    st.session_state.as_done = True
                    st.rerun()
                else:
                    st.error(
                        "Could not generate suggestions — try again or switch to Manual list.")
        else:
            st.markdown(
                "<p style='font-size:13px;font-weight:600;color:#111827;margin:0 0 2px 0'>Suggested taxonomy</p>"
                "<p style='font-size:13px;color:#6b7280;margin:0 0 10px 0'>Rename, delete, or add categories before running.</p>",
                unsafe_allow_html=True
            )
            cats = st.session_state.as_cats
            updated = []
            for idx, cat in enumerate(cats):
                ic, dc = st.columns([9, 1])
                with ic:
                    v = st.text_input(
                        f"c{idx}", value=cat, key=f"asc_{idx}", label_visibility="collapsed")
                    if v.strip():
                        updated.append(v.strip())
                with dc:
                    if st.button("✕", key=f"del_{idx}"):
                        cats.pop(idx)
                        st.session_state.as_cats = cats
                        st.rerun()
            st.session_state.as_cats = updated
            bc, rc, _ = st.columns([2, 2, 4])
            with bc:
                if st.button("+ Add category", key="add_cat"):
                    st.session_state.as_cats.append("")
                    st.rerun()
            with rc:
                if st.button("↺ Re-generate", key="regen"):
                    st.session_state.as_done = False
                    st.session_state.as_cats = []
                    st.rerun()
            valid_as = [c for c in updated if c]
            st.caption(f"✅ {len(valid_as)} categories confirmed" if len(valid_as) >= 2
                       else f"{len(valid_as)} categories — minimum 2 required")

    elif st.session_state.cat_mode == "auto_suggest" and frozen and st.session_state.as_done:
        # Show confirmed taxonomy read-only
        cats_str = ", ".join(st.session_state.as_cats[:5])
        if len(st.session_state.as_cats) > 5:
            cats_str += f" +{len(st.session_state.as_cats)-5} more"
        st.markdown(
            f"<p style='font-size:13px;color:#9ca3af;margin:4px 0'>{cats_str}</p>",
            unsafe_allow_html=True
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Group 2: Analysis depth
    st.markdown(
        f"<p style='font-size:14px;font-weight:600;color:{c_title};margin:0 0 4px 0'>Analysis depth</p>"
        f"<p style='font-size:13px;color:{c_sub};margin:0 0 10px 0'>How many categories per ticket?</p>",
        unsafe_allow_html=True
    )

    depth = st.radio(
        "Analysis depth",
        options=["Primary category only", "Full theme mapping"],
        index=0 if st.session_state.depth == "primary" else 1,
        key="depth_radio",
        label_visibility="collapsed",
        disabled=frozen
    )
    if not frozen:
        st.session_state.depth = "primary" if depth == "Primary category only" else "full"

    depth_descs = {
        "primary": "Each ticket gets one primary category. Fastest — ~60–90 seconds for 100 rows.",
        "full": "Each ticket is mapped to all applicable themes. Adds ~60–90 seconds for the second pass."
    }
    st.caption(depth_descs[st.session_state.depth])

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Run button
    ctx_valid = len(st.session_state.context.strip()) >= 10
    cat_mode_key = st.session_state.cat_mode

    if cat_mode_key == "no_suggestions":
        run_ready = ctx_valid
    elif cat_mode_key == "manual_list":
        ml_cats = [l.strip()
                   for l in st.session_state.manual_cats.split("\n") if l.strip()]
        run_ready = ctx_valid and 2 <= len(ml_cats) <= 15
    elif cat_mode_key == "auto_suggest":
        as_valid = st.session_state.as_done and len(
            [c for c in st.session_state.as_cats if c]) >= 2
        run_ready = ctx_valid and as_valid and row_count > 50
    else:
        run_ready = False

    if not ctx_valid and not frozen:
        st.warning(
            "Enter a data description above (at least 10 characters) before running.", icon="⚠️")

    if st.button("▶ Run", disabled=not run_ready or frozen, type="primary", key="run_btn"):
        st.session_state.stage = "processing"
        st.rerun()

    # Processing — always rendered here, fills in when running, stays complete after
    if stage in ("processing", "results"):
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown("<p class='section-title'>Processing</p>", unsafe_allow_html=True)

        if stage == "results":
            st.progress(1.0)
            st.markdown(
                "<p style='font-size:14px;font-weight:600;color:#0f766e;margin:6px 0'>✅ Complete</p>",
                unsafe_allow_html=True
            )

        elif stage == "processing":
            import time as _time
            from engine import (
                get_client, _build_categorisation_prompt, _call_gemini,
                _parse_batch_response, _apply_bucket_threshold, BATCH_SIZE
            )

            df       = st.session_state.df
            context  = st.session_state.context
            cat_mode = st.session_state.cat_mode
            depth    = st.session_state.depth

            categories = None
            if cat_mode == "manual_list":
                categories = [l.strip() for l in st.session_state.manual_cats.split("\n") if l.strip()]
            elif cat_mode == "auto_suggest":
                categories = [c for c in st.session_state.as_cats if c]

            total_batches = (len(df) + 9) // 10
            total_steps   = total_batches + 1 + (total_batches if depth == "full" else 0)
            step_counter  = [0]

            progress_bar = st.progress(0.0)
            status_el    = st.empty()

            client           = get_client()
            accumulated_cats = list(categories) if categories else []
            result_df        = df.copy()
            result_df["new_category"] = ""
            result_df["confidence"]   = ""
            result_df["reasoning"]    = ""
            rows = result_df.to_dict(orient="records")

            for batch_num in range(total_batches):
                start = batch_num * BATCH_SIZE
                end   = min(start + BATCH_SIZE, len(rows))
                batch = rows[start:end]
                prompt = _build_categorisation_prompt(
                    context=context, mode=cat_mode,
                    accumulated_categories=accumulated_cats, batch=batch
                )
                try:
                    raw     = _call_gemini(client, prompt)
                    results = _parse_batch_response(raw, batch)
                    for i, res in enumerate(results):
                        idx = start + i
                        result_df.at[idx, "new_category"] = res.get("new_category", "Uncategorised")
                        result_df.at[idx, "confidence"]   = res.get("confidence", "Low")
                        result_df.at[idx, "reasoning"]    = res.get("reasoning", "")
                        cat = res.get("new_category", "")
                        if cat and cat != "Uncategorised" and cat not in accumulated_cats:
                            accumulated_cats.append(cat)
                except Exception as e:
                    for i in range(len(batch)):
                        result_df.at[start + i, "new_category"] = "Uncategorised"
                        result_df.at[start + i, "confidence"]   = "Low"
                        result_df.at[start + i, "reasoning"]    = f"Error: {str(e)}"

                current_cats = result_df.iloc[:end]["new_category"].replace("Uncategorised", None).dropna().nunique()
                step_counter[0] += 1
                progress_bar.progress(min(step_counter[0] / total_steps, 1.0))
                status_el.markdown(
                    f"<p style='font-size:14px;color:#374151;margin:6px 0'>"
                    f"Categorising batch {batch_num+1} of {total_batches} — "
                    f"{current_cats} {'category' if current_cats==1 else 'categories'} identified so far</p>",
                    unsafe_allow_html=True
                )
                if batch_num < total_batches - 1:
                    _time.sleep(4)

            result_df = _apply_bucket_threshold(result_df)

            step_counter[0] += 1
            progress_bar.progress(min(step_counter[0] / total_steps, 1.0))
            status_el.markdown(
                "<p style='font-size:14px;color:#374151;margin:6px 0'>Running consolidation pass...</p>",
                unsafe_allow_html=True
            )
            from engine import run_consolidation as _consolidate
            consolidation = _consolidate(result_df, context)
            result_df     = consolidation["df"]

            final_n    = result_df["new_category"].replace("Uncategorised", None).dropna().nunique()
            merge_n    = len(consolidation.get("transparency_log", []))
            merge_note = f", {merge_n} auto-merge{'s' if merge_n!=1 else ''} applied" if merge_n else ""
            status_el.markdown(
                f"<p style='font-size:14px;color:#374151;margin:6px 0'>"
                f"Consolidation complete — {final_n} final categories{merge_note}</p>",
                unsafe_allow_html=True
            )

            mt_df = None
            if depth == "full":
                from engine import _build_multi_tag_prompt, _parse_multi_tag_response
                final_cat_list      = [c for c in result_df["new_category"].unique() if c != "Uncategorised"]
                mt_df               = result_df.copy()
                mt_df["multi_tags"] = ""
                mt_rows             = result_df.to_dict(orient="records")
                for batch_num in range(total_batches):
                    start  = batch_num * BATCH_SIZE
                    end    = min(start + BATCH_SIZE, len(mt_rows))
                    batch  = mt_rows[start:end]
                    prompt = _build_multi_tag_prompt(context=context, categories=final_cat_list, batch=batch)
                    try:
                        raw     = _call_gemini(client, prompt)
                        results = _parse_multi_tag_response(raw, batch)
                        for i, res in enumerate(results):
                            mt_df.at[start+i, "multi_tags"] = " | ".join(res.get("tags", []))
                    except Exception:
                        pass
                    step_counter[0] += 1
                    progress_bar.progress(min(step_counter[0] / total_steps, 1.0))
                    status_el.markdown(
                        f"<p style='font-size:14px;color:#374151;margin:6px 0'>"
                        f"Mapping themes — batch {batch_num+1} of {total_batches} complete</p>",
                        unsafe_allow_html=True
                    )
                    if batch_num < total_batches - 1:
                        _time.sleep(4)

            progress_bar.progress(1.0)
            status_el.markdown(
                "<p style='font-size:14px;font-weight:600;color:#0f766e;margin:6px 0'>✅ Complete</p>",
                unsafe_allow_html=True
            )
            st.session_state.result_df     = result_df
            st.session_state.consolidation = consolidation
            st.session_state.mt_df         = mt_df
            st.session_state.stage         = "results"
            _time.sleep(0.6)
            st.rerun()

    st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════════

if stage == "results" and st.session_state.result_df is not None:

    result_df = st.session_state.result_df
    consolidation = st.session_state.consolidation
    mt_df = st.session_state.mt_df
    total_rows = len(result_df)

    st.markdown(
        f"<p class='section-title'>✅ Results — {total_rows} tickets processed</p>",
        unsafe_allow_html=True
    )

    # Results table
    fc, _ = st.columns([3, 5])
    with fc:
        show_low = st.checkbox(
            "Show Low confidence rows only",
            value=st.session_state.show_low_conf,
            key="lc_toggle"
        )
        st.session_state.show_low_conf = show_low

    display = result_df[result_df["confidence"]
                        == "Low"] if show_low else result_df
    table_rows = []
    for _, row in display.iterrows():
        desc = str(row["issue_description"])
        table_rows.append({
            "Ticket ID":    row["ticket_id"],
            "Description":  desc[:80] + "..." if len(desc) > 80 else desc,
            "Old label":    row["current_label"],
            "New category": row["new_category"],
            "Confidence":   row["confidence"],
            "Reasoning":    row["reasoning"]
        })

    if table_rows:
        st.dataframe(
            pd.DataFrame(table_rows),
            use_container_width=True, hide_index=True,
            column_config={
                "Ticket ID":    st.column_config.TextColumn(width="small"),
                "Description":  st.column_config.TextColumn(width="large"),
                "Old label":    st.column_config.TextColumn(width="medium"),
                "New category": st.column_config.TextColumn(width="medium"),
                "Confidence":   st.column_config.TextColumn(width="small"),
                "Reasoning":    st.column_config.TextColumn(width="large"),
            }
        )
    else:
        st.info("No Low confidence rows found.")

    # Category distribution
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<p class='section-title'>Category Distribution</p>",
                unsafe_allow_html=True)
    cat_counts = result_df["new_category"].value_counts()
    st.plotly_chart(
        make_chart(cat_counts.index.tolist(), cat_counts.values.tolist()),
        use_container_width=True
    )

    # Multi-tag distribution
    all_tags = []
    if mt_df is not None:
        for tags_str in mt_df["multi_tags"]:
            if tags_str:
                all_tags.extend([t.strip() for t in tags_str.split("|")])
        if all_tags:
            tag_counts = Counter(all_tags)
            sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
            st.markdown("<div style='height:8px'></div>",
                        unsafe_allow_html=True)
            st.markdown(
                "<p class='section-title'>Category Distribution — Full theme mapping</p>",
                unsafe_allow_html=True
            )
            st.caption(
                "Each ticket mapped to all applicable themes. "
                "A ticket may appear in multiple bars — counts will exceed total row count."
            )
            st.plotly_chart(
                make_chart(
                    [t[0] for t in sorted_tags], [t[1] for t in sorted_tags],
                    x_label="Theme occurrences (tickets may appear in multiple bars)"
                ),
                use_container_width=True
            )

    # Results Summary
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown("<p class='section-title'>Results Summary</p>",
                unsafe_allow_html=True)

    c_data = consolidation or {}
    narrative = c_data.get("narrative", "")
    summaries = c_data.get("category_summaries", {})
    trans_log = c_data.get("transparency_log", [])
    merge_flags = c_data.get("merge_flags", [])
    uc_analysis = c_data.get("uncategorised_analysis", [])
    uc_count = len(result_df[result_df["new_category"] == "Uncategorised"])

    if narrative:
        st.markdown(
            f"<p style='font-size:15px;color:#111827;line-height:1.7;margin-bottom:16px'>{narrative}</p>",
            unsafe_allow_html=True
        )

    if summaries:
        st.markdown("<p class='summary-label'>Category breakdown</p>",
                    unsafe_allow_html=True)
        rows_b = []
        for cat, summary in summaries.items():
            if cat == "Uncategorised":
                continue
            count = len(result_df[result_df["new_category"] == cat])
            pct = f"{round(count/len(result_df)*100)}%" if len(result_df) else "—"
            rows_b.append({"Category": cat, "Tickets": count,
                          "%": pct, "What it covers": summary})
        if rows_b:
            st.dataframe(
                pd.DataFrame(rows_b), use_container_width=True, hide_index=True,
                column_config={
                    "Category":       st.column_config.TextColumn(width="medium"),
                    "Tickets":        st.column_config.NumberColumn(width="small"),
                    "%":              st.column_config.TextColumn(width="small"),
                    "What it covers": st.column_config.TextColumn(width="large"),
                }
            )

    if trans_log:
        st.markdown("<p class='summary-label'>Auto-merges applied</p>",
                    unsafe_allow_html=True)
        for entry in trans_log:
            st.markdown(
                f"<div class='box-merge'>✓ {entry}</div>", unsafe_allow_html=True)

    if merge_flags:
        st.markdown("<p class='summary-label'>Flags to review</p>",
                    unsafe_allow_html=True)
        for flag in merge_flags:
            st.markdown(
                f"<div class='box-flag'>⚠ {flag}</div>", unsafe_allow_html=True)

    if uc_count == 0:
        st.markdown(
            "<p class='summary-label'>Uncategorised bucket</p>"
            "<p style='font-size:14px;color:#6b7280'>All tickets were categorised with sufficient confidence.</p>",
            unsafe_allow_html=True
        )
    elif uc_analysis:
        st.markdown(
            f"<p class='summary-label'>Uncategorised bucket ({uc_count} tickets)</p>",
            unsafe_allow_html=True
        )
        for obs in uc_analysis:
            st.markdown(
                f"<div class='box-uc'>· {obs}</div>", unsafe_allow_html=True)

    if all_tags:
        top3 = sorted(tag_counts.items(), key=lambda x: -x[1])[:3]
        st.markdown("<p class='summary-label'>Cross-theme signals</p>",
                    unsafe_allow_html=True)
        for cat, count in top3:
            pct = round(count / len(mt_df) * 100)
            st.markdown(
                f"<div class='box-mt'><strong>{cat}</strong> — "
                f"appears across {count} tickets ({pct}%) in multiple themes</div>",
                unsafe_allow_html=True
            )

    # Download + Start over
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    download_df = mt_df if mt_df is not None else result_df.copy()
    if "multi_tags" not in download_df.columns:
        download_df = download_df.copy()
        download_df["multi_tags"] = ""

    dl_col, _, so_col = st.columns([2, 4, 2])
    with dl_col:
        st.download_button(
            label="⬇ Download CSV",
            data=download_df.to_csv(index=False).encode("utf-8"),
            file_name="categorised_tickets.csv",
            mime="text/csv",
            key="dl_btn",
            use_container_width=True
        )
    with so_col:
        if st.button("↺ Start over", key="reset_bottom", use_container_width=True):
            reset_all()
            st.rerun()
