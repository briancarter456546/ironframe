"""
Iron Frame quickstart -- your first verified, audited LLM call.

Prerequisites:
    pip install ironframe
    set ANTHROPIC_API_KEY=sk-ant-...   (Windows)
    export ANTHROPIC_API_KEY=sk-ant-... (Linux/Mac)

Run:
    python examples/quickstart.py
"""

from ironframe import IronFrameConfig, IronFrameClient


def main() -> None:
    # Load config from environment (ANTHROPIC_API_KEY must be set).
    config = IronFrameConfig.from_env()

    # Create a client. Every call will be:
    #   - routed by capability preference (not model name)
    #   - budget-checked against per-request / per-session / per-day caps
    #   - logged to the immutable audit trail (write-before-release)
    client = IronFrameClient(config=config)

    # Make a call. "fast" routes to Haiku by default.
    # response is an IronFrameResponse -- supports both attribute and dict access.
    response = client.complete(
        prompt="What is the capital of France? Answer in one word.",
        preference="fast",
    )

    print("=== Iron Frame Quickstart ===")
    print(f"Response:   {response.content.strip()}")
    print(f"Model:      {response.model}")
    print(f"Cost USD:   ${response.cost:.6f}")
    print(f"Tokens in:  {response.tokens_in}")
    print(f"Tokens out: {response.tokens_out}")
    print(f"Session:    {response.session_id or ''}")
    print()
    print(f"Budget remaining: {client.budget.remaining()}")
    print()
    print("[OK] Audit log written. Check output/ironframe/ for the JSONL trail.")


if __name__ == "__main__":
    main()
