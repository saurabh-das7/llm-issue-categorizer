# app/main.py
# llm-issue-categorizer — Streamlit UI
# M2: primary flow (sample tiles, upload, No Suggestions mode, results)
# M3 adds: Manual List, Auto-Suggest modes
# M4 adds: Review panel, Multi-tag view

import io
import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import parse_file, run_categorisation, run_consolidation, run_multi_tag, run_auto_suggest
from samples import SAMPLES, get_sample_df, get_sample_context

# ── Page configuration ─────────────────────────────────────────────────────────

st.set_page_config(
    page_title="llm-issue-categorizer",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── CSS ────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Tighten default Streamlit padding */
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    /* Sample tile styling */
    div[data-testid="column"] .stButton button {
        width: 100%;
        height: auto;
        padding: 1rem;
        text-align: left;
        white-space: normal;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background: white;
    }
    div[data-testid="column"] .stButton button:hover {
        border-color: #0f766e;
        background: #f0fdf9;
    }

    /* Confidence badge colours */
    .badge-high {
        background: #e1f5ee; color: #085041;
        padding: 2px 8px; border-radius: 12px;
        font-size: 12px; font-weight: 500;
    }
    .badge-medium {
        background: #faeeda; color: #633806;
        padding: 2px 8px; border-radius: 12px;
        font-size: 12px; font-weight: 500;
    }
    .badge-low {
        background: #fcebeb; color: #501313;
        padding: 2px 8px; border-radius: 12px;
        font-size: 12px; font-weight: 500;
    }

    /* Section divider */
    .section-divider {
        border: none; border-top: 1px solid #e0e0e0;
        margin: 1.5rem 0;
    }

    /* Data warning box */
    .data-warning {
        background: #fef9ec; border: 1px solid #f0c060;
        border-radius: 8px; padding: 0.75rem 1rem;
        font-size: 13px; color: #633806;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ── Session state initialisation ───────────────────────────────────────────────

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
        "show_low_conf_only": False,
        "mt_run_complete": False,
        "view": "single",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_state()


def reset_all():
    """Reset all session state and return to Step 1."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()


# ── Header ─────────────────────────────────────────────────────────────────────

col_title, col_reset = st.columns([6, 1])
with col_title:
    st.markdown("## 🗂️ llm-issue-categorizer")
    st.caption("Turn vague operational ticket labels into structured product intelligence")
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

# ── Sample tiles ───────────────────────────────────────────────────────────────

st.markdown("**Try a sample dataset** — loads instantly, no upload needed")

tile_cols = st.columns(3)
sample_keys = list(SAMPLES.keys())

for i, key in enumerate(sample_keys):
    s = SAMPLES[key]
    with tile_cols[i]:
        selected = st.session_state.sample_key == key
        label = f"{s['icon']} **{s['label']}**\n\n{s['row_count']} rows"
        if st.button(label, key=f"tile_{key}", type="primary" if selected else "secondary"):
            st.session_state.sample_key = key
            st.session_state.df = get_sample_df(key)
            st.session_state.context = get_sample_context(key)
            st.session_state.step = 2
            # Reset downstream state
            st.session_state.result_df = None
            st.session_state.consolidation = None
            st.session_state.mt_df = None
            st.session_state.mt_run_complete = False
            st.rerun()
        if selected:
            st.caption("✅ Selected")

# ── Divider ────────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)
div_cols = st.columns([2, 1, 2])
with div_cols[1]:
    st.markdown("<div style='text-align:center;color:#aaa;font-size:13px'>— or upload your own —</div>",
                unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ── Upload zone ────────────────────────────────────────────────────────────────

st.markdown("""
<div class='data-warning'>
⚠️ <strong>Do not upload files containing personal data, customer PII, or confidential 
business information.</strong> Data submitted to this tool is processed by the Google 
Gemini API and subject to Google's data handling policies.
</div>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Upload a CSV, Excel (.xlsx), or TXT (pipe-delimited) file — max 100 rows",
    type=["csv", "xlsx", "txt"],
    key="file_uploader"
)

if uploaded_file is not None:
    df, error = parse_file(uploaded_file)
    if error:
        st.error(error)
    else:
        st.session_state.sample_key = None
        st.session_state.df = df
        # Clear context so user must enter their own
        if st.session_state.context == get_sample_context("upi") or \
           st.session_state.context == get_sample_context("ads") or \
           st.session_state.context == get_sample_context("cop"):
            st.session_state.context = ""
        st.session_state.step = 2
        st.session_state.result_df = None
        st.session_state.consolidation = None
        st.session_state.mt_df = None
        st.session_state.mt_run_complete = False

# Context field — always shown once file or sample is loaded
if st.session_state.df is not None:
    ctx = st.text_input(
        "What kind of data is this? *",
        value=st.session_state.context,
        placeholder="e.g. Support tickets for a logistics ops team",
        help="Passed to the LLM with every prompt for domain-aware categorisation.",
        key="ctx_input"
    )
    st.session_state.context = ctx

    if st.session_state.df is not None:
        row_count = len(st.session_state.df)
        st.success(f"✅ {row_count} rows loaded — ready to proceed")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Mode selection
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 2 and st.session_state.df is not None and st.session_state.result_df is None:

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
            "desc": "We sample 25% of your rows and propose a taxonomy for you to review before the full run.",
        }
    }

    mode_labels = [v["label"] for v in mode_options.values()]
    mode_keys = list(mode_options.keys())

    selected_mode_label = st.radio(
        "Select mode",
        options=mode_labels,
        index=mode_keys.index(st.session_state.mode) if st.session_state.mode in mode_keys else 0,
        key="mode_radio",
        label_visibility="collapsed"
    )
    selected_mode = mode_keys[mode_labels.index(selected_mode_label)]

    # Reset auto-suggest state if mode changed away from it
    if selected_mode != st.session_state.mode:
        st.session_state.auto_suggest_done = False
        st.session_state.auto_suggest_categories = []

    st.session_state.mode = selected_mode
    st.caption(mode_options[selected_mode]["desc"])

    # ── Manual List configuration ──────────────────────────────────────────────
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

        # Parse and validate
        cat_lines = [l.strip() for l in manual_input.split("\n") if l.strip()]
        cat_count = len(cat_lines)

        if cat_count == 0:
            st.caption("0 categories — minimum 2 required")
        elif cat_count == 1:
            st.caption("1 category — minimum 2 required")
        elif cat_count > 15:
            st.warning(f"{cat_count} categories entered — maximum is 15. Please remove some.", icon="⚠️")
        else:
            st.caption(f"✅ {cat_count} categories entered")

        st.caption(
            "The LLM will map tickets to your categories and may create additional "
            "categories for patterns not covered, provided they have enough tickets."
        )

        context_valid = len(st.session_state.context.strip()) >= 10
        run_ready = cat_count >= 2 and cat_count <= 15 and context_valid
        if not context_valid:
            st.warning("Please enter a data description above before running.", icon="⚠️")

        if st.button("▶ Run categorisation", disabled=not run_ready,
                     type="primary", key="run_btn_ml"):
            st.session_state.step = 3
            st.rerun()

    # ── Auto-Suggest configuration ─────────────────────────────────────────────
    elif selected_mode == "auto_suggest":
        if as_disabled:
            st.info(
                "Auto-suggest requires more than 50 rows to sample meaningfully. "
                "Your dataset has fewer rows — please use No suggestions or Manual list instead.",
                icon="ℹ️"
            )
        else:
            st.markdown("<br>", unsafe_allow_html=True)

            if not st.session_state.auto_suggest_done:
                # Pre-generation state
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
                            "Could not generate suggestions — please try again or "
                            "switch to Manual list mode."
                        )
            else:
                # Post-generation: editable category list
                st.markdown(
                    "**Suggested taxonomy** — rename, delete, or add categories "
                    "before running the full categorisation."
                )
                st.caption(
                    "The LLM can create additional categories during the full run "
                    "for patterns not captured here, as long as they have enough tickets."
                )

                # Render editable list using session state
                cats = st.session_state.auto_suggest_categories
                updated_cats = []

                for idx, cat in enumerate(cats):
                    col_input, col_del = st.columns([8, 1])
                    with col_input:
                        new_val = st.text_input(
                            f"Category {idx + 1}",
                            value=cat,
                            key=f"as_cat_{idx}",
                            label_visibility="collapsed"
                        )
                        if new_val.strip():
                            updated_cats.append(new_val.strip())
                    with col_del:
                        if st.button("✕", key=f"del_cat_{idx}"):
                            # Remove this category and rerun
                            cats.pop(idx)
                            st.session_state.auto_suggest_categories = cats
                            st.rerun()

                st.session_state.auto_suggest_categories = updated_cats

                # Add category
                if st.button("+ Add category", key="add_cat_btn"):
                    st.session_state.auto_suggest_categories.append("")
                    st.rerun()

                # Validation and run
                valid_cats = [c for c in updated_cats if c]
                cat_count = len(valid_cats)
                st.markdown("<br>", unsafe_allow_html=True)

                if cat_count < 2:
                    st.warning("Please keep at least 2 categories.", icon="⚠️")

                context_valid = len(st.session_state.context.strip()) >= 10
                run_ready = cat_count >= 2 and context_valid

                if st.button("▶ Run full categorisation", disabled=not run_ready,
                             type="primary", key="run_btn_as"):
                    st.session_state.manual_categories = "\n".join(valid_cats)
                    st.session_state.mode = "auto_suggest"
                    st.session_state.step = 3
                    st.rerun()

                if st.button("↺ Re-generate suggestions", key="regen_btn"):
                    st.session_state.auto_suggest_done = False
                    st.session_state.auto_suggest_categories = []
                    st.rerun()

    # ── No Suggestions run button ──────────────────────────────────────────────
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
    total_batches = (len(df) + 9) // 10  # ceiling division by batch size 10

    progress_bar = st.progress(0)
    status_text = st.empty()
    eta_text = st.empty()

    start_time = time.time()

    def update_progress(batch_num, total):
        pct = batch_num / total
        progress_bar.progress(pct)
        elapsed = time.time() - start_time
        if batch_num > 0:
            rate = elapsed / batch_num
            remaining = rate * (total - batch_num)
            eta_text.caption(f"Estimated time remaining: ~{int(remaining)} seconds")
        if batch_num == total:
            status_text.markdown(f"Running final consolidation pass...")
        else:
            status_text.markdown(f"Processing batch **{batch_num}** of **{total}**...")

    # Determine categories to pass based on mode
    mode = st.session_state.mode
    if mode in ("manual_list", "auto_suggest"):
        categories = [
            l.strip() for l in st.session_state.manual_categories.split("\n")
            if l.strip()
        ]
    else:
        categories = None

    # Run categorisation
    result_df = run_categorisation(
        df=df,
        context=context,
        mode=mode,
        categories=categories,
        progress_callback=update_progress
    )

    # Run consolidation
    consolidation = run_consolidation(result_df, context)
    result_df = consolidation["df"]  # apply any auto-merges

    progress_bar.progress(1.0)
    status_text.markdown("✅ **Complete!**")
    eta_text.empty()

    st.session_state.result_df = result_df
    st.session_state.consolidation = consolidation
    st.session_state.step = 4
    time.sleep(0.5)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Results
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 4 and st.session_state.result_df is not None:

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    result_df = st.session_state.result_df
    consolidation = st.session_state.consolidation
    total_rows = len(result_df)

    # ── Completion banner + download ───────────────────────────────────────────

    banner_col, dl_col = st.columns([5, 1])
    with banner_col:
        st.markdown(f"#### ✅ Categorisation complete — {total_rows} tickets processed")
    with dl_col:
        csv_bytes = result_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="categorised_tickets.csv",
            mime="text/csv",
            key="dl_top"
        )

    # ── Results table ──────────────────────────────────────────────────────────

    st.markdown("**Results**")

    filter_col, _ = st.columns([2, 4])
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

    # Build display table
    table_data = []
    for _, row in display_df.iterrows():
        desc = str(row["issue_description"])
        desc_short = desc[:80] + "..." if len(desc) > 80 else desc
        conf = row["confidence"]
        badge_class = f"badge-{conf.lower()}"
        table_data.append({
            "Ticket ID": row["ticket_id"],
            "Description": desc_short,
            "Old label": row["current_label"],
            "New category": row["new_category"],
            "Confidence": conf,
            "Reasoning": row["reasoning"]
        })

    if table_data:
        st.dataframe(
            pd.DataFrame(table_data),
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

    # ── Bar chart ──────────────────────────────────────────────────────────────

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Category distribution**")

    cat_counts = result_df["new_category"].value_counts()
    categories = cat_counts.index.tolist()
    counts = cat_counts.values.tolist()
    total = sum(counts)
    pcts = [f"{c} ({round(c/total*100)}%)" for c in counts]

    # Colour: teal for named categories, grey for Uncategorised
    colors = []
    teal_shades = ["#0f766e", "#0d9488", "#14b8a6", "#2dd4bf", "#5eead4", "#99f6e4"]
    teal_idx = 0
    for cat in categories:
        if cat == "Uncategorised":
            colors.append("#d1d5db")
        else:
            colors.append(teal_shades[teal_idx % len(teal_shades)])
            teal_idx += 1

    fig = go.Figure(go.Bar(
        x=counts,
        y=categories,
        orientation="h",
        marker_color=colors,
        text=pcts,
        textposition="outside",
        hovertemplate="%{y}: %{x} tickets<extra></extra>"
    ))

    fig.update_layout(
        xaxis_title="Ticket count",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=120, t=10, b=40),
        height=max(300, len(categories) * 45),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(size=13)
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")

    st.plotly_chart(fig, use_container_width=True)

    # ── Review panel ───────────────────────────────────────────────────────────

    with st.expander("📋 Review before downloading", expanded=False):

        # Transparency log
        st.markdown("**Transparency log**")
        if consolidation and consolidation.get("transparency_log"):
            for entry in consolidation["transparency_log"]:
                st.markdown(f"✓ {entry}")
        else:
            st.markdown("*No categories were merged — all categories were sufficiently distinct.*")

        st.markdown("---")

        # Category summaries
        st.markdown("**Category summaries**")
        if consolidation and consolidation.get("category_summaries"):
            for cat, summary in consolidation["category_summaries"].items():
                if cat != "Uncategorised":
                    st.markdown(f"**{cat}** — {summary}")
        else:
            st.markdown("*Summaries not available.*")

        st.markdown("---")

        # Merge flags
        if consolidation and consolidation.get("merge_flags"):
            st.markdown("**Merge flags**")
            for flag in consolidation["merge_flags"]:
                st.warning(f"⚠ {flag}", icon=None)
            st.markdown("---")

        # Uncategorised analysis
        st.markdown("**Uncategorised bucket analysis**")
        uc_count = len(result_df[result_df["new_category"] == "Uncategorised"])
        if uc_count == 0:
            st.markdown("*All tickets were categorised with sufficient confidence.*")
        elif consolidation and consolidation.get("uncategorised_analysis"):
            st.markdown(f"*{uc_count} tickets in Uncategorised bucket. Themes observed:*")
            for obs in consolidation["uncategorised_analysis"]:
                st.markdown(f"· {obs}")
        else:
            st.markdown(f"*{uc_count} tickets in Uncategorised bucket.*")

    # ── Multi-tag section ──────────────────────────────────────────────────────

    st.markdown("<br>", unsafe_allow_html=True)

    if not st.session_state.mt_run_complete:
        mt_col, _ = st.columns([3, 3])
        with mt_col:
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
    else:
        # Show multi-tag results
        st.markdown("**Multi-tag view**")
        st.caption(
            "Each ticket mapped to all applicable themes. "
            "A ticket may appear in multiple categories — counts will exceed total row count."
        )

        view_toggle = st.radio(
            "View",
            ["Single-bucket", "Multi-tag"],
            horizontal=True,
            key="view_toggle"
        )

        if view_toggle == "Multi-tag" and st.session_state.mt_df is not None:
            mt_df = st.session_state.mt_df

            # Explode multi_tags for distribution
            all_tags = []
            for tags_str in mt_df["multi_tags"]:
                if tags_str:
                    all_tags.extend([t.strip() for t in tags_str.split("|")])

            if all_tags:
                from collections import Counter
                tag_counts = Counter(all_tags)
                mt_cats = list(tag_counts.keys())
                mt_cnts = list(tag_counts.values())
                mt_total = len(result_df)

                mt_colors = []
                teal_idx2 = 0
                for cat in mt_cats:
                    if cat == "Uncategorised":
                        mt_colors.append("#d1d5db")
                    else:
                        mt_colors.append(teal_shades[teal_idx2 % len(teal_shades)])
                        teal_idx2 += 1

                fig_mt = go.Figure(go.Bar(
                    x=mt_cnts,
                    y=mt_cats,
                    orientation="h",
                    marker_color=mt_colors,
                    text=[f"{c}" for c in mt_cnts],
                    textposition="outside",
                    hovertemplate="%{y}: %{x} tag occurrences<extra></extra>"
                ))
                fig_mt.update_layout(
                    xaxis_title="Tag occurrences (tickets may appear in multiple bars)",
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=0, r=80, t=10, b=40),
                    height=max(300, len(mt_cats) * 45),
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    font=dict(size=13)
                )
                fig_mt.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
                st.plotly_chart(fig_mt, use_container_width=True)

            # Show multi-tag table
            mt_table = mt_df[["ticket_id", "issue_description", "new_category", "multi_tags"]].copy()
            mt_table.columns = ["Ticket ID", "Description", "Primary category", "All tags"]
            st.dataframe(mt_table, use_container_width=True, hide_index=True)

    # ── Bottom download ────────────────────────────────────────────────────────

    st.markdown("<br>", unsafe_allow_html=True)

    # Include multi_tags column if multi-tag was run
    if st.session_state.mt_df is not None:
        download_df = st.session_state.mt_df
    else:
        download_df = result_df
        if "multi_tags" not in download_df.columns:
            download_df = download_df.copy()
            download_df["multi_tags"] = ""

    csv_bytes_bottom = download_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_bytes_bottom,
        file_name="categorised_tickets.csv",
        mime="text/csv",
        key="dl_bottom"
    )