# test_engine.py — M1 full engine test on 90-row UPI dataset
# Run: python test_engine.py

from app.samples import get_sample_df, get_sample_context
from app.engine import run_categorisation, run_consolidation

# ── Load sample data ───────────────────────────────────────────────────────────
df = get_sample_df("upi")
context = get_sample_context("upi")
print(f"Loaded {len(df)} rows — context: {context[:60]}...")

# ── Run categorisation ─────────────────────────────────────────────────────────
print("\nRunning categorisation (9 batches × 10 rows)...")

def progress(batch_num, total):
    print(f"  Batch {batch_num}/{total} complete")

result_df = run_categorisation(
    df=df,
    context=context,
    mode="no_suggestions",
    categories=None,
    progress_callback=progress
)

print("\n--- Category distribution ---")
print(result_df["new_category"].value_counts().to_string())

print("\n--- Low confidence rows ---")
low_conf = result_df[result_df["confidence"] == "Low"]
if len(low_conf) == 0:
    print("  None")
else:
    print(low_conf[["ticket_id", "new_category", "reasoning"]].to_string(index=False))

# ── Run consolidation ──────────────────────────────────────────────────────────
print("\nRunning consolidation pass...")
consolidation = run_consolidation(result_df, context)

print("\n--- Transparency log ---")
if consolidation["transparency_log"]:
    for entry in consolidation["transparency_log"]:
        print(f"  {entry}")
else:
    print("  No merges applied")

print("\n--- Category summaries ---")
for cat, summary in consolidation["category_summaries"].items():
    print(f"  {cat}: {summary}")

print("\n--- Merge flags ---")
if consolidation["merge_flags"]:
    for flag in consolidation["merge_flags"]:
        print(f"  ⚠ {flag}")
else:
    print("  None")

print("\n--- Uncategorised analysis ---")
for obs in consolidation["uncategorised_analysis"]:
    print(f"  · {obs}")

print("\n=== M1 complete ===")