# Build Log — llm-issue-categorizer

A running journal of what was built, what was decided, and what was learned at each milestone.
Entries written after each milestone completes. Honest about what broke and why.

---

## M0 — Environment Setup & API Validation
**Status:** ✅ Complete

### What was built
- GitHub Codespaces environment configured with Python 3.12, all dependencies installed via `requirements.txt`
- `test_api.py` validation script confirming Gemini API key injection via Codespaces Secrets
- Confirmed `gemini-3.1-flash-lite` free tier availability and rate limits (500 RPD, 15 RPM) in AI Studio dashboard

### Key decisions
- **Codespaces over local machine:** Microsoft IP ownership policy means no project code on work hardware. Codespaces eliminates the risk entirely.
- **`GOOGLE_API_KEY_V2` as secret name:** Separate from any other Gemini key to avoid conflicts.
- **`google-genai` SDK:** The older `google-generativeai` package is deprecated. `google-genai` has a different import structure — caught early, avoided pain later.

### Gotchas
- Streamlit port forwarding in Codespaces requires `--server.enableCORS false --server.enableXsrfProtection false` at launch, or a `.streamlit/config.toml` with those settings. Without this, the app runs but the browser shows a 404. Resolved by adding `config.toml` to the repo in M6.

---

## M1 — Engine Build & Validation
**Status:** ✅ Complete

### What was built
- `app/engine.py` — full categorisation engine with five public functions and eight private helpers
- `app/samples.py` — 255 rows across three datasets (UPI Customer Care, Ads System Monitoring, Copilot Support)
- `test_engine.py` — end-to-end validation against the 90-row UPI dataset

### Engine architecture
**Five public functions:**
- `parse_file()` — CSV/Excel/TXT ingestion; only `issue_description` required; `ticket_id` auto-generated if missing; windows-1252 encoding fallback for Excel exports
- `run_categorisation()` — 10-row batches; accumulated category list passed across batches for consistency; bucket threshold (min 5 rows) applied post-run
- `run_consolidation()` — single LLM pass generating: narrative summary, per-category one-liners, auto-merges, merge flags, uncategorised analysis
- `run_multi_tag()` — second pass mapping each ticket to all applicable themes; pipe-separated `multi_tags` column
- `run_auto_suggest()` — samples 25% of rows (min 13, max 25); returns proposed taxonomy list

### M1 validation results (90-row UPI dataset, No suggestions mode)
- Zero low confidence rows
- 7 categories generated, distribution matched expected patterns
- Consolidation auto-merged two near-identical categories correctly
- Combined category summaries preserved in merged bucket

### Key decisions
- **Batch size of 10:** Balances API call efficiency against context window. Larger batches produced inconsistent JSON; smaller batches hit RPM limits.
- **Accumulated categories across batches:** Each batch receives the running list of categories identified so far. This prevents the same concept getting named differently across batches.
- **4-second sleep between batches:** Stays within 15 RPM free tier limit with headroom.

### Gotchas
- `google-generativeai` vs `google-genai` import structure is completely different. All engine code uses `google-genai`.
- Empty `app/__init__.py` required for Streamlit module resolution when running from repo root.

---

## M2 — Streamlit UI: Core Structure & No Suggestions Mode
**Status:** ✅ Complete

### What was built
- `app/main.py` — full Streamlit UI with header, Choose your data section, Configure your run section, processing flow, and results
- Three sample dataset tiles with one-click loading
- File upload with encoding fallback (windows-1252 for Excel exports)
- Download template button (CSV with correct column headers)
- Results table with Low confidence filter
- Horizontal bar chart with dark-to-light teal gradient (interpolated across named categories, grey for Uncategorised)
- Results Summary section: narrative, category breakdown table, auto-merges, flags, uncategorised analysis

### Design system established
- Page background: `#f3f4f6` (light grey)
- Single accent: `#0f766e` (teal)
- Font: system-ui stack — consistent across all elements
- Three text sizes: 28px title, 15px body, 13px labels
- Teal gradient: interpolated from `#0f766e` to `#ccfbf1` across named categories; wrapping fixed by using ratio-based interpolation instead of a fixed 6-shade list

### Key decisions
- **Only `issue_description` required:** All other columns optional. `ticket_id` auto-generated as "Row 1, 2, 3..." if missing. This decision made after testing with real Ads ops ticket exports which had no structured IDs.
- **Results Summary always visible:** Originally a collapsible expander. Moved to always-visible — hiding the narrative and category breakdown behind a click buried the best part of the output.
- **Single Download CSV at bottom:** Earlier version had two download buttons. Removed the top one.

### Gotchas
- File uploader does not clear on reset unless its `key` parameter changes. Fixed by storing `uploader_key` in session state and incrementing on reset.
- `st.session_state.df` was being overwritten to None during processing because the file uploader re-renders on every Streamlit rerun. Fixed by adding a row-count equality check before updating df.

---

## M3 — Manual List & Auto-Suggest Modes
**Status:** ✅ Complete

### What was built
- Manual list mode: text area for user-defined categories (one per line), min 2 / max 15 validation
- Auto-suggest mode: "Generate suggestions" button triggers `run_auto_suggest()`, returns editable chip list with rename/delete/add/re-generate controls
- All three modes validated end-to-end against all three sample datasets

### Validation results
- **No suggestions (UPI):** 10 categories, 9 (10%) Uncategorised, sharp distribution
- **Manual list (Ads):** LLM correctly used provided categories; merged two semantically similar ones (Bid/Auction + Ad Delivery → Campaign Delivery & Auction Performance). Zero Uncategorised.
- **Auto-suggest (Copilot):** 8 suggested categories from 25% sample, all domain-appropriate. Zero Uncategorised. "Response Accuracy and Quality" correctly dominated at 40%.

### Key decisions
- **Auto-suggest requires >50 rows:** Sampling 25% of fewer than 50 rows gives too small a sample for meaningful taxonomy suggestion.
- **LLM can extend manual list:** In Manual list mode, the LLM maps to user-defined categories but can create new buckets if the data warrants it. Mirrors real PM workflow — starting point preserved, genuine patterns not missed.

---

## M4 — Review Panel & Multi-Tag Validation
**Status:** ✅ Complete

### What was built
- Validated Results Summary (formerly "Review before downloading") across all three datasets
- Validated multi-tag view end-to-end: bar chart, CSV with pipe-separated `multi_tags` column
- Confirmed CSV download schema: `ticket_id`, `issue_description`, `current_label`, `resolution_notes`, `new_category`, `confidence`, `reasoning`, `multi_tags`

### Validation results
- **Transparency log:** Auto-merge correctly fired on UPI — 'Registration and Onboarding Issues' + 'Account Linking Issues' → 'Account Setup and Linking' (12 tickets).
- **Merge flags:** Two flags on UPI — Failed Transaction / Credit Settlement overlap and Registration / KYC overlap. Both correct and useful.
- **Uncategorised analysis:** 10 UPI tickets surfaced three genuine product signals: PIN management friction, wrong UPI ID transfer confusion, self-service navigation gaps.
- **Multi-tag chart:** Total tag occurrences (122) correctly exceeded 90-row total. Single-bucket and multi-tag charts gave meaningfully different analytical views.

---

## M5 — UI Polish & Design System
**Status:** ✅ Complete

### What was built
- Full design system applied consistently across all sections
- Two-group Configure section: **Category source** and **Analysis depth**
- Multi-tag moved from post-results button to upfront choice in Configure — runs in the same processing session
- Combined progress bar covering all phases with single updating status line
- Frozen sections: Choose your data and Configure your run remain visible but disabled during processing and results, preserving page height so Processing appears below Run
- Start over button at bottom of results page alongside Download CSV
- `.streamlit/config.toml` committed with CORS and XSRF disabled

### Key decisions
- **Frozen sections preserve height:** Replacing frozen sections with compact badges caused Processing to render near the top of the page — page height shrank dramatically. Keeping full section height with `disabled=True` widgets solved this.
- **Analysis depth upfront:** Moving multi-tag to a pre-run choice eliminated the buried post-results button and simplified the results page to a single coherent view.

### Gotchas
- `nonlocal log_lines` SyntaxError: `log_lines` was at the same scope level as the nested function, not in an outer function. Removed the `nonlocal` declaration.
- Windows-1252 encoding: real ops ticket CSV exports use Windows-1252. Added UTF-8 → windows-1252 fallback in `parse_file()`.
- Auto-suggest chip text inputs got red borders from the mandatory context field CSS rule. Fixed by scoping the selector to `data-key="ctx_input"` only.
- Duplicate `st.markdown()` argument caused an IndentationError during a refactor. Removed the duplicate.

---

## M6 — Deployment to Streamlit Community Cloud
**Status:** ✅ Complete

### What was built
- App deployed to Streamlit Community Cloud via share.streamlit.io
- `GOOGLE_API_KEY_V2` added to Streamlit Cloud secrets dashboard
- README updated with live URL and ✅ status

### Live URL
[https://llm-issue-categorizer.streamlit.app](https://llm-issue-categorizer.streamlit.app)

### Key decisions
- **Streamlit Community Cloud over Codespaces URL:** Codespace URLs are session-specific, require GitHub login to access even when Public, and go dead when the Codespace sleeps. Streamlit Cloud gives a permanent public URL with no authentication required.
- **Secret in dashboard, not in repo:** `GOOGLE_API_KEY_V2` lives in Streamlit Cloud's secrets manager. `.streamlit/secrets.toml` is in `.gitignore`.

### Total build time
Approximately 6 weeks across PM documentation (completed first) and build phases. All six milestones complete. App live and publicly accessible.
