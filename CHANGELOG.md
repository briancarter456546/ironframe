# Changelog

All notable changes to Iron Frame will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/briancarteraus/ironframe/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/briancarteraus/ironframe/releases/tag/v0.1.0
