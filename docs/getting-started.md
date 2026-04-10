# Getting Started with Iron Frame

This guide walks you through installing Iron Frame, making your first verified LLM call, and understanding what happens under the hood.

## Install

```bash
pip install ironframe
```

Optional extras:

```bash
pip install "ironframe[openai]"   # OpenAI / Perplexity adapter
pip install "ironframe[z3]"       # Symbolic verification (Tier 4)
pip install "ironframe[all]"      # Everything
```

## Configure

Iron Frame needs at minimum an Anthropic API key. Set it in your environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or use a `.env` file:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
IRONFRAME_BUDGET_PER_REQUEST=0.50
IRONFRAME_BUDGET_PER_SESSION=5.00
IRONFRAME_BUDGET_PER_DAY=25.00
```

## Your First Call

```python
from ironframe.config_v1_0 import IronFrameConfig
from ironframe.mal.client_v1_0 import IronFrameClient

config = IronFrameConfig.from_env()
client = IronFrameClient(config=config)

result = client.complete(
    prompt="Summarize the key risks in this contract.",
    preference="smart",
)

print(result["text"])
print(f"Cost: ${result['cost_usd']:.4f}")
```

Behind the scenes, that one call:

1. **Routed by capability.** `preference="smart"` selects the best model for reasoning, not a hardcoded name. Swap providers without changing your code.
2. **Budget-checked.** Per-request, per-session, and per-day caps enforced before the call. If you're over budget, the call is refused (not silently truncated).
3. **Logged to the immutable audit trail.** Write-before-release: the audit entry is written before the response is returned. If logging fails, the operation does not complete.
4. **Captured in a compliance-ready schema.** HIPAA, FINRA, SOC2, SEC, and GDPR fields are all captured by default -- even if you don't need them yet.

## Capability Preferences

| Preference | Default model | Use for |
|------------|---------------|---------|
| `fast` | Claude Haiku | Quick lookups, classification, summarization |
| `smart` | Claude Sonnet | Reasoning, analysis, writing |
| `cheap` | Claude Haiku | Cost-sensitive workloads |
| `verification` | Perplexity Sonar | Cross-model verification |
| `long-context` | Claude Sonnet | Long document processing |

You can override routing in config or pass an explicit model name.

## Next Steps

- [`docs/architecture.md`](architecture.md) -- How Iron Frame's 18 components fit together
- [`docs/compliance-adapters.md`](compliance-adapters.md) -- Using and writing compliance adapters
- [`examples/`](../examples/) -- Working examples for every major feature
- [`SPEC.md`](../SPEC.md) -- The canonical specification
