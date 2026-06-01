# Launch & Retrospective — llm-issue-categorizer

---

## Launch Status
**Live:** [https://llm-issue-categorizer.streamlit.app](https://llm-issue-categorizer.streamlit.app)
**Launch date:** June 2026
**Stack:** Python 3.12 · Streamlit · Google Gemini 3.1 Flash-Lite (free tier) · Streamlit Community Cloud

---

## Pre-Launch QA Checklist

### Functionality
- [x] No suggestions mode — all three sample datasets run cleanly
- [x] Manual list mode — LLM maps to user categories, creates new buckets appropriately
- [x] Auto-suggest mode — taxonomy generated from 25% sample, editable before run
- [x] Full theme mapping — multi-tag pass runs in same session, chart appears in results
- [x] Results table — confidence filter works, Low rows correctly identified
- [x] Category distribution chart — gradient correct, Uncategorised in grey, sorted by volume
- [x] Results Summary — narrative, breakdown table, auto-merges, flags, uncategorised analysis all present
- [x] Download CSV — all 8 columns present; `multi_tags` blank if depth was Primary only
- [x] Start over — clears session state, clears uploaded file, returns to input state
- [x] Upload — CSV, Excel, TXT all parse correctly; windows-1252 encoding fallback works
- [x] Download template — correct column headers, downloads as CSV

### Edge cases
- [x] Upload file with only `issue_description` column — auto-generates `ticket_id`, defaults other columns to empty
- [x] Upload file with >100 rows — error message shown, context field hidden
- [x] Manual list with <2 categories — Run button stays disabled
- [x] Auto-suggest on dataset with ≤50 rows — mode disabled with explanation
- [x] Context field <10 characters — Run button disabled, caption prompts user to press Enter
- [x] All tickets categorised — Uncategorised bucket shows "All tickets categorised" message

### Performance
- [x] 90-row dataset, Primary only — completes in under 90 seconds
- [x] 90-row dataset, Full theme mapping — completes in under 3 minutes
- [x] Progress bar updates after each batch — visible feedback throughout
- [x] Processing renders below Run button — frozen sections preserve page height

### Design
- [x] Header visible and readable
- [x] Sample tiles equal height across all three
- [x] Frozen sections faded but legible — colours preserved at ~55% opacity
- [x] Results Summary always visible — not hidden in expander
- [x] Download CSV and Start over at bottom of results page

### Deployment
- [x] App live on Streamlit Community Cloud
- [x] API key in secrets dashboard — not in repo
- [x] `.streamlit/secrets.toml` in `.gitignore`
- [x] `config.toml` committed with CORS and XSRF disabled
- [x] README updated with live URL
- [x] Status updated from 🔨 to ✅

---

## Post-Launch Retrospective

### What was built

An LLM-powered operational ticket categoriser that takes vague, inconsistently labelled issue data and returns a structured, auditable taxonomy — with confidence scores, reasoning notes, auto-merge detection, and pattern summaries. Three categorisation modes (No suggestions, Manual list, Auto-suggest), two analysis depths (Primary category only, Full theme mapping), and a Results Summary that surfaces what the raw labels never could.

The tool is genuinely useful for the problem it solves. It was tested against real Ads platform monitoring ticket data (57 rows, windows-1252 encoding, no structured labels) and returned a clean 6-category taxonomy with meaningful distribution and useful merge flags in under 90 seconds.

### What worked well

**Design before build discipline.** All 9 PM documents were completed before a single line of application code was written. This meant the build phase had no scope uncertainty — every feature decision was already made and reasoned through. The PRD, UX flow, and sample data bank served as the single source of truth throughout.

**The three-mode taxonomy design.** No suggestions, Manual list, and Auto-suggest cover the full spectrum of PM approaches to an unfamiliar dataset. The decision to let the LLM extend a manual list (rather than strictly enforce it) was the right call — it preserves user intent while not missing genuine patterns.

**Moving multi-tag to Configure.** Originally a post-results button. Moving it to an upfront choice in Configure simplified the results page significantly, eliminated a second run button buried below the fold, and made the processing flow feel like a single coherent operation rather than two separate steps.

**The accumulated categories architecture.** Passing the running category list to each batch prevented the same concept being named differently across batches — a subtle but important consistency mechanism that made the output usable without manual cleanup.

**Results Summary as always-visible output.** The narrative paragraph, category breakdown table, merge transparency, and uncategorised analysis are the most valuable part of the tool. Making them always visible rather than collapsing them behind an expander was the right call — they surface the "so what" that justifies running the tool.

### What was harder than expected

**Processing section rendering position.** Getting the Processing section to appear below the Run button took significantly more iteration than expected. The core issue: when frozen sections collapse, page height shrinks, and Streamlit renders Processing near the top. The solution — keeping full section height with `disabled=True` widgets — is correct but took many failed attempts with compact badge approaches before arriving there.

**Streamlit Codespaces port forwarding.** The CORS/XSRF issue with Codespaces is a known but poorly documented problem. The fix (`--server.enableCORS false --server.enableXsrfProtection false`) was found in a GitHub community discussion. Adding `config.toml` to the repo makes this transparent for future sessions.

**CSS scoping in Streamlit.** Streamlit's CSS injection via `st.markdown()` applies globally — there's no component-level scoping. The mandatory red border on the context field accidentally applied to all text inputs including the auto-suggest chip editors. Fixed by scoping to a specific `data-key` attribute, but this required understanding how Streamlit renders widget attributes.

**Upload flow state management.** The file uploader re-renders on every Streamlit rerun. During processing, this overwrote `st.session_state.df` with None because the file was no longer "attached." The row-count equality check fix works but is a workaround for a fundamental Streamlit limitation.

### What to do differently next time

**Build the CORS config file in M0.** The Codespaces port forwarding issue is known and affects every Streamlit project. Creating `config.toml` in the environment setup milestone would save confusion in every subsequent milestone.

**Session state schema upfront.** The session state keys grew organically across milestones. Defining the full schema in M1 (before any UI code) would have prevented several bugs caused by missing keys or inconsistent naming.

**Processing architecture decision earlier.** The decision to embed processing inside the Configure section (rather than as a standalone section) should have been made in the UX flow document, not discovered during M5 polish. The UX flow wireframe assumed a separate Processing section — the reality of Streamlit's rendering model made that approach unworkable.

### Metrics at launch

| Metric | Value |
|--------|-------|
| Processing time (90 rows, Primary only) | ~75 seconds |
| Processing time (90 rows, Full theme mapping) | ~160 seconds |
| API cost per run | ₹0 (free tier) |
| Monthly infrastructure cost | ₹0 |
| Sample datasets | 3 (255 rows total) |
| PM docs completed | 9 of 9 |
| Build milestones | 6 of 6 |

### Planned improvements (v2)

- **Lens selection in Results Summary** — when dataset volume grows to 30+ JDs, allow users to choose which analysis sections to show rather than always showing all six
- **Batch size tuning** — current 10-row batches are conservative; larger batches may be viable for the paid tier
- **Download as Excel** — the current CSV output loses column formatting in some Excel versions; an `.xlsx` download would preserve it
- **Progress percentage display** — the current "batch N of M" status is functional but a simple percentage would be cleaner
- **Saved runs** — allow users to save and reload a previous categorisation without re-running the API
