"""
Iron Frame quickstart -- your first verified, audited LLM call.

Prerequisites:
    pip install ironframe
    set ANTHROPIC_API_KEY=sk-ant-...   (Windows)
    export ANTHROPIC_API_KEY=sk-ant-... (Linux/Mac)

Run:
    python examples/quickstart.py
"""

from ironframe.config_v1_0 import IronFrameConfig
from ironframe.mal.client_v1_0 import IronFrameClient


def main() -> None:
    # Load config from environment (ANTHROPIC_API_KEY must be set).
    config = IronFrameConfig.from_env()

    # Create a client. Every call will be:
    #   - routed by capability preference (not model name)
    #   - budget-checked against per-request / per-session / per-day caps
    #   - logged to the immutable audit trail (write-before-release)
    client = IronFrameClient(config=config)

    # Make a call. "fast" routes to Haiku by default.
    result = client.complete(
        prompt="What is the capital of France? Answer in one word.",
        preference="fast",
    )

    print("=== Iron Frame Quickstart ===")
    print(f"Response:   {result.get('text', '').strip()}")
    print(f"Model:      {result.get('model', 'unknown')}")
    print(f"Cost USD:   ${result.get('cost_usd', 0.0):.6f}")
    print(f"Tokens in:  {result.get('tokens_in', 0)}")
    print(f"Tokens out: {result.get('tokens_out', 0)}")
    print(f"Session:    {result.get('session_id', '')}")
    print()
    print(f"Budget remaining: {client.budget.remaining()}")
    print()
    print("[OK] Audit log written. Check output/ironframe/ for the JSONL trail.")


if __name__ == "__main__":
    main()
