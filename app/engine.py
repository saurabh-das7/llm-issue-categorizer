# app/engine.py
# Categorisation engine for llm-issue-categorizer
# Built in Milestone 1 — functions added one at a time

import os
import json
import time
import pandas as pd
from google import genai

# ── Model configuration ────────────────────────────────────────────────────────

MODEL = "gemini-3.1-flash-lite"
BATCH_SIZE = 10
MIN_BUCKET_THRESHOLD = 5  # minimum rows for a named category to survive

# ── Gemini client ──────────────────────────────────────────────────────────────


def get_client():
    """
    Initialise and return the Gemini client.
    Reads GOOGLE_API_KEY_V2 from environment (injected by Codespaces secret
    and Streamlit secrets in production).
    """
    api_key = os.environ.get("GOOGLE_API_KEY_V2")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY_V2 not found in environment. "
            "Check Codespaces secrets or Streamlit secrets configuration."
        )
    return genai.Client(api_key=api_key)


# ── Function 1: parse_file ─────────────────────────────────────────────────────

def parse_file(file):
    """
    Parse an uploaded file (CSV, Excel, or TXT) into a clean DataFrame.

    Parameters:
        file: file object from Streamlit's st.file_uploader

    Returns:
        (df, error): tuple where
            - df is a clean pandas DataFrame if successful, None if failed
            - error is a plain-English error string if failed, None if successful

    Column behaviour:
        - Column names are lowercased and whitespace-stripped on import
        - Required columns: ticket_id, issue_description, current_label
        - Optional column: resolution_notes (added as empty string if missing)
        - Row limit: 100 rows maximum (not including header)
    """
    REQUIRED_COLUMNS = {"ticket_id", "issue_description", "current_label"}
    MAX_ROWS = 100

    try:
        filename = file.name.lower()

        # ── Read file based on extension ───────────────────────────────────────
        if filename.endswith(".csv"):
            df = pd.read_csv(file)

        elif filename.endswith(".xlsx"):
            df = pd.read_excel(file, engine="openpyxl")

        elif filename.endswith(".txt"):
            # Expected format: pipe-delimited
            # ticket_id | issue_description | current_label | resolution_notes
            df = pd.read_csv(file, sep="|")

        else:
            return None, (
                f"Unsupported file format: '{file.name}'. "
                "Please upload a CSV, Excel (.xlsx), or TXT (pipe-delimited) file."
            )

        # ── Normalise column names ─────────────────────────────────────────────
        df.columns = [col.strip().lower().replace(" ", "_")
                      for col in df.columns]

        # ── Check required columns ─────────────────────────────────────────────
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            missing_display = ", ".join(sorted(missing))
            return None, (
                f"Missing required column(s): {missing_display}. "
                "Please check your file and re-upload."
            )

        # ── Add optional column if missing ─────────────────────────────────────
        if "resolution_notes" not in df.columns:
            df["resolution_notes"] = ""

        # ── Drop completely empty rows ─────────────────────────────────────────
        df = df.dropna(subset=["issue_description"])
        df = df.reset_index(drop=True)

        # ── Row count check ────────────────────────────────────────────────────
        if len(df) == 0:
            return None, "No data rows found in this file. Please check the file and re-upload."

        if len(df) > MAX_ROWS:
            return None, (
                f"This file has {len(df)} rows. "
                f"The tool supports up to {MAX_ROWS} rows. "
                "Please trim the file and re-upload."
            )

        # ── Clean up data ──────────────────────────────────────────────────────
        for col in ["ticket_id", "issue_description", "current_label", "resolution_notes"]:
            df[col] = df[col].fillna("").astype(str).str.strip()

        return df, None

    except Exception as e:
        return None, f"Could not read the file: {str(e)}. Please check the format and try again."


# ── Function 2: run_categorisation ────────────────────────────────────────────

def run_categorisation(df, context, mode, categories=None, progress_callback=None):
    """
    Run LLM categorisation on all rows in batches of BATCH_SIZE.

    Parameters:
        df: clean DataFrame from parse_file()
        context: one-line description of the data type (str)
        mode: "no_suggestions" | "manual_list" | "auto_suggest"
        categories: list of category name strings (for manual_list and auto_suggest)
                    None for no_suggestions mode
        progress_callback: optional function(batch_num, total_batches) called
                           after each batch completes

    Returns:
        df: original DataFrame with three new columns appended:
            - new_category (str)
            - confidence (str: High | Medium | Low)
            - reasoning (str)
    """
    client = get_client()

    df = df.copy()
    df["new_category"] = ""
    df["confidence"] = ""
    df["reasoning"] = ""

    # Accumulated category list grows as batches are processed
    accumulated_categories = list(categories) if categories else []

    rows = df.to_dict(orient="records")
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(rows))
        batch = rows[start:end]

        prompt = _build_categorisation_prompt(
            context=context,
            mode=mode,
            accumulated_categories=accumulated_categories,
            batch=batch
        )

        try:
            response = _call_gemini(client, prompt)
            results = _parse_batch_response(response, batch)

            for i, result in enumerate(results):
                row_idx = start + i
                df.at[row_idx, "new_category"] = result.get(
                    "new_category", "Uncategorised")
                df.at[row_idx, "confidence"] = result.get("confidence", "Low")
                df.at[row_idx, "reasoning"] = result.get("reasoning", "")

                # Add new categories to accumulated list
                cat = result.get("new_category", "")
                if cat and cat != "Uncategorised" and cat not in accumulated_categories:
                    accumulated_categories.append(cat)

        except Exception as e:
            # Batch failed — mark rows, continue
            for i in range(len(batch)):
                row_idx = start + i
                df.at[row_idx, "new_category"] = "Uncategorised"
                df.at[row_idx, "confidence"] = "Low"
                df.at[row_idx, "reasoning"] = f"Processing error: {str(e)}"

        if progress_callback:
            progress_callback(batch_num + 1, total_batches)

        # Respect RPM limit between batches
        if batch_num < total_batches - 1:
            time.sleep(4)

    # Collapse under-threshold categories into Uncategorised
    df = _apply_bucket_threshold(df)

    return df


# ── Function 3: run_consolidation ─────────────────────────────────────────────

def run_consolidation(df, context):
    """
    Single post-categorisation LLM pass:
      Stage A — generate one-line summary per category
      Stage B — auto-merge high-confidence near-duplicates,
                flag uncertain merges for user review,
                analyse Uncategorised bucket

    Parameters:
        df: annotated DataFrame from run_categorisation()
        context: one-line description of the data type (str)

    Returns:
        dict with keys:
            - transparency_log: list of merge strings auto-applied
            - category_summaries: dict of {category_name: one_liner}
            - merge_flags: list of uncertain merge suggestion strings
            - uncategorised_analysis: list of theme observation strings
            - df: updated DataFrame with auto-merges applied
    """
    client = get_client()

    category_counts = df["new_category"].value_counts().to_dict()

    # Sample up to 3 tickets per category
    category_samples = {}
    for cat in category_counts:
        sample_rows = df[df["new_category"] == cat].head(3)
        category_samples[cat] = [
            {
                "description": row["issue_description"],
                "reasoning": row["reasoning"]
            }
            for _, row in sample_rows.iterrows()
        ]

    # Uncategorised rows for bucket analysis
    uncategorised_rows = df[df["new_category"] == "Uncategorised"]
    uncategorised_samples = [
        row["issue_description"]
        for _, row in uncategorised_rows.head(10).iterrows()
    ]

    prompt = _build_consolidation_prompt(
        context=context,
        category_counts=category_counts,
        category_samples=category_samples,
        uncategorised_samples=uncategorised_samples
    )

    try:
        response = _call_gemini(client, prompt)
        result = _parse_consolidation_response(response)
    except Exception as e:
        return {
            "transparency_log": [],
            "category_summaries": {cat: "" for cat in category_counts},
            "merge_flags": [],
            "uncategorised_analysis": [f"Analysis unavailable: {str(e)}"],
            "df": df
        }

    # Apply auto-merges to DataFrame
    merges = result.get("auto_merges", [])
    transparency_log = []
    summaries = result.get("category_summaries", {})

    for merge in merges:
        source_cats = merge.get("merge_these", [])
        target_cat = merge.get("into", "")
        if not source_cats or not target_cat:
            continue

        affected = df["new_category"].isin(source_cats)
        count = int(affected.sum())
        if count > 0:
            df.loc[affected, "new_category"] = target_cat
            merged_labels = " + ".join(f"'{c}'" for c in source_cats)
            transparency_log.append(
                f"Merged: {merged_labels} → '{target_cat}' ({count} tickets)"
            )

            # Build a summary for the merged category from source summaries
            # so the UI always has a description for every final category
            if target_cat not in summaries:
                source_summaries = [
                    summaries[c] for c in source_cats if c in summaries
                ]
                if source_summaries:
                    summaries[target_cat] = " / ".join(source_summaries)

            # Remove the source category summaries — they no longer exist
            for c in source_cats:
                summaries.pop(c, None)

    result["category_summaries"] = summaries
    result["transparency_log"] = transparency_log
    result["df"] = df

    return result


# ── Function 4: run_multi_tag ──────────────────────────────────────────────────

def run_multi_tag(df, context, categories, progress_callback=None):
    """
    Second LLM pass mapping each ticket to ALL applicable categories.

    Parameters:
        df: annotated DataFrame from run_categorisation()
        context: one-line description of the data type (str)
        categories: list of final category names from the main run
        progress_callback: optional function(batch_num, total_batches)

    Returns:
        df: DataFrame with multi_tags column added (pipe-separated)
    """
    client = get_client()

    df = df.copy()
    df["multi_tags"] = ""

    rows = df.to_dict(orient="records")
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(rows))
        batch = rows[start:end]

        prompt = _build_multi_tag_prompt(
            context=context,
            categories=categories,
            batch=batch
        )

        try:
            response = _call_gemini(client, prompt)
            results = _parse_multi_tag_response(response, batch)

            for i, result in enumerate(results):
                row_idx = start + i
                tags = result.get("tags", [])
                df.at[row_idx, "multi_tags"] = " | ".join(tags)

        except Exception as e:
            for i in range(len(batch)):
                row_idx = start + i
                df.at[row_idx, "multi_tags"] = ""

        if progress_callback:
            progress_callback(batch_num + 1, total_batches)

        if batch_num < total_batches - 1:
            time.sleep(4)

    return df


# ── Function 5: run_auto_suggest ──────────────────────────────────────────────

def run_auto_suggest(df, context):
    """
    Sample 25% of rows and ask the LLM to propose a starting taxonomy.
    Used in Auto-Suggest mode before the full categorisation run.

    Parameters:
        df: clean DataFrame from parse_file()
        context: one-line description of the data type (str)

    Returns:
        list of suggested category name strings
    """
    client = get_client()

    # Sample 25% — minimum 13 rows, maximum 25 rows
    sample_size = max(13, min(25, int(len(df) * 0.25)))
    sample_df = df.sample(n=sample_size, random_state=42)

    rows = sample_df.to_dict(orient="records")
    ticket_lines = []
    for row in rows:
        ticket_lines.append(
            f"- {row['issue_description']} "
            f"[current label: {row['current_label']}]"
        )
    tickets_section = "\n".join(ticket_lines)

    prompt = f"""You are helping a PM categorise operational support tickets.

Context: {context}

Below is a sample of {sample_size} tickets from a dataset. Based on these tickets,
propose a taxonomy of 5-10 distinct category names that would cover the full dataset.

Requirements:
- Each category should be distinct and non-overlapping
- Names should be clear and descriptive (3-6 words each)
- Cover the major issue types visible in this sample
- Anticipate patterns that may exist in the full dataset beyond this sample

Sample tickets:
{tickets_section}

Return a JSON array of category name strings only — no other text, no markdown fences:
["Category One", "Category Two", ...]"""

    try:
        response = _call_gemini(client, prompt)
        cleaned = _clean_json_response(response)
        categories = json.loads(cleaned)
        # Ensure it's a flat list of strings
        if isinstance(categories, list):
            return [str(c).strip() for c in categories if c]
        return []
    except Exception:
        return []


# ── Prompt builders ────────────────────────────────────────────────────────────

def _build_categorisation_prompt(context, mode, accumulated_categories, batch):
    """Build the batch categorisation prompt."""

    categories_section = ""
    if accumulated_categories:
        cat_list = "\n".join(f"  - {c}" for c in accumulated_categories)
        categories_section = f"\nCategories identified so far (reuse these where they fit):\n{cat_list}\n"

    if mode == "no_suggestions":
        new_category_rule = (
            "Create clear, specific category names that describe the issue type. "
            "Reuse existing categories from the list above wherever they fit. "
            "Create a new category only when the issue is genuinely distinct "
            "from all existing ones. Use 'Uncategorised' only when there is "
            "genuinely insufficient information to classify the ticket."
        )
    else:
        new_category_rule = (
            "Map tickets to the categories provided above wherever they fit. "
            "Create a new category only when the issue is genuinely distinct "
            "from all provided categories. Use 'Uncategorised' only when there "
            "is genuinely insufficient information to classify the ticket."
        )

    ticket_lines = []
    for row in batch:
        resolution = row.get("resolution_notes", "").strip()
        resolution_part = f"\n  Resolution: {resolution}" if resolution else ""
        ticket_lines.append(
            f"ticket_id: {row['ticket_id']}\n"
            f"  Description: {row['issue_description']}\n"
            f"  Current label: {row['current_label']}"
            f"{resolution_part}"
        )
    tickets_section = "\n\n".join(ticket_lines)

    return f"""You are a ticket categorisation assistant analysing operational data.

Context: {context}
{categories_section}
{new_category_rule}

For each ticket, return:
- new_category: exactly one category name
- confidence: High, Medium, or Low
- reasoning: one specific sentence explaining the decision

Return a JSON array only — no other text, no markdown fences.
[
  {{"ticket_id": "...", "new_category": "...", "confidence": "High|Medium|Low", "reasoning": "..."}},
  ...
]

Tickets:
{tickets_section}"""


def _build_consolidation_prompt(context, category_counts, category_samples, uncategorised_samples):
    """Build the consolidation pass prompt."""

    dist_lines = []
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        samples = category_samples.get(cat, [])
        sample_text = "; ".join(s["description"][:80] for s in samples[:2])
        dist_lines.append(f"  '{cat}' ({count} tickets) — e.g. {sample_text}")
    distribution = "\n".join(dist_lines)

    uc_text = ""
    if uncategorised_samples:
        uc_lines = "\n".join(f"  - {s[:100]}" for s in uncategorised_samples)
        uc_text = f"\nUncategorised tickets (sample):\n{uc_lines}"

    return f"""You are reviewing the results of a ticket categorisation run.

Context: {context}

Category distribution:
{distribution}
{uc_text}

STAGE A — Write a one-line summary for each named category (not Uncategorised).
Describe what the tickets in that bucket have in common, in plain language
suitable for a stakeholder presentation.

STAGE B — Using the Stage A summaries, identify merge opportunities:
- AUTO_MERGE: categories that are near-identical in meaning. Merge these.
- FLAG: categories that may overlap but you are not certain. Flag only (max 3).

STAGE C — Write a 2-3 sentence plain-English narrative summarising the full results.
Cover: total tickets processed, number of categories, the dominant theme and its share,
and the most important signal from the uncategorised bucket (if any).
Write it as if briefing a PM who has not seen the data. Be specific, not generic.

Also analyse the Uncategorised bucket and identify the top 2-3 themes
present in those tickets. Write as observations, not category names.

Return JSON only — no other text, no markdown fences:
{{
  "narrative": "2-3 sentence plain English summary of the full results",
  "category_summaries": {{"category name": "one sentence summary", ...}},
  "auto_merges": [{{"merge_these": ["Category A", "Category B"], "into": "Merged Name"}}, ...],
  "merge_flags": ["plain English flag", ...],
  "uncategorised_analysis": ["observation 1", "observation 2"]
}}"""


def _build_multi_tag_prompt(context, categories, batch):
    """Build the multi-tag pass prompt."""

    cat_list = "\n".join(
        f"  - {c}" for c in categories if c != "Uncategorised")

    ticket_lines = []
    for row in batch:
        ticket_lines.append(
            f"ticket_id: {row['ticket_id']}\n"
            f"  Description: {row['issue_description']}"
        )
    tickets_section = "\n\n".join(ticket_lines)

    return f"""You are mapping support tickets to all applicable themes.

Context: {context}

Available categories:
{cat_list}

For each ticket, identify ALL categories that apply — not just the primary one.

Return a JSON array only — no other text, no markdown fences:
[
  {{"ticket_id": "...", "tags": ["Category A", "Category B"]}},
  ...
]

Tickets:
{tickets_section}"""


# ── Response parsers ───────────────────────────────────────────────────────────

def _call_gemini(client, prompt):
    """Send a prompt to Gemini and return the raw text response."""
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )
    return response.text.strip()


def _clean_json_response(raw):
    """Strip markdown code fences if the model wraps the response."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _parse_batch_response(raw, batch):
    """Parse the JSON array from a categorisation batch call."""
    try:
        cleaned = _clean_json_response(raw)
        results = json.loads(cleaned)
        if len(results) != len(batch):
            raise ValueError(
                f"Expected {len(batch)} results, got {len(results)}")
        return results
    except Exception:
        return [
            {
                "ticket_id": row["ticket_id"],
                "new_category": "Uncategorised",
                "confidence": "Low",
                "reasoning": "Could not parse model response for this batch."
            }
            for row in batch
        ]


def _parse_consolidation_response(raw):
    """Parse the JSON object from the consolidation pass."""
    try:
        cleaned = _clean_json_response(raw)
        return json.loads(cleaned)
    except Exception:
        return {
            "category_summaries": {},
            "auto_merges": [],
            "merge_flags": [],
            "uncategorised_analysis": []
        }


def _parse_multi_tag_response(raw, batch):
    """Parse the JSON array from a multi-tag batch call."""
    try:
        cleaned = _clean_json_response(raw)
        results = json.loads(cleaned)
        if len(results) != len(batch):
            raise ValueError(
                f"Expected {len(batch)} results, got {len(results)}")
        return results
    except Exception:
        return [{"ticket_id": row["ticket_id"], "tags": []} for row in batch]


# ── Bucket threshold enforcement ───────────────────────────────────────────────

def _apply_bucket_threshold(df):
    """
    Collapse any named category below MIN_BUCKET_THRESHOLD rows
    into Uncategorised. Uncategorised itself is exempt.
    """
    category_counts = df["new_category"].value_counts()
    for cat, count in category_counts.items():
        if cat == "Uncategorised":
            continue
        if count < MIN_BUCKET_THRESHOLD:
            df.loc[df["new_category"] == cat, "new_category"] = "Uncategorised"
    return df
