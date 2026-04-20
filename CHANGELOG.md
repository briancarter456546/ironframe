# Changelog

All notable changes to Iron Frame will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-04-20

### Fixed

- **Top-level import path.** `from ironframe import IronFrameClient` now
  works, matching the import pattern every 2026-era SDK ships with. In
  0.1.1 readers had to type `from ironframe.mal.client_v1_0 import
  IronFrameClient`, which is correct but surprising for a first-impression
  quickstart. Both import paths continue to work.

- **README quickstart.** Reduced to a single top-level import for the
  common case.

### Added

- `IronFrameClient` re-exported at the top level of the `ironframe`
  package (`ironframe/__init__.py`). Alongside `IronFrameConfig` and
  `IronFrameResponse`, the three classes a typical user interacts with
  are now all importable from `ironframe` directly.

- `IronFrameResponse` re-exported at the top level for the same reason.

### Unchanged

- Long-form paths (`from ironframe.mal.client_v1_0 import
  IronFrameClient`, `from ironframe.mal.response_v1_0 import
  IronFrameResponse`) continue to work. Pure re-export; no breakage.

## [0.1.1] - 2026-04-19

### Fixed

- **README quickstart accuracy.** `IronFrameClient.complete()` now returns an
  `IronFrameResponse` instead of a plain `dict`, so the attribute-access
  pattern documented in `README.md` (`response.content`, `response.cost`,
  `response.model`) works. Previously the README and the code disagreed:
  the README promised attributes, the code returned a dict, and a reader
  copy-pasting the quickstart hit `AttributeError` in the first 30 seconds.

- **README parameter name.** `client.complete()` uses `preference=`, not
  `capability=`. The README's `capability="smart"` was wrong against the
  actual signature; corrected in this release.

### Added

- `ironframe.mal.response_v1_0.IronFrameResponse` — a dict subclass with
  attribute properties. Exposed at `ironframe.mal.IronFrameResponse`.
  Canonical field access: `.text`, `.model`, `.provider`, `.tokens_in`,
  `.tokens_out`, `.cost_usd`, `.stop_reason`, `.preference`, `.session_id`.
  README-facing aliases: `.content` (→ text), `.cost` (→ cost_usd),
  `.confidence` (returns None unless a separate SAE step has populated
  it — raw MAL calls do not compute confidence; run `sae.verify()` to
  score).

- `IronFrameResponse.to_dict()` / `.raw` — return a plain-dict copy for
  callers that want decoupled serialisation.

- 18 new tests in `tests/test_mal_response.py` covering attribute access,
  dict backward compatibility (`isinstance`, `[]`, `.get`, `in`, `keys`,
  `items`, `json.dumps`, `**` unpacking), and to_dict round-trip copy
  semantics.

### Changed

- **No breaking API changes for dict-using consumers.** Every existing
  pattern (`response['text']`, `response.get('cost_usd')`,
  `isinstance(response, dict)`, `json.dumps(response)`, `**response`)
  continues to work unchanged because `IronFrameResponse` subclasses
  `dict`. Internal MAL, SAE, eval, and recovery modules required zero
  code changes.

### Unchanged

- `client.stream()` still yields plain dicts. The generator contract is
  intentionally different from `complete()` and is not wrapped.

## [0.1.0] - 2026-04-10

### Added

Initial public release.

- **18 core components** implementing the Iron Frame specification:
  1. Model Abstraction Layer (MAL) with Anthropic and OpenAI/Perplexity adapters
  2. Skill Registry with versioning and dependency resolution
  3. State Machine / Session Manager
  4. Hook Engine -- deterministic enforcement outside the LLM context window
  5. Self-Audit Engine (SAE) with tiered verification (0-4)
  6. Logic Skills (Toulmin, CQoT, fallacy detection)
  7. Immutable Audit Log with write-before-release semantics
  8. Error Recovery with circuit breakers and retry-with-variation
  9. Context Budget Manager
  10. KB Grounding Layer
  11. Security / Injection Defense (5-layer)
  12. Tool Governance
  13. Eval & Regression Framework
  14. Multi-Agent Coordination Protocol
  15. Cost/Latency Budget Manager with task profiles
  16. I/O Schema Validation
  17. Agent Trust & Identity with zero-trust tiers
  18. Spec Conformance & Drift Engine

- **5 compliance adapters** (source-available, commercial license required for production):
  HIPAA, FINRA, SOC2, SEC, GDPR

- **Requirements Traceability Matrix** with 22 tracked requirements mapped to components, code, and tests

- **Apache 2.0 core license** with explicit patent grant

[Unreleased]: https://github.com/briancarter456546/ironframe/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/briancarter456546/ironframe/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/briancarter456546/ironframe/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/briancarter456546/ironframe/releases/tag/v0.1.0
