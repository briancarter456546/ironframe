# ADR-002: Open-Core Licensing Model (MIT Core, Commercial Adapters)

**Date:** 2026-04-08
**Status:** Accepted

## Context

Iron Frame needs a licensing strategy that balances open adoption with
sustainable revenue. The core engine provides value to any LLM application;
compliance adapters and enterprise features provide value to specific
regulated industries willing to pay.

## Decision

MIT license for the core Iron Frame engine. Commercial license for
compliance adapters (HIPAA, FINRA, SOC2), enterprise features
(multi-tenant isolation, SSO, SLA guarantees), and professional support.

## Reasoning

- MIT core maximizes adoption and community contribution
- Compliance adapters require domain expertise and ongoing maintenance
  that justifies commercial licensing
- Enterprise features (multi-tenancy, audit isolation) are not needed
  by individual developers or small teams
- This model is proven by PostHog, GitLab, Supabase, and similar
  infrastructure companies

## Alternatives Considered

- **Fully open source (AGPL):** Rejected. AGPL discourages enterprise
  adoption and does not generate revenue directly.
- **Fully proprietary:** Rejected. Limits adoption, makes community
  building impossible, and positions poorly against open alternatives.
- **Source-available (BSL/SSPL):** Considered. Too restrictive for
  the adoption-first strategy needed at this stage.

## Consequences

- Must maintain a clear boundary between MIT core and commercial modules
- Community can contribute to core but not to commercial adapters
- Pricing must reflect value delivered, not feature gating
- The `ironframe/` package must work completely without commercial modules
