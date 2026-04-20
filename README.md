# Iron Frame

**Infrastructure reliability layer for LLM-powered systems.**

Reliable. Trustworthy. Accurate. Diligent.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-beta-yellow)]()

Iron Frame sits between raw LLMs and domain applications -- trading, healthcare, compliance, research -- and handles every fundamental limitation of LLMs: hallucinations, reasoning errors, context drift, bias accumulation, and incomplete process execution.

It is **infrastructure**, not a domain system. Your application sits on top of Iron Frame and trusts the foundation beneath it.

---

## Why Iron Frame

Most "AI reliability" products try to fix hallucination with more AI. Iron Frame takes a different approach: **deterministic enforcement outside the LLM context window.** A model cannot rationalize around hooks it never sees.

- **Hooks execute outside the LLM.** Deterministic gates at the platform level, not in the prompt.
- **Self-auditing from day 1.** Confidence scoring, self-consistency, and cross-model verification on every output.
- **Compliance-ready audit from day 1.** HIPAA, FINRA, SOC2, SEC, GDPR fields captured by the audit schema natively -- not bolted on.
- **Spend caps are mandatory.** Per-request, per-session, and per-day budget ceilings prevent runaway cost.
- **Immutable audit trail.** Write-before-release. If logging fails, the operation does not complete.
- **Model-agnostic.** Swappable providers with capability-based routing (fast / smart / cheap / verification / long-context).

---

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

---

## Quickstart

```python
from ironframe import IronFrameConfig
from ironframe.mal.client_v1_0 import IronFrameClient

config = IronFrameConfig.from_env()
client = IronFrameClient(config)

response = client.complete(
    prompt="Summarize the key risks in this contract.",
    preference="smart",
)

print(response.content)
print(f"Cost: ${response.cost:.4f}")
print(f"Model: {response.model}   Tokens: {response.tokens_in}/{response.tokens_out}")
```

`response` is an `IronFrameResponse` — a `dict` subclass that supports
both attribute access (`response.content`, `response.cost`, `response.model`)
and dict access (`response["text"]`, `response.get("cost_usd")`). Every
call is audited and budget-checked. Confidence scoring is a separate
pass — run `sae.verify(response)` to populate `response.confidence`; raw
MAL calls leave it as `None`. See [`examples/`](examples/) for more.

---

## Architecture

Iron Frame has 18 components organized around four pillars:

| Pillar | Components |
|--------|-----------|
| **Model Access** | Model Abstraction Layer (MAL), Budget Manager, Error Recovery |
| **Verification** | Self-Audit Engine (SAE), Logic Skills, Eval & Regression, KB Grounding |
| **Enforcement** | Hook Engine, State Machine, Tool Governance, Security, Agent Trust, I/O Schema |
| **Observability** | Immutable Audit Log, Compliance Adapters, Conformance & Drift Engine, Context Budget |

See [`SPEC.md`](SPEC.md) for the canonical specification and [`docs/architecture.md`](docs/architecture.md) for a walkthrough.

---

## Compliance Adapters

Iron Frame ships adapters for HIPAA, FINRA, SOC2, SEC, and GDPR compliance requirements. The base classes are Apache 2.0 -- you can write your own adapters for any protocol.

The pre-built regulatory adapters in `src/ironframe/compliance/adapters/` are **source-available under PolyForm Noncommercial**. They are free for research, education, nonprofits, and personal projects. Commercial use in a for-profit production system requires a commercial license.

See [`src/ironframe/compliance/adapters/LICENSE_COMMERCIAL`](src/ironframe/compliance/adapters/LICENSE_COMMERCIAL) and [`docs/compliance-adapters.md`](docs/compliance-adapters.md).

---

## Licensing (TL;DR)

- **Core framework:** Apache License 2.0 -- use it freely, including commercially. Includes an explicit patent grant.
- **Compliance adapters** (`compliance/adapters/`): PolyForm Noncommercial. Free for noncommercial use. Commercial license available.
- **Base classes** (`compliance/base_v1_0.py`, `compliance/audit_requirements_v1_0.py`): Apache 2.0. Write your own adapters.

See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and the [open-core ADR](docs/decisions/ADR-002-open-core-licensing.md).

---

## Status

Iron Frame is in **beta**. The API surface is stable (every module is explicitly versioned with a `_v1_0` suffix), but expect refinement before v1.0.

- 18 components implemented
- 5 compliance adapters
- Requirements Traceability Matrix with 22 tracked requirements
- Unit + integration test coverage

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Documentation

- [`SPEC.md`](SPEC.md) -- Canonical specification
- [`constitution.md`](constitution.md) -- Non-negotiable framework laws
- [`docs/getting-started.md`](docs/getting-started.md) -- First use
- [`docs/architecture.md`](docs/architecture.md) -- Architecture overview
- [`docs/compliance-adapters.md`](docs/compliance-adapters.md) -- Writing and using compliance adapters
- [`docs/decisions/`](docs/decisions/) -- Architecture Decision Records
