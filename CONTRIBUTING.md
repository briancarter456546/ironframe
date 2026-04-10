# Contributing to Iron Frame

## Spec Changes Travel with Code Changes

Any PR that modifies a component must include a corresponding update to
`SPEC.md`. This is non-negotiable. The spec is a living document that
reflects the current state of the system.

**Update triggers:**

| Event | Spec update required |
|-------|---------------------|
| New component added | Add component section to SPEC.md |
| Phase completed | Update Integration Points + Phases table |
| Architecture decision changed | Update relevant component + add ADR in docs/decisions/ |
| New compliance adapter built | Add to Compliance Adapter Layer section |
| Integration point wired/changed | Update Integration Points section |

## Architecture Decision Records (ADRs)

Significant architectural decisions are recorded in `docs/decisions/` using
the template at `docs/decisions/ADR-000-template.md`.

ADRs capture **why** a choice was made, not just what was chosen. This
protects institutional knowledge across sessions and contributors.

## Code Standards

- All Python files versioned: `thing_v1_0.py`
- UTF-8 encoding on all file I/O
- ASCII only in code output (no unicode symbols)
- No domain imports inside `ironframe/` -- the package must work standalone
- Every component has a JSON contract in `contracts/`
- Tests in `tests/` -- no mocking of core Iron Frame components

## RTM Discipline

Every accepted requirement in the RTM (`conformance/rtm_v1_0.py`) must have:
- At least one implementation artifact
- At least one verification artifact

New code files should be linked to an existing IF-REQ or trigger a new one.
Run `ConformanceEngine().run_static_check()` to verify no orphans.
