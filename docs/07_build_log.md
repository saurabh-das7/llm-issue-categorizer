# 07 — Build Log

*llm-issue-categorizer · Updated continuously during build*

---

## Purpose

This is a running journal of the build — honest, not polished. 
Every session gets an entry. Entries record what was accomplished, 
what was harder than expected, what changed from the plan, and 
what comes next. A log that only records wins is a press release. 
This is not that.

---

## Entry format

```
### Entry N — [Short title]
**Date:** [Month Year]
**Milestone:** [M0–M6]
**Hours this session:** [X hours]

**What was accomplished:**

**What was harder than expected:**

**What changed from the plan:**

**What's next:**
```

---

## Entries

### Entry 1 — Environment setup and API verified
**Date:** May 2026
**Milestone:** M0
**Hours this session:** ~1 hour

**What was accomplished:**
GitHub Codespaces environment set up. All five dependencies installed
cleanly via postCreateCommand in devcontainer.json. Gemini API key
(GOOGLE_API_KEY_V2) confirmed injecting correctly as a Codespaces
Secret. First API call to gemini-3.1-flash-lite returned valid
structured JSON with correct category, confidence, and reasoning fields.
Folder structure established: app/, docs/, requirements.txt, .gitignore,
test_api.py, placeholder app/main.py, app/engine.py, app/samples.py.

**What was harder than expected:**
Case sensitivity mismatch between the secret name (GOOGLE_API_KEY_V2)
and the test script (GOOGLE_API_KEY_v2) caused the first run to fail
with "API key not found." Fixed by updating the script to match the
exact secret name. Environment variable names are case-sensitive.

**What changed from the plan:**
Nothing — M0 went exactly as designed.

**What's next:**
M1 — build engine.py: file parsing, batch categorisation loop,
consolidation pass.

---

### Entry 2 — Categorisation engine built and validated
**Date:** May 2026
**Milestone:** M1
**Hours this session:** ~3 hours

**What was accomplished:**
All four engine functions built in `app/engine.py` and validated against
the full 90-row UPI sample dataset. `parse_file()` handles CSV, Excel,
and TXT input with column normalisation and row limit enforcement.
`run_categorisation()` processes rows in batches of 10, accumulates
category labels across batches for consistency, and applies the 5-row
bucket threshold post-run. `run_consolidation()` runs a two-stage LLM
pass — generating per-category one-liners first, then using those to
inform auto-merge decisions — and correctly applies high-confidence
merges with a transparency log. `run_multi_tag()` built and ready for
UI integration in M2. `app/samples.py` populated with all 255 rows
across three datasets (UPI, Ads, Copilot).

**What was harder than expected:**
The initial prompt told the LLM to only create categories if a pattern
would appear 5+ times across the full dataset. Since the LLM only sees
10 rows at a time, it played it safe and put almost everything into
Uncategorised. Fix: removed the threshold constraint from the prompt
entirely and let `_apply_bucket_threshold()` do the enforcement
post-run — which is the correct architecture. The prompt should never
mention the threshold.

Second issue: after auto-merges were applied in the consolidation pass,
the merged category had no summary — the summaries were generated using
the pre-merge category names. Fix: after applying each merge, combined
the source summaries into the merged category name and removed the
source entries from the summaries dict. No extra API call needed.

**What changed from the plan:**
Prompt design required two iterations before categorisation quality was
acceptable. Architecture did not change — the fix was in the prompt
instructions only. Engine test script (`test_engine.py`) ran directly
against the full 90-row sample rather than a smaller synthetic dataset,
which gave more meaningful validation earlier.

**What's next:**
M2 — build `app/main.py`. Primary flow end-to-end: three sample tiles,
upload zone, context field, mode selection (No Suggestions only at first),
progress bar, results table, bar chart, download CSV. Test deployment to
Streamlit Community Cloud at end of M2.

---

*Previous: [06 — Roadmap](./06_roadmap.md)*  
*Next: [08 — Launch & Retrospective](./08_launch_and_retro.md)*