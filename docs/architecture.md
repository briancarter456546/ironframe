# Iron Frame Architecture

Iron Frame is organized around 18 components. This document gives a high-level map. For the authoritative specification, see [`SPEC.md`](../SPEC.md).

## The Four Pillars

| Pillar | What it does | Components |
|--------|-------------|-----------|
| **Model Access** | Clean, normalized, budgeted access to LLMs | MAL (1), Budget (15), Recovery (8) |
| **Verification** | Know when the model is wrong | SAE (5), Logic (6), Eval (13), KB Grounding (10) |
| **Enforcement** | Deterministic gates outside the LLM | Hooks (4), State (3), Tool Governance (12), Security (11), Agent Trust (17), I/O Schema (16) |
| **Observability** | Compliance-ready audit trail | Audit Log (7), Compliance (-), Conformance (18), Context Budget (9) |

## The 18 Components

1. **Model Abstraction Layer (MAL)** -- The only component that touches LLMs. Capability-based routing (`fast`, `smart`, `cheap`, `verification`, `long-context`). Adapters for Anthropic and Perplexity; OpenAI in progress.

2. **Skill Registry** -- Versioned catalog of skills with dependency resolution.

3. **State Machine / Session Manager** -- Phase gates, durable session state.

4. **Hook Engine** -- Deterministic enforcement gates that execute **outside the LLM context window**. A model cannot rationalize around them.

5. **Self-Audit Engine (SAE)** -- Tiered verification (0-4), confidence scoring, cross-model verification. Budget-capped to prevent runaway escalation.

6. **Logic Skills** -- Toulmin argument decomposition, CQoT (Critical Questions over Toulmin), fallacy taxonomy.

7. **Immutable Audit Log** -- Append-only, write-before-release. If logging fails, the operation does not complete. Compliance-ready schema from day 1.

8. **Error Recovery & Resilience** -- Circuit breakers, retry-with-variation, fallback chains.

9. **Context Budget Manager** -- Token budgeting, compression, staleness detection.

10. **KB Grounding Layer** -- Retrieval, freshness tracking, conflict arbitration.

11. **Security / Injection Defense** -- 5-layer defense: perimeter, structural, gating, monitoring, containment.

12. **Tool Governance** -- Contracts, rate limiting, auth, versioning.

13. **Eval & Regression Framework** -- Scenario library, multiple eval methods, regression gates.

14. **Multi-Agent Coordination** -- Structured message protocol, role registry, resource locks, loop detection.

15. **Cost/Latency Budget Manager** -- Task profiles, SLA enforcement, telemetry.

16. **I/O Schema Validation** -- Pydantic-first contracts, drift detection.

17. **Agent Trust & Identity** -- Zero-trust tiers (`OBSERVE`, `LIMITED`, `STANDARD`, `ELEVATED`), HMAC-signed tokens, anomaly detection, kill switch.

18. **Spec Conformance & Drift Engine** -- Requirements Traceability Matrix, static checker (CI/CD gate), runtime monitor, drift reporter.

## The Hooks-Outside-the-LLM Principle

Most "AI safety" approaches embed rules in the prompt. This fails when the model is under context pressure, when the prompt is long, or when the model simply decides to ignore the rules. Iron Frame takes the opposite approach: **deterministic enforcement happens at the platform level, before the model is ever called**. A prompt containing blocked content never reaches the model.

This means:
- Hooks are code, not text
- Hooks cannot be rationalized around
- Hooks are the same whether the model is Claude, GPT, Gemini, or a local Llama

See [`docs/decisions/ADR-001-hooks-outside-llm.md`](decisions/ADR-001-hooks-outside-llm.md) for the full rationale.

## Open-Core Boundary

Iron Frame is dual-licensed:

- **Apache 2.0** -- Core framework. Explicit patent grant. Use commercially without restriction.
- **PolyForm Noncommercial** -- Pre-built compliance adapters (HIPAA, FINRA, SOC2, SEC, GDPR). Free for noncommercial use. Commercial use requires a separate license.

The base classes (`compliance/base_v1_0.py`, `compliance/adapter_base_v1_0.py`, `compliance/audit_requirements_v1_0.py`) are Apache 2.0. You can write your own compliance adapters freely.

See [`docs/decisions/ADR-002-open-core-licensing.md`](decisions/ADR-002-open-core-licensing.md).

## Further Reading

- [`SPEC.md`](../SPEC.md) -- Canonical specification
- [`constitution.md`](../constitution.md) -- Non-negotiable framework laws
- [`docs/decisions/`](decisions/) -- Architecture Decision Records (ADRs)
