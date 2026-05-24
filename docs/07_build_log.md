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
cleanly via postCreateCommand. Gemini API key (GOOGLE_API_KEY_V2)
confirmed injecting correctly. First API call to gemini-3.1-flash-lite
returned valid structured JSON with correct category, confidence, and
reasoning fields.

**What was harder than expected:**
Case sensitivity mismatch between secret name (GOOGLE_API_KEY_V2) and
test script (GOOGLE_API_KEY_v2) caused the first run to fail. Fixed by
updating the script.

**What changed from the plan:**
Nothing — M0 went exactly as designed.

**What's next:**
M1 — build engine.py: file parsing, batch categorisation loop,
consolidation pass.


---

*Previous: [06 — Roadmap](./06_roadmap.md)*  
*Next: [08 — Launch & Retrospective](./08_launch_and_retro.md)*
