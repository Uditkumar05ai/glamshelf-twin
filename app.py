"""
Glam Shelf Twin — Phase 0
A localhost-only Flask app that drafts WhatsApp replies in The Glam Shelf voice.

MILESTONE 3: Wire up the Claude API call.
Calls Claude via the Claude Agent SDK (uses the local Claude Code CLI auth →
no separate API key needed). brain.md is loaded fresh on every request and
sent as the system prompt.
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Force unbuffered stdout so [INFO] prints appear immediately in the terminal.
# UTF-8 encoding lets us print emoji (🤍) and other non-ASCII chars in debug logs
# without hitting Windows' default cp1252 UnicodeEncodeError.
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

# Windows: force the Proactor event loop policy so subprocess.exec works inside
# Flask's worker threads (the default in non-main threads on Windows can't
# spawn subprocesses, which breaks the Claude Agent SDK).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

app = Flask(__name__)

PROJECT_DIR = Path(__file__).parent.resolve()
BRAIN_FILE = PROJECT_DIR / "brain" / "brain.md"
MODEL = "claude-sonnet-4-6"



def load_brain() -> str:
    """Read brain.md fresh from disk on every request."""
    print(f"[BRAIN] Loading {BRAIN_FILE}")
    text = BRAIN_FILE.read_text(encoding="utf-8")
    print(f"[BRAIN] Loaded {len(text)} chars")
    return text


def build_full_prompt(brain: str, customer_message: str, order_context: str) -> str:
    """Bundle brain + customer context into a single prompt sent via stdin.

    We can't use ClaudeAgentOptions(system_prompt=brain) because the SDK passes
    system_prompt as a CLI argument to claude.exe — Windows caps the command
    line at ~8KB and brain.md is much larger. Sending it inside the prompt
    body works because the prompt is delivered via stdin (no size limit).
    """
    return (
        "=== BRAIN FILE (treat the entire block below as your operating instructions and brand voice — follow it strictly) ===\n\n"
        f"{brain}\n\n"
        "=== TASK ===\n\n"
        "Customer WhatsApp message:\n"
        f"{customer_message}\n\n"
        "Order context (may be empty):\n"
        f"{order_context or '(none provided)'}\n\n"
        "Based strictly on the brain file above, do two things:\n"
        "1. Classify this situation as AUTO, DRAFT+APPROVE, or ESCALATE per Section 5 rules\n"
        "2. Draft the reply in The Glam Shelf's voice per Section 4 playbook\n\n"
        "Return ONLY raw JSON. Absolutely no markdown code fences. No ```json blocks. "
        "No prose, greeting, or commentary before or after the JSON. Your response "
        "MUST start with the character { and MUST end with the character }.\n"
        "Use this exact shape:\n"
        '{ "classification": "AUTO" | "DRAFT+APPROVE" | "ESCALATE", "reply": "..." }'
    )


def strip_markdown_fences(text: str) -> tuple[str, bool]:
    """Remove ```json ... ``` or ``` ... ``` wrapping from Claude's response.

    Returns (cleaned_text, was_fenced) — the boolean lets us log whether
    Claude slipped fences in so we can track how often it happens.
    """
    cleaned = text.strip()
    was_fenced = False
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
        was_fenced = True
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
        was_fenced = True
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
        was_fenced = True
    return cleaned.strip(), was_fenced


async def ask_claude(prompt: str) -> str:
    """Send the request to Claude via the Agent SDK and collect the assistant text."""
    print(f"[CLAUDE] Calling model {MODEL} (prompt: {len(prompt)} chars)")
    options = ClaudeAgentOptions(
        model=MODEL,
        allowed_tools=[],          # No tool use — pure text generation
        permission_mode="bypassPermissions",
        cwd=str(PROJECT_DIR),
    )

    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)

    full_text = "".join(chunks).strip()
    print(f"[CLAUDE] Got {len(full_text)} chars back")
    # Show the first 300 chars of the raw response so we can spot fences or drift.
    preview = full_text[:300] + ("..." if len(full_text) > 300 else "")
    print(f"[CLAUDE] Raw response preview:\n        {preview}")

    cleaned, was_fenced = strip_markdown_fences(full_text)
    if was_fenced:
        print("[CLAUDE] NOTE: markdown code fences were detected and stripped")
    return cleaned


@app.route("/")
def home():
    print("[INFO] Homepage requested")
    return render_template("index.html")


@app.route("/draft", methods=["POST"])
def draft():
    print("\n" + "=" * 60)
    print("[DRAFT] New request received")
    data = request.get_json(silent=True) or {}
    customer_message = (data.get("customer_message") or "").strip()
    order_context = (data.get("order_context") or "").strip()

    print(f"[DRAFT] customer_message ({len(customer_message)} chars):")
    print(f"        {customer_message[:200]}{'...' if len(customer_message) > 200 else ''}")
    print(f"[DRAFT] order_context ({len(order_context)} chars)")

    if not customer_message:
        print("[DRAFT] ERROR: customer_message is empty")
        return jsonify({"error": "customer_message is required"}), 400

    if not BRAIN_FILE.exists():
        print(f"[DRAFT] ERROR: brain file missing at {BRAIN_FILE}")
        return jsonify({"error": f"brain file not found at {BRAIN_FILE}"}), 500

    try:
        brain = load_brain()
        full_prompt = build_full_prompt(brain, customer_message, order_context)
        raw_response = asyncio.run(ask_claude(full_prompt))
        print(f"[DRAFT] Returning raw response ({len(raw_response)} chars)")
        print("=" * 60 + "\n")
        return jsonify({"raw": raw_response})
    except Exception as e:
        print(f"[DRAFT] EXCEPTION: {type(e).__name__}: {e}")
        print("[DRAFT] Full traceback:")
        traceback.print_exc()
        cause = e.__cause__ or e.__context__
        if cause:
            print(f"[DRAFT] Underlying cause: {type(cause).__name__}: {cause}")
        print("=" * 60 + "\n")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Glam Shelf Twin — Phase 0  (Milestone 3)")
    print(f"  Brain file: {BRAIN_FILE}")
    print(f"  Model:      {MODEL}")
    print("  Open this in your browser: http://localhost:5000")
    print("  Press CTRL+C in this terminal to stop the server.")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=True)
