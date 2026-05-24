"""
Milestone 0 — API verification script
--------------------------------------
Run this to confirm:
  1. google-genai SDK is installed correctly
  2. GOOGLE_API_KEY_V2 Codespaces secret is being injected
  3. gemini-3.1-flash-lite model is accessible on the free tier
  4. A structured JSON response can be parsed cleanly

Usage:
  python test_api.py

Expected output:
  SDK import: OK
  API key found: OK
  API call: OK
  Response parsed: OK
  --- Response content ---
  { ...valid JSON... }
  --- M0 complete. Engine build can begin. ---
"""

import os
import json
import sys


def run_test():
    # --- Step 1: SDK import ---
    try:
        from google import genai
        print("SDK import: OK")
    except ImportError as e:
        print(f"SDK import: FAILED — {e}")
        print("Run: pip install google-genai")
        sys.exit(1)

    # --- Step 2: API key ---
    api_key = os.environ.get("GOOGLE_API_KEY_V2")
    if not api_key:
        print("API key: FAILED — GOOGLE_API_KEY_V2 not found in environment")
        print("Check that the Codespaces Secret is named exactly GOOGLE_API_KEY_V2")
        sys.exit(1)
    print("API key found: OK")

    # --- Step 3: API call ---
    try:
        client = genai.Client(api_key=api_key)

        prompt = """
You are a ticket categorisation assistant. Categorise the following 
support ticket into exactly one category from this list:
- Payment Failure
- App Crash
- Fraud

Ticket: "Transaction of Rs 500 to a merchant failed but the amount 
was debited from my account."

Respond in JSON only, no other text. Format:
{
  "category": "...",
  "confidence": "High | Medium | Low",
  "reasoning": "one sentence"
}
"""
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt
        )
        print("API call: OK")

    except Exception as e:
        print(f"API call: FAILED — {e}")
        print("\nCommon causes:")
        print("  - Model name incorrect (check: gemini-3.1-flash-lite)")
        print("  - API key invalid or not yet active")
        print("  - Free tier rate limit hit (check AI Studio dashboard)")
        sys.exit(1)

    # --- Step 4: Parse response ---
    try:
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        print("Response parsed: OK")
        print("\n--- Response content ---")
        print(json.dumps(parsed, indent=2))
        print("\n--- M0 complete. Engine build can begin. ---")

    except json.JSONDecodeError as e:
        print(f"Response parsed: FAILED — {e}")
        print("Raw response was:")
        print(response.text)
        print("\nThis is a prompt or model issue — the API call itself worked.")
        sys.exit(1)


if __name__ == "__main__":
    run_test()
