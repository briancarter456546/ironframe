"""
Hook enforcement -- deterministic gates OUTSIDE the LLM context window.

This is Iron Frame's single most important architectural decision: hooks
execute outside the model's context. A model cannot rationalize around them,
forget them, or skip them due to context pressure.

The HookEngine is event-driven: register handlers against named events,
then fire(event, context) to run the chain. Blocking hooks halt the chain
on failure.

No API key required -- this is pure enforcement logic.

Run:
    python examples/hook_enforcement.py
"""

from ironframe.hooks.engine_v1_0 import HookEngine, HookResult


def block_destructive_prompts(context: dict) -> HookResult:
    """Pre-completion hook: block prompts containing 'delete all'."""
    prompt = context.get("prompt", "").lower()
    if "delete all" in prompt:
        return HookResult(
            allow=False,
            message="Destructive intent detected: 'delete all' is blocked by policy.",
        )
    return HookResult(allow=True)


def redact_secrets(context: dict) -> HookResult:
    """Post-completion hook: warn if output looks like it contains an API key."""
    output = context.get("output", "")
    if "sk-" in output or "api_key" in output.lower():
        return HookResult(
            allow=False,
            message="Output may contain an API key. Blocking release.",
        )
    return HookResult(allow=True)


def main() -> None:
    engine = HookEngine()

    engine.register(
        event="pre_completion",
        handler=block_destructive_prompts,
        blocking=True,
        description="Blocks destructive intent patterns",
    )
    engine.register(
        event="post_completion",
        handler=redact_secrets,
        blocking=True,
        description="Prevents accidental secret leakage in responses",
    )

    print("=== Iron Frame Hook Enforcement ===\n")
    print(f"Registered events: {engine.events}")
    print(f"Hook summary:      {engine.summary()}\n")

    test_prompts = [
        "Summarize the project status.",                 # allowed
        "Please delete all records from the database.",  # blocked
    ]

    for prompt in test_prompts:
        chain = engine.fire("pre_completion", {"prompt": prompt})
        status = "[OK] ALLOWED" if chain.allow else "[BLOCK] DENIED"
        print(f"{status}: {prompt}")
        if not chain.allow:
            print(f"         Blocked by: {chain.blocked_by}")
            for r in chain.results:
                if not r.allow:
                    print(f"         Reason: {r.message}")
        print()

    # Post-completion check
    print("--- Post-completion secret scan ---")
    suspect_output = "Here is your API key: sk-ant-example123"
    chain = engine.fire("post_completion", {"output": suspect_output})
    status = "[OK] RELEASED" if chain.allow else "[BLOCK] HELD"
    print(f"{status}: {suspect_output[:40]}...")
    if not chain.allow:
        print(f"         Blocked by: {chain.blocked_by}")
    print()

    print("Key point: the LLM never saw the blocked prompt. The hook ran")
    print("at the platform level, before any model call was made.")


if __name__ == "__main__":
    main()
