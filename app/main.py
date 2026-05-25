# app/main.py
# llm-issue-categorizer — Streamlit UI
# All modes complete. UI polish applied per M5 review.

import io
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

# ── CSS ────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* Attribution row */
.attr-row {
    font-size: 13px; color: #666;
    margin-top: 2px; margin-bottom: 0;
}
.attr-row a { color: #0f766e; text-decoration: none; margin-right: 10px; }
.attr-row a:hover { text-decoration: underline; }

/* Section divider */
.section-divider { border: none; border-top: 1px solid #e0e0e0; margin: 1.5rem 0; }

/* Data warning */
.data-warning {
    background: #fef9ec; border: 1px solid #f0c060;
    border-radius: 8px; padding: 0.6rem 1rem;
    font-size: 13px; color: #633806; margin-bottom: 0.75rem;
}

/* Results summary card */
.summary-card {
    background: #f8fffe; border: 1px solid #d0ede8;
    border-radius: 10px; padding: 1.1rem 1.25rem;
    margin-bottom: 1rem;
}
.summary-narrative {
    font-size: 14px; color: #1a1a1a;
    line-height: 1.6; margin-bottom: 1rem;
}
.summary-section-title {
    font-size: 12px; font-weight: 600;
    letter-spacing: 0.05em; text-transform: uppercase;
    color: #0f766e; margin: 0.9rem 0 0.4rem 0;
}
.merge-tag {
    background: #e1f5ee; color: #085041;
    padding: 2px 8px; border-radius: 4px;
    font-size: 12px; margin-bottom: 4px;
    display: inline-block;
}
.flag-tag {
    background: #faeeda; color: #633806;
    padding: 6px 10px; border-radius: 4px;
    font-size: 12px; margin-bottom: 4px;
}
.uc-obs {
    font-size: 13px; color: #444;
    padding: 3px 0; border-bottom: 1px solid #eee;
}
.uc-obs:last-child { border-bottom: none; }
.mt-signal {
    background: #f0fdf9; border-left: 3px solid #0f766e;
    padding: 6px 10px; margin-bottom: 4px;
    font-size: 13px; color: #1a1a1a; border-radius: 0 4px 4px 0;
}

/* Locked mode display */
.mode-locked {
    background: #f5f5f5; border: 1px solid #e0e0e0;
    border-radius: 8px; padding: 0.6rem 1rem;
    font-size: 13px; color: #555; margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

TEAL_SHADES = ["#0f766e", "#0d9488",
               "#14b8a6", "#2dd4bf", "#5eead4", "#99f6e4"]
GREY = "#d1d5db"


# ── Session state ──────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "step": 1,
        "sample_key": None,
        "df": None,
        "context": "",
        "mode": "no_suggestions",
        "manual_categories": "",
        "auto_suggest_categories": [],
        "auto_suggest_done": False,
        "result_df": None,
        "consolidation": None,
        "mt_df": None,
        "mt_run_complete": False,
        "show_low_conf_only": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def reset_all():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_chart(categories, counts, x_label="Ticket count"):
    total = sum(counts)
    pcts = [f"{c} ({round(c/total*100)}%)" if total else str(c)
            for c in counts]
    colors = []
    ti = 0
    for cat in categories:
        if cat == "Uncategorised":
            colors.append(GREY)
        else:
            colors.append(TEAL_SHADES[ti % len(TEAL_SHADES)])
            ti += 1
    fig = go.Figure(go.Bar(
        x=counts, y=categories, orientation="h",
        marker_color=colors,
        text=pcts, textposition="outside",
        hovertemplate="%{y}: %{x}<extra></extra>"
    ))
    fig.update_layout(
        xaxis_title=x_label,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=120, t=10, b=40),
        height=max(280, len(categories) * 44),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(size=13)
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


def get_template_csv():
    template = pd.DataFrame(columns=[
        "ticket_id", "issue_description", "current_label", "resolution_notes"
    ])
    return template.to_csv(index=False).encode("utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

col_title, col_reset = st.columns([6, 1])
with col_title:
    st.markdown("## 🗂️ llm-issue-categorizer")
    st.markdown(
        "<p class='attr-row'>Turn vague operational ticket labels into structured product intelligence. "
        "Built by <strong>Saurabh Das</strong> — Senior TPM & Designated PM at Microsoft AI, "
        "documenting an AI learning journey in public.&nbsp;&nbsp;"
        "<a href='https://linkedin.com/in/saurabhdas7' target='_blank'>LinkedIn</a>"
        "<a href='https://github.com/saurabh-das7/llm-issue-categorizer' target='_blank'>GitHub</a>"
        "<a href='https://github.com/saurabh-das7/llm-issue-categorizer' target='_blank'>Project repo</a>"
        "</p>",
        unsafe_allow_html=True
    )
with col_reset:
    st.write("")
    if st.button("↺ Start over", key="reset_btn"):
        reset_all()
        st.rerun()

st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Data input
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("#### Step 1 — Choose your data")
st.markdown("**Try a sample dataset** — loads instantly, no upload needed")

tile_cols = st.columns(3)
for i, key in enumerate(list(SAMPLES.keys())):
    s = SAMPLES[key]
    with tile_cols[i]:
        selected = st.session_state.sample_key == key
        label = f"{s['icon']} **{s['label']}**\n\n{s['row_count']} rows"
        if st.button(label, key=f"tile_{key}",
                     type="primary" if selected else "secondary"):
            st.session_state.sample_key = key
            st.session_state.df = get_sample_df(key)
            st.session_state.context = get_sample_context(key)
            st.session_state.step = 2
            st.session_state.result_df = None
            st.session_state.consolidation = None
            st.session_state.mt_df = None
            st.session_state.mt_run_complete = False
            st.session_state.auto_suggest_done = False
            st.rerun()
        if selected:
            st.caption("✅ Selected")

st.markdown("<br>", unsafe_allow_html=True)
div_cols = st.columns([2, 1, 2])
with div_cols[1]:
    st.markdown(
        "<div style='text-align:center;color:#aaa;font-size:13px'>— or upload your own —</div>",
        unsafe_allow_html=True
    )
st.markdown("<br>", unsafe_allow_html=True)

# Data warning
st.markdown("""
<div class='data-warning'>
⚠️ <strong>Do not upload files containing personal data, customer PII, or confidential
business information.</strong> Data submitted to this tool is processed by the Google
Gemini API and subject to Google's data handling policies.
</div>
""", unsafe_allow_html=True)

# Column requirements note + template download
req_col, tmpl_col = st.columns([4, 1])
with req_col:
    st.markdown(
        "<p style='font-size:13px;color:#555;margin-bottom:4px'>"
        "Required columns: <code>ticket_id</code>, <code>issue_description</code>, "
        "<code>current_label</code> &nbsp;·&nbsp; Optional: <code>resolution_notes</code> "
        "&nbsp;·&nbsp; Max 100 rows &nbsp;·&nbsp; Accepted: CSV, Excel (.xlsx), TXT (pipe-delimited)"
        "</p>",
        unsafe_allow_html=True
    )
with tmpl_col:
    st.download_button(
        label="⬇ Download template",
        data=get_template_csv(),
        file_name="ticket_template.csv",
        mime="text/csv",
        key="tmpl_dl"
    )

uploaded_file = st.file_uploader(
    "Upload your file",
    type=["csv", "xlsx", "txt"],
    key="file_uploader",
    label_visibility="collapsed"
)

upload_error = None
if uploaded_file is not None:
    df, error = parse_file(uploaded_file)
    if error:
        upload_error = error
        st.error(error)
    else:
        st.session_state.sample_key = None
        # Clear sample context when switching to upload
        if st.session_state.context in [
            get_sample_context("upi"),
            get_sample_context("ads"),
            get_sample_context("cop")
        ]:
            st.session_state.context = ""
        st.session_state.df = df
        st.session_state.step = 2
        st.session_state.result_df = None
        st.session_state.consolidation = None
        st.session_state.mt_df = None
        st.session_state.mt_run_complete = False

# Context field — only shown when data loaded and no upload error
if st.session_state.df is not None and upload_error is None:
    ctx = st.text_input(
        "What kind of data is this? *",
        value=st.session_state.context,
        placeholder="e.g. Support tickets for a logistics ops team",
        help="Passed to the LLM with every prompt for domain-aware categorisation.",
        key="ctx_input"
    )
    st.session_state.context = ctx
    row_count = len(st.session_state.df)
    st.success(f"✅ {row_count} rows loaded — ready to proceed")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Mode selection
# ══════════════════════════════════════════════════════════════════════════════

# After run: show locked mode summary
if st.session_state.step >= 2 and st.session_state.result_df is not None:
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    mode_labels = {
        "no_suggestions": "No suggestions",
        "manual_list": "Manual list",
        "auto_suggest": "Auto-suggest"
    }
    chosen = mode_labels.get(st.session_state.mode, st.session_state.mode)
    st.markdown(
        f"<div class='mode-locked'>✅ <strong>Step 2 — Mode:</strong> {chosen}</div>",
        unsafe_allow_html=True
    )

# Before run: show full mode selection UI
elif st.session_state.step >= 2 and st.session_state.df is not None:
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.markdown("#### Step 2 — Choose categorisation mode")

    row_count = len(st.session_state.df)
    as_disabled = row_count <= 50

    mode_options = {
        "no_suggestions": {
            "label": "No suggestions",
            "desc": "LLM reads all rows and generates its own category names. No input needed."
        },
        "manual_list": {
            "label": "Manual list",
            "desc": "You define starting categories. LLM maps to them and creates new buckets as needed."
        },
        "auto_suggest": {
            "label": "Auto-suggest" + (" (requires >50 rows)" if as_disabled else ""),
            "desc": "We sample 25% of your rows and propose a taxonomy for you to review before the full run."
        }
    }

    mode_labels_list = [v["label"] for v in mode_options.values()]
    mode_keys = list(mode_options.keys())

    selected_label = st.radio(
        "Select mode",
        options=mode_labels_list,
        index=mode_keys.index(
            st.session_state.mode) if st.session_state.mode in mode_keys else 0,
        key="mode_radio",
        label_visibility="collapsed"
    )
    selected_mode = mode_keys[mode_labels_list.index(selected_label)]

    if selected_mode != st.session_state.mode:
        st.session_state.auto_suggest_done = False
        st.session_state.auto_suggest_categories = []
    st.session_state.mode = selected_mode
    st.caption(mode_options[selected_mode]["desc"])

    # ── Manual List ────────────────────────────────────────────────────────────
    if selected_mode == "manual_list":
        st.markdown("<br>", unsafe_allow_html=True)
        manual_input = st.text_area(
            "Your categories — one per line",
            value=st.session_state.manual_categories,
            height=160,
            placeholder="Payment failure\nApp crash\nRefund dispute\nKYC issue\nFraud / unauthorized",
            key="manual_textarea"
        )
        st.session_state.manual_categories = manual_input
        cat_lines = [l.strip() for l in manual_input.split("\n") if l.strip()]
        cat_count = len(cat_lines)
        if cat_count < 2:
            st.caption(
                f"{cat_count} {'category' if cat_count == 1 else 'categories'} — minimum 2 required")
        elif cat_count > 15:
            st.warning(
                f"{cat_count} categories — maximum is 15. Please remove some.", icon="⚠️")
        else:
            st.caption(f"✅ {cat_count} categories entered")
        st.caption(
            "The LLM will map tickets to your categories and may create additional "
            "buckets for patterns not covered, provided they have enough tickets."
        )
        context_valid = len(st.session_state.context.strip()) >= 10
        run_ready = 2 <= cat_count <= 15 and context_valid
        if not context_valid:
            st.warning(
                "Please enter a data description above before running.", icon="⚠️")
        if st.button("▶ Run categorisation", disabled=not run_ready,
                     type="primary", key="run_btn_ml"):
            st.session_state.step = 3
            st.rerun()

    # ── Auto-Suggest ───────────────────────────────────────────────────────────
    elif selected_mode == "auto_suggest":
        if as_disabled:
            st.info(
                "Auto-suggest requires more than 50 rows. "
                "Use No suggestions or Manual list instead.",
                icon="ℹ️"
            )
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            if not st.session_state.auto_suggest_done:
                st.markdown(
                    "We'll sample 25% of your tickets and propose a starting taxonomy. "
                    "Takes ~15–20 seconds."
                )
                if st.button("Generate suggestions from your data", key="gen_suggest_btn"):
                    with st.spinner("Sampling tickets and generating taxonomy..."):
                        suggestions = run_auto_suggest(
                            st.session_state.df,
                            st.session_state.context
                        )
                    if suggestions:
                        st.session_state.auto_suggest_categories = suggestions
                        st.session_state.auto_suggest_done = True
                        st.rerun()
                    else:
                        st.error(
                            "Could not generate suggestions — please try again or switch to Manual list.")
            else:
                st.markdown(
                    "**Suggested taxonomy** — rename, delete, or add categories "
                    "before running the full categorisation."
                )
                st.caption(
                    "The LLM can create additional categories during the full run "
                    "for patterns not captured here, as long as they have enough tickets."
                )
                cats = st.session_state.auto_suggest_categories
                updated_cats = []
                for idx, cat in enumerate(cats):
                    col_input, col_del = st.columns([8, 1])
                    with col_input:
                        new_val = st.text_input(
                            f"cat_{idx}",
                            value=cat,
                            key=f"as_cat_{idx}",
                            label_visibility="collapsed"
                        )
                        if new_val.strip():
                            updated_cats.append(new_val.strip())
                    with col_del:
                        if st.button("✕", key=f"del_cat_{idx}"):
                            cats.pop(idx)
                            st.session_state.auto_suggest_categories = cats
                            st.rerun()
                st.session_state.auto_suggest_categories = updated_cats

                if st.button("+ Add category", key="add_cat_btn"):
                    st.session_state.auto_suggest_categories.append("")
                    st.rerun()

                valid_cats = [c for c in updated_cats if c]
                st.markdown("<br>", unsafe_allow_html=True)
                context_valid = len(st.session_state.context.strip()) >= 10
                run_ready = len(valid_cats) >= 2 and context_valid

                col_run, col_regen = st.columns([2, 2])
                with col_run:
                    if st.button("▶ Run full categorisation", disabled=not run_ready,
                                 type="primary", key="run_btn_as"):
                        st.session_state.manual_categories = "\n".join(
                            valid_cats)
                        st.session_state.step = 3
                        st.rerun()
                with col_regen:
                    if st.button("↺ Re-generate suggestions", key="regen_btn"):
                        st.session_state.auto_suggest_done = False
                        st.session_state.auto_suggest_categories = []
                        st.rerun()

    # ── No Suggestions ─────────────────────────────────────────────────────────
    else:
        context_valid = len(st.session_state.context.strip()) >= 10
        if not context_valid:
            st.warning(
                "Please enter a data description (at least 10 characters) before running.",
                icon="⚠️"
            )
        if st.button("▶ Run categorisation", disabled=not context_valid,
                     type="primary", key="run_btn_ns"):
            st.session_state.step = 3
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Processing
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 3 and st.session_state.result_df is None:
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    st.markdown("#### Processing")

    df = st.session_state.df
    context = st.session_state.context
    total_batches = (len(df) + 9) // 10
    estimated_secs = total_batches * 6  # ~6 seconds per batch including sleep

    progress_bar = st.progress(0)
    status_text = st.empty()
    eta_text = st.empty()
    eta_text.caption(f"Estimated time: ~{estimated_secs} seconds")

    def update_progress(batch_num, total):
        pct = batch_num / total
        progress_bar.progress(pct)
        if batch_num == total:
            status_text.markdown("Running final consolidation pass...")
            eta_text.empty()
        else:
            status_text.markdown(
                f"Processing batch **{batch_num}** of **{total}**..."
            )

    mode = st.session_state.mode
    categories = None
    if mode in ("manual_list", "auto_suggest"):
        categories = [
            l.strip() for l in st.session_state.manual_categories.split("\n")
            if l.strip()
        ]

    result_df = run_categorisation(
        df=df, context=context, mode=mode,
        categories=categories, progress_callback=update_progress
    )

    consolidation = run_consolidation(result_df, context)
    result_df = consolidation["df"]

    progress_bar.progress(1.0)
    status_text.markdown("✅ **Complete!**")
    eta_text.empty()

    st.session_state.result_df = result_df
    st.session_state.consolidation = consolidation
    st.session_state.step = 4
    time.sleep(0.4)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Results
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 4 and st.session_state.result_df is not None:
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    result_df = st.session_state.result_df
    consolidation = st.session_state.consolidation
    total_rows = len(result_df)

    # Completion banner
    st.markdown(
        f"#### ✅ Categorisation complete — {total_rows} tickets processed")

    # ── Results table ──────────────────────────────────────────────────────────
    st.markdown("**Results**")
    filter_col, _ = st.columns([3, 5])
    with filter_col:
        show_low = st.checkbox(
            "Show Low confidence rows only",
            value=st.session_state.show_low_conf_only,
            key="low_conf_toggle"
        )
        st.session_state.show_low_conf_only = show_low

    display_df = result_df.copy()
    if show_low:
        display_df = display_df[display_df["confidence"] == "Low"]

    table_rows = []
    for _, row in display_df.iterrows():
        desc = str(row["issue_description"])
        table_rows.append({
            "Ticket ID": row["ticket_id"],
            "Description": desc[:80] + "..." if len(desc) > 80 else desc,
            "Old label": row["current_label"],
            "New category": row["new_category"],
            "Confidence": row["confidence"],
            "Reasoning": row["reasoning"]
        })

    if table_rows:
        st.dataframe(
            pd.DataFrame(table_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticket ID": st.column_config.TextColumn(width="small"),
                "Description": st.column_config.TextColumn(width="large"),
                "Old label": st.column_config.TextColumn(width="medium"),
                "New category": st.column_config.TextColumn(width="medium"),
                "Confidence": st.column_config.TextColumn(width="small"),
                "Reasoning": st.column_config.TextColumn(width="large"),
            }
        )
    else:
        st.info("No Low confidence rows found.")

    # ── Category distribution — single-bucket ──────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Category Distribution**")
    cat_counts = result_df["new_category"].value_counts()
    fig = make_chart(cat_counts.index.tolist(), cat_counts.values.tolist())
    st.plotly_chart(fig, use_container_width=True)

    # ── Category distribution — multi-tag (shown only after multi-tag run) ─────
    if st.session_state.mt_run_complete and st.session_state.mt_df is not None:
        mt_df = st.session_state.mt_df
        all_tags = []
        for tags_str in mt_df["multi_tags"]:
            if tags_str:
                all_tags.extend([t.strip() for t in tags_str.split("|")])
        if all_tags:
            tag_counts = Counter(all_tags)
            sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
            mt_cats = [t[0] for t in sorted_tags]
            mt_cnts = [t[1] for t in sorted_tags]
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("**Category Distribution — Multi-tag view**")
            st.caption(
                "Each ticket mapped to all applicable themes. "
                "A ticket may appear in multiple categories — counts will exceed total row count."
            )
            fig_mt = make_chart(
                mt_cats, mt_cnts,
                x_label="Tag occurrences (tickets may appear in multiple bars)"
            )
            st.plotly_chart(fig_mt, use_container_width=True)

    # ── Results Summary — always shown ─────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Results Summary**")

    c = consolidation or {}
    narrative = c.get("narrative", "")
    summaries = c.get("category_summaries", {})
    transparency_log = c.get("transparency_log", [])
    merge_flags = c.get("merge_flags", [])
    uc_analysis = c.get("uncategorised_analysis", [])

    with st.container():
        st.markdown("<div class='summary-card'>", unsafe_allow_html=True)

        # Narrative
        if narrative:
            st.markdown(
                f"<p class='summary-narrative'>{narrative}</p>",
                unsafe_allow_html=True
            )

        # Category breakdown table
        if summaries:
            st.markdown(
                "<p class='summary-section-title'>Category breakdown</p>",
                unsafe_allow_html=True
            )
            breakdown_rows = []
            for cat, summary in summaries.items():
                if cat == "Uncategorised":
                    continue
                count = len(result_df[result_df["new_category"] == cat])
                total = len(result_df)
                pct = f"{round(count/total*100)}%" if total else "—"
                breakdown_rows.append({
                    "Category": cat,
                    "Tickets": count,
                    "%": pct,
                    "What it covers": summary
                })
            if breakdown_rows:
                st.dataframe(
                    pd.DataFrame(breakdown_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Category": st.column_config.TextColumn(width="medium"),
                        "Tickets": st.column_config.NumberColumn(width="small"),
                        "%": st.column_config.TextColumn(width="small"),
                        "What it covers": st.column_config.TextColumn(width="large"),
                    }
                )

        # Auto-merges
        if transparency_log:
            st.markdown(
                "<p class='summary-section-title'>Auto-merges applied</p>",
                unsafe_allow_html=True
            )
            for entry in transparency_log:
                st.markdown(
                    f"<div class='merge-tag'>✓ {entry}</div><br>",
                    unsafe_allow_html=True
                )

        # Merge flags
        if merge_flags:
            st.markdown(
                "<p class='summary-section-title'>Flags to review</p>",
                unsafe_allow_html=True
            )
            for flag in merge_flags:
                st.markdown(
                    f"<div class='flag-tag'>⚠ {flag}</div>",
                    unsafe_allow_html=True
                )

        # Uncategorised analysis
        uc_count = len(result_df[result_df["new_category"] == "Uncategorised"])
        if uc_count == 0:
            st.markdown(
                "<p class='summary-section-title'>Uncategorised bucket</p>",
                unsafe_allow_html=True
            )
            st.markdown(
                "<p style='font-size:13px;color:#555'>All tickets were categorised with sufficient confidence.</p>",
                unsafe_allow_html=True
            )
        elif uc_analysis:
            st.markdown(
                f"<p class='summary-section-title'>Uncategorised bucket ({uc_count} tickets)</p>",
                unsafe_allow_html=True
            )
            for obs in uc_analysis:
                st.markdown(
                    f"<div class='uc-obs'>· {obs}</div>",
                    unsafe_allow_html=True
                )

        # Cross-theme signals — added after multi-tag run
        if st.session_state.mt_run_complete and st.session_state.mt_df is not None:
            mt_df = st.session_state.mt_df
            all_tags = []
            for tags_str in mt_df["multi_tags"]:
                if tags_str:
                    all_tags.extend([t.strip() for t in tags_str.split("|")])
            if all_tags:
                tag_counts = Counter(all_tags)
                top3 = sorted(tag_counts.items(), key=lambda x: -x[1])[:3]
                st.markdown(
                    "<p class='summary-section-title'>Cross-theme signals (multi-tag)</p>",
                    unsafe_allow_html=True
                )
                for cat, count in top3:
                    pct = round(count / len(mt_df) * 100)
                    st.markdown(
                        f"<div class='mt-signal'><strong>{cat}</strong> — "
                        f"appears in {count} tickets ({pct}%) across multiple categories</div>",
                        unsafe_allow_html=True
                    )
        elif not st.session_state.mt_run_complete:
            st.markdown(
                "<p style='font-size:12px;color:#999;margin-top:0.75rem'>"
                "Run the multi-tag analysis below to see cross-theme signals.</p>",
                unsafe_allow_html=True
            )

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Multi-tag run button ───────────────────────────────────────────────────
    if not st.session_state.mt_run_complete:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Advanced multi-tag view**")
        st.caption(
            "Map each ticket to all applicable themes — not just the primary one. "
            "Adds ~60–90 seconds."
        )
        if st.button("Run advanced multi-tag view", key="mt_run_btn"):
            with st.spinner("Running multi-tag analysis..."):
                final_cats = [
                    c for c in result_df["new_category"].unique()
                    if c != "Uncategorised"
                ]
                mt_df = run_multi_tag(
                    df=result_df,
                    context=st.session_state.context,
                    categories=final_cats
                )
                st.session_state.mt_df = mt_df
                st.session_state.mt_run_complete = True
                st.rerun()

    # ── Download CSV ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state.mt_df is not None:
        download_df = st.session_state.mt_df
    else:
        download_df = result_df.copy()
        if "multi_tags" not in download_df.columns:
            download_df["multi_tags"] = ""

    csv_bytes = download_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download CSV",
        data=csv_bytes,
        file_name="categorised_tickets.csv",
        mime="text/csv",
        key="dl_bottom"
    )
