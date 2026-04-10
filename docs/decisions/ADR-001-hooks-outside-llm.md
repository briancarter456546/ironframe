# ADR-001: Hooks Execute Outside LLM Context Window

**Date:** 2026-04-08
**Status:** Accepted

## Context

LLM-based agent systems require enforcement points that guarantee process
compliance, output validation, and audit logging. The naive implementation
places these enforcement instructions inside the prompt -- as system prompt
rules or chain-of-thought constraints.

## Decision

All hooks in Iron Frame execute outside the LLM's context window, at the
platform/orchestration layer. The model has no visibility into hook logic
and cannot influence whether hooks fire.

## Reasoning

- A model operating under context pressure (long sessions, complex tasks)
  can drop, abbreviate, or rationalize around prompt-level instructions
- Prompt-level rules are not auditable -- there is no deterministic record
  of whether a rule was applied
- Platform-level hooks are deterministic: they either fire or they don't,
  and the outcome is logged regardless of model behavior
- This is the architectural property that makes Iron Frame's compliance
  guarantees meaningful rather than aspirational

## Alternatives Considered

- **Prompt-level enforcement:** Rejected. Model can rationalize around it.
  Not auditable. Degrades under context pressure.
- **Post-hoc output filtering:** Rejected as sole mechanism. Catches some
  errors but does not enforce process completeness or prevent partial execution.

## Consequences

- Hook logic must be maintained separately from prompt logic
- Adds orchestration complexity (hooks are platform code, not prompt text)
- Enables deterministic audit trail -- hooks produce verifiable log entries
  the model cannot suppress
- Is the primary architectural differentiator from competitor guardrail systems
