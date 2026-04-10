# Iron Frame -- Canonical Specification

**Version:** 1.1 | **Date:** 2026-04-08
**Status:** Authoritative. All implementation derives from this document.
**Update Rule:** Spec changes travel with code changes. Every Phase completion
requires a spec update before the next Phase begins.

---

## What Iron Frame Is

Iron Frame is the **infrastructure reliability layer** for LLM-powered systems. It sits between the raw model and any domain application -- trading, healthcare, compliance, research -- and handles every fundamental limitation of LLMs: hallucinations, reasoning errors, context drift, bias accumulation, and incomplete process execution.

It does not do domain work. It ensures that whatever domain system runs on top of it can trust the foundation beneath it.

The core promise is four words: **reliable, trustworthy, accurate, diligent**.

Every component exists to enforce one or more of those properties. A system running on Iron Frame passes audits, enforces processes, catches its own errors, and leaves a traceable record of every decision.

---

## Hard Constraints

1. **API-only.** Iron Frame NEVER depends on Claude Max, interactive chat sessions, or any specific IDE integration. All functionality is available through programmatic API calls. This is non-negotiable -- it is what makes Iron Frame a product, not a personal workflow hack.

2. **Zero domain imports.** The `ironframe/` package imports ONLY stdlib and declared dependencies (`anthropic`, `openai`). It never imports from Brian's domain code or any application built on top of it. The boundary test: delete everything outside `ironframe/` and the package still works.

3. **Model agnostic.** The model is swappable infrastructure, not a trusted source of truth. If Claude is replaced by GPT-5, Gemini, or a local Llama variant, Iron Frame's guarantees hold. This means genuine capability-aware routing, not a thin wrapper that normalizes to the lowest common denominator.

4. **Self-auditing from day 1.** Confidence scoring, self-consistency checks, and divergence detection run on every output as standard infrastructure, not optional add-ons.

5. **Compliance-ready from day 1.** The audit schema captures HIPAA/FINRA/SOC2 fields from the start. Not stubs -- the data structure IS compliance-ready. Enforcement adapters come later, but the data they need is already being captured.

6. **Immutable audit trail.** Logs are written before outputs are released (write-before-release). Logs cannot be modified after writing. If logging fails, the operation does not complete.

---

## Guiding Principles

### Architecture Agnosticism
Iron Frame makes no assumptions about which LLM is running beneath it. Capability-aware routing, model-specific prompt adapters, and intelligent fallback chains -- not a thin normalization layer.

### Separation of Concerns
Iron Frame is not a trading system, research agent, or clinical tool. Domain systems sit *on top of* Iron Frame. This boundary is strict. Iron Frame provides a surface with defined contracts; domain applications consume that surface.

### Hooks Are Enforced Outside the LLM
The single most important architectural decision: hooks execute **outside the LLM's context window**. A model cannot rationalize around them, forget them, or skip them due to context pressure. Deterministic gates operate at the platform level, not the prompt level.

### Self-Auditing Is First-Class
The system knows when it doesn't know. Outputs below confidence thresholds do not pass silently -- they are flagged, routed, or escalated.

### Streaming Is an Architectural Requirement
Streaming responses require special handling for write-before-release. The audit log uses an open/close pattern: entry opened when stream starts (logs input, model, session), entry closed when stream completes (adds output hash, confidence, token count). If a stream fails mid-way, the entry is closed with error status. (CriticMode correction: streaming gap.)

### Spend Caps Are Mandatory
Tier escalation without budget ceiling is a production risk. Per-request, per-session, and per-day spend caps are enforced. If budget is exhausted, the system returns the best result from the highest completed tier plus a disclosure. (CriticMode correction: runaway spend.)

---

## Core Components

### 1. Model Abstraction Layer (MAL)

The MAL is the only component that touches the LLM directly. It provides a normalized interface so all upstream components are model-agnostic.

**Responsibilities:**
- Unified API contract regardless of provider (Anthropic, OpenAI, Perplexity, local models)
- **Capability-based routing:** tasks routed by preference ("fast", "smart", "cheap", "verification", "long-context"), not model names
- Model-specific prompt adapters
- Fallback chain execution: if Model A fails or returns low confidence, escalate to Model B
- Token budget management and context window tracking
- **Spend tracking:** every call records cost; budget checked before each request

**Key design note:** MAL does not perform validation or auditing. Its single job is clean, normalized communication with models. All quality guarantees happen in downstream components.

### 2. Immutable Audit Log

The audit log is a write-once, append-only record of every significant event. It is the foundation of trust.

**Every logged event contains:**
- Timestamp and session ID
- Event type and component that generated it
- Input hash (SHA-256, not full input -- for PHI/PII safety)
- Output summary (truncated, configurable length)
- Confidence score, band, and contributing signals
- Model identity, provider, tokens in/out, cost in USD
- Hook execution results (pass/fail/escalated)
- Active compliance adapters
- Data lineage (source input IDs, reasoning chain reference)
- Retention class (set by compliance adapters, e.g., "7yr" for FINRA)

**Design requirements:**
- Write-before-release for non-streaming. Stream-close-before-return for streaming.
- Logs cannot be modified after writing (append-only)
- Log schema is stable and versioned
- Logs are structured for machine query (JSONL for dev, indexed storage for production)
- Full data lineage traceable from any output back to source inputs

**Storage roadmap:** JSONL for development and solo use. SQLite or Parquet for indexed queries at product volume. The schema is identical either way. (CriticMode correction: JSONL scaling.)

### 3. Skill Registry & Loader

Skills are knowledge modules -- structured documents that tell an agent what it needs to know for a specific category of work.

**Responsibilities:**
- Versioned catalog of all available skills
- Two loading modes: on-demand (task-matched) and preloaded (session start)
- Just-in-time loading -- agents load only relevant skills, not a monolithic context blob
- Skill activation state tracking per session
- Skill dependencies (Skill B requires Skill A)
- Skill validation before activation

**Skill tiers:**

| Tier | Scope | Examples |
|------|-------|---------|
| Core | Iron Frame internal | audit_logging, confidence_scoring, process_enforcement |
| Domain | Application-specific | financial_analysis, research_methodology |
| Protocol | Regulatory/external | HIPAA_adapter, FINRA_adapter, SOC2_adapter |

### 4. State Machine / Session Manager

Tracks where any given task or conversation is in its lifecycle.

**Responsibilities:**
- Persistent session state: active skills, completed steps, pending validations, confidence history, escalation flags
- Phase model enforcement: tasks move through defined phases and cannot skip without explicit authorization
- State corruption detection and recovery
- Current state context provided to hooks at every checkpoint
- Session memory: what has been asserted, validated, and what remains unverified

**Key design decision:** State files stay separate. The session coordinator reads/writes multiple backing stores but does NOT merge them into one file. Each keeps its own scope and failure domain. Corruption in one does not take out the others. (CriticMode correction: state unification fragility.)

### 5. Hook Engine

Hooks are deterministic enforcement gates that wrap every significant execution event. They run outside the LLM's reasoning loop.

**Hook types:**

| Hook | Fires | Purpose |
|------|-------|---------|
| `pre-skill` | Before skill activation | Validates prerequisites, checks state |
| `post-skill` | After skill completion | Verifies output meets skill contract |
| `pre-execution` | Before any tool or action | Authorization, parameter validation |
| `post-execution` | After any tool or action | Output validation, side-effect logging |
| `completion-gate` | Before task marked complete | Enforces all required steps done |
| `escalation` | On threshold breach | Routes to human review or fallback |
| `session-start` | At session initialization | Injects base policies + compliance context |
| `session-end` | At session close | Forces audit log finalization |

Hooks are composable. Multiple hooks chain on the same event. Order is deterministic. A hook failure halts execution by default unless marked `non-blocking` with a defined fallback.

**Dual implementation:** Bash hooks for Claude Code sessions (existing pattern). Python-native hook engine for API/product workflows (no bash dependency).

### 6. Self-Audit Engine (SAE)

Iron Frame's continuous self-monitoring component.

**SAE Verification Tiers:**

| Tier | What | Typical Cost | Implementation |
|------|------|-------------|----------------|
| 0 | Prompt-embedded logic (Toulmin/CQoT) | Free | Prompt addendum, no API call |
| 1 | Same-model judge call | ~$0.001 | Fast/cheap model via MAL |
| 2 | Self-consistency (3 samples) | ~$0.01 | Same model, varied temperature |
| 3 | Cross-model verification | ~$0.02 | Different model family (Perplexity) |
| 4 | Symbolic solver (Z3/Prolog) | ~$0.001 | Deterministic compute |

**Tier 3 uses cross-model verification, NOT same-family debate.** The proven pattern: use Perplexity (web-grounded, different training data) to verify Claude output. This avoids the NeurIPS finding that same-family models converge on shared errors rather than catching them. (CriticMode correction: multi-agent debate fails on same-family models.)

**Core mechanisms:**
- **Confidence scoring:** Multi-signal scoring with configurable bands (HIGH >0.8 / MEDIUM 0.5-0.8 / LOW 0.2-0.5 / UNACCEPTABLE <0.2). Domain-pluggable: base scorer + domain-specific signal plugins. (CriticMode correction: confidence generalization.)
- **Self-consistency checking:** Regenerate claims multiple times; unstable claims flagged as potential hallucinations
- **LLM-as-judge:** Separate judge model evaluates specific factual claims, not holistic quality
- **Reasoning chain audit:** Each step in CoT validated individually; broken chains flagged even if final answer looks correct
- **Divergence detection:** Monitors for behavioral drift -- tone shifts, precision changes, scope creep, reasoning pattern changes
- **Escalation routing:** Composite trust score per output. Below threshold: retry, fallback model, human-in-the-loop, or halt

**Budget enforcement:** Router checks `BudgetTracker` before escalating to a higher tier. If budget exhausted mid-escalation, returns best completed result plus confidence disclosure. Compliance adapters can set minimum tier floors (e.g., HIPAA analytical output = Tier 2+).

### 7. Logic Skills

Python modules that implement formal argumentation and reasoning validation. These serve double duty: Tier 0 prompt addenda for the SAE, and standalone Claude Code skills.

**Toulmin Argumentation Schema:**
Every argument decomposed into six components: Claim, Grounds, Warrant, Backing, Qualifier, Rebuttal. Forces explicit articulation of WHY a conclusion follows from evidence.

**Critical Questions of Thought (CQoT):**
Battery of critical questions targeting every element of an argument schema before producing a final answer. Based on December 2024 research operationalizing Toulmin for LLMs.

1. LLM reasons through query, separating premises from conclusions (no final answer yet)
2. Each conclusion checked: Is the claim supported? Does the warrant connect evidence to claim? Rebuttals considered?
3. Final response produced only after validity check

**Fallacy Detection:**
29+ fallacy taxonomy with stepwise binary classification. Relational knowledge graph of fallacy relationships as verification step.

**Premise-Conclusion Decomposition:**
```
P1: [premise]
P2: [premise]
...
-> C1: [conclusion, derived from P1, P2]
```
Forces traceable reasoning chains where errors become visible.

### 8. Compliance Adapter Layer (CAL)

Pluggable protocol module. Iron Frame becomes "HIPAA-compliant" or "FINRA-compliant" by loading the appropriate adapter, not by baking regulatory logic into the core.

Each adapter is a **skill + hook bundle**:
- The skill defines what the protocol requires
- The hooks enforce those requirements at every execution checkpoint
- The adapter registers itself with the Hook Engine on load

**Audit requirements already documented:**

| Protocol | Key Requirements |
|----------|-----------------|
| HIPAA | PHI detection/redaction, encryption tags, 6yr retention, access audit, minimum-necessary |
| FINRA | Recordkeeping completeness, customer-output review, transaction trail, 7yr retention |
| SOC2 | Access control logging, change management trail, availability monitoring |

The audit schema (`schema_v1_0.py`) captures the union of these requirements from day 1. Compliance adapters interpret and enforce protocol-specific rules later, but the data is already there.

### 9. Error Recovery & Resilience Engine

LLMs fail in non-obvious ways -- not crashes, but silent degradations: partial answers, plausible-but-wrong outputs, truncated reasoning, context overflow.

**Mechanisms:**
- **Circuit breaker:** Error rate tracking per component. Opens on threshold, cool-down timer, prevents cascading failures
- **Retry with variation:** Failed generations retried with modified prompts or different models, not identical retries. Error context preserved (rate limit vs content policy vs reasoning error)
- **Partial output recovery:** Valid portions isolated, flagged, and returned rather than discarding everything
- **Graceful degradation:** Explicit fallback behaviors per task type: abstain, escalate, partial answer with confidence disclosure, or hard halt
- **State rollback:** Corrupt or unrecoverable session state rolls back to last verified checkpoint

### 10. Context Manager (C9)

Actively manages context window budget to prevent token waste and maintain output quality.

**Responsibilities:**
- Context zone management (priority-based allocation)
- Aggressive compression when budget thresholds approached
- Context staleness detection (rot detector)
- Trust-aware compression (preserves high-trust context over low-trust)
- Skill-tier context allocation
- Telemetry on context usage patterns

**RTM:** IF-REQ-006

### 11. Knowledge Base Grounding (C10)

Retrieves, validates, and grounds LLM outputs against stored knowledge with freshness tracking and conflict arbitration.

**Responsibilities:**
- Storage and retrieval of structured knowledge entries
- Freshness scoring and staleness detection
- Conflict arbitration when KB entries contradict
- Write policies (who can write what class of knowledge)
- Output grounding -- linking claims to KB evidence
- Migration support for schema evolution

**RTM:** IF-REQ-013

### 12. Security Engine (C11)

Detects, sanitizes, and logs adversarial inputs including prompt injection attempts.

**Responsibilities:**
- Prompt injection detection (pattern-based + semantic)
- Input sanitization
- Security gate enforcement (block/warn/log)
- Threat logging for forensic analysis
- Trust assessment for input sources

**RTM:** IF-REQ-014

### 13. Tool Governance (C12)

Governs all tool access through declared contracts, rate limiting, authentication, and versioning.

**Responsibilities:**
- Tool registry with versioned contracts
- Rate limiting per tool and per session
- Authentication and authorization checks
- Resource lock management (used by C14 coordination)
- Tool versioning for stable interfaces

**RTM:** IF-REQ-002, IF-REQ-008

### 14. Eval Harness (C13)

Evaluates component behavior via benchmark scenarios with governance signal checks and regression gates.

**Responsibilities:**
- Scenario library (HAPPY_PATH, EDGE_CASE, ADVERSARIAL, REGRESSION)
- Multiple eval methods (exact_match, semantic_similarity, behavioral_trace, adversarial_probe, llm_judge)
- Governance signal checks on every eval run
- Regression gates that block releases on failure
- RTM coverage mapping (scenarios linked to requirements)

**RTM:** IF-REQ-012

### 15. Multi-Agent Coordination (C14)

Structured protocol for multi-agent task decomposition, messaging, and resource coordination.

**Responsibilities:**
- Agent role registry with declared capabilities
- Structured message protocol (no freeform natural language for operational coordination)
- Task decomposition graph with dependency management and cycle detection
- Handoff protocol requiring orchestrator acknowledgment
- Loop detection with automatic halt
- Resource coordination via graph-priority lock ordering

**Safety invariants:**
- No message may cause trust escalation (effective_tier = min(sender, receiver))
- Shared resources serialized by graph priority
- Loop detection triggers halt when threshold exceeded
- Handoffs require orchestrator acknowledgment

**RTM:** IF-REQ-004, IF-REQ-004A, IF-REQ-004B, IF-REQ-004C, IF-REQ-004D

### 16. Cost/Latency Budget Manager (C15)

Per-task budget profiles with SLA enforcement, routing signals, and telemetry.

**Responsibilities:**
- Task budget profiles (token budget, latency SLA, cost ceiling, enforcement tier)
- Real-time budget ledger per session
- SLA enforcement with three thresholds: Warning (60%), Degradation (80%), Breach (100%)
- Routing signals to MAL for model selection under budget pressure
- Reliability overhead tracking (hooks, schema checks, eval, audit are visible costs)
- Budget telemetry and snapshots

**Enforcement tiers:** HARD (block on breach), SOFT (warn and degrade), TRACK (observe only)

**RTM:** IF-REQ-009, IF-REQ-010

### 17. I/O Schema Validation (C16)

Validates all tool call inputs and outputs against declared schemas at governed boundaries.

**Responsibilities:**
- Schema registry (versioned, loaded from JSON)
- Payload validation with field-level error diagnostics
- Three coercion modes: STRICT, PERMISSIVE, REPORT_ONLY
- Boundary point definitions for governed validation
- Schema drift detection
- Actionable error messages for recovery (C8 integration)

**RTM:** IF-REQ-008

### 18. Agent Trust & Identity (C17)

Manages agent identity, autonomy tiers, and trust enforcement.

**Responsibilities:**
- Four autonomy tiers: OBSERVE (1), LIMITED (2), STANDARD (3), ELEVATED (4)
- HMAC-SHA256 signed session tokens (single source of truth for identity)
- Tier-based permission enforcement (read/write KB, tool calls, external tools, canonical writes)
- Anomaly detection for trust violations
- Kill switch for agent termination
- Output provenance tracking

**Key design:** Agents cannot self-declare tiers. Any attempt to claim a higher tier than the token grants is ignored and logged as anomaly. Tier elevation requires re-attestation, not model assertion.

**RTM:** IF-REQ-007

### 19. Spec Conformance & Drift Engine (C18)

Verifies Iron Frame against its own architecture specification.

**Sub-components:**
- **18a RTM Registry:** Machine-readable requirements traceability matrix (22 requirements)
- **18b Static Checker:** CI/CD gate checking RTM completeness, architecture boundary violations, orphan artifacts, invariant coverage
- **18c Runtime Monitor:** Non-blocking side-channel observer evaluating invariants against trace events
- **18d Drift Reporter:** Baseline management and drift differential reporting

**Drift taxonomy:** CODE_SPEC_MISMATCH, ARCH_BOUNDARY_VIOLATION, ORPHAN_ARTIFACT, INVARIANT_NOT_VERIFIED, RTM_COVERAGE_GAP, PROTO_VIOLATION, TRUST_ESCALATION, LOCK_PRIORITY_VIOLATION, LOOP_HANDLING_FAILURE, AUDIT_GAP, UNSPECIFIED_BEHAVIOR

**RTM:** IF-REQ-005

---

## The Skill-State-Hook Flow

Every task execution follows this cycle:

```
1. INTAKE
   Session Manager initializes state object
   Session-start hook fires -> injects base policies + active compliance adapters

2. SKILL LOADING
   Skill Registry matches task to required skills
   pre-skill hooks validate prerequisites
   Skills loaded just-in-time into agent context
   post-skill hooks confirm skill activation

3. EXECUTION
   pre-execution hooks authorize the action
   MAL sends request to appropriate model (budget checked first)
   LLM generates output

4. SELF-AUDIT
   SAE scores output for confidence, consistency, hallucination risk
   CoT chain validated step-by-step if applicable
   Judge model runs if confidence is borderline
   Budget checked before any tier escalation

5. HOOK VALIDATION
   post-execution hooks run (compliance checks, output schema validation)
   Compliance adapter hooks enforce protocol-specific requirements
   Results logged to immutable audit trail (write-before-release)

6. ROUTING
   High confidence -> output released
   Medium confidence -> output released with confidence disclosure
   Low confidence -> retry or escalate
   Unacceptable -> halt, log, alert

7. COMPLETION GATE
   completion-gate hook verifies ALL required process steps complete
   State machine confirms no phase was skipped
   Final audit log entry written
   session-end hook fires
```

No step can be skipped. The completion gate prevents declaring success on incomplete work.

---

## Personal System vs. Sellable Product

Iron Frame means the same thing in both contexts. The implementation boundaries differ.

| Dimension | Brian's System | Sellable Product |
|-----------|---------------|------------------|
| Config | `.env` file via `IronFrameConfig.from_env_file()` | Env vars or JSON via `from_env()` / `from_json()` |
| Model binding | Claude-optimized adapters with fallback | Fully model-agnostic, no preferred provider |
| Compliance | Personal finance + research protocols | Full adapter library: HIPAA, FINRA, SOC2, custom |
| Confidence thresholds | Tuned to trading/research risk tolerance | Configurable per deployment |
| Audit log | Local JSONL | Multi-tenant, isolated per client, indexed storage |
| Skill Registry | Personal skills catalog | Versioned public + private skill namespaces |
| Hook Engine | Bash hooks (Claude Code) + Python engine | Python-native SDK for custom hooks |
| Certification | Internal | SOC2 Type II, HIPAA BAA-eligible, FedRAMP-ready |
| Orchestration | Single-tenant, direct integration | Multi-tenant API with tenant isolation |

The core engine -- MAL, SAE, Hook Engine, Skill Registry, State Machine, Audit Log -- is identical.

---

## What Iron Frame Is Not

- **Not a domain system.** Trading logic, research methodologies, clinical decision support live in applications built on Iron Frame, not inside it.
- **Not a model fine-tune.** Iron Frame does not modify the model. It wraps, validates, and enforces around it.
- **Not a chat interface.** Iron Frame has no user-facing layer. It is infrastructure consumed by applications.
- **Not a hallucination eliminator.** Hallucinations are structural. Iron Frame detects, flags, and routes around them -- it does not prevent them at the model level.
- **Not dependent on interactive sessions.** Everything works through API calls. No Claude Max, no IDE, no interactive chat required.

---

## Integration Points

**All wired (Phase 3 complete):**
- C12 -> C14: ResourceLockManager called from coordination protocol
- C17 -> C14: Trust tier enforcement applied to coordination messages
- C14 -> C7: Coordination halts written to audit log
- C15 -> C7: SLA breaches written to audit log
- C14 -> C18: Coordination events reach RuntimeMonitor.observe()
- C15 -> C18: SLA violations reach RuntimeMonitor.observe()
- C18 -> C13: c18-static-clean, c18-trust-drift, c18-rtm-gap scenarios registered

---

## Decision Log

See `docs/decisions/` for full ADRs.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| ADR-001 | Hooks execute outside LLM context window | Accepted | 2026-04-08 |
| ADR-002 | Open-core licensing model (MIT core, commercial adapters) | Accepted | 2026-04-08 |

---

## Phases

| Phase | Status | Baseline | Notes |
|-------|--------|----------|-------|
| Phase 1 | Complete | -- | 9 core components built |
| Phase 2 | Complete | bdf57917-c62 | 18 components, all contracts, RTM seeded |
| Phase 3 | Complete | 42595777 | 3 wiring gaps closed, 48 tests, RTM expanded to 22 reqs |

---

## Package Structure

```
ironframe/
  __init__.py                    # Version string, public API
  SPEC.md                        # This file
  config_v1_0.py                 # Pluggable config (env vars, .env, JSON)
  test_harness_v1_0.py           # End-to-end harness (real API calls)
  mal/                           # Model Abstraction Layer (C1)
    client_v1_0.py               # IronFrameClient -- unified interface
    router_v1_0.py               # Capability-aware routing + spend tracking
    budget_v1_0.py               # Per-request, per-session, per-day spend caps
    adapters/
      anthropic_v1_0.py          # Anthropic Messages API adapter
      perplexity_v1_0.py         # Perplexity Sonar adapter
  skills/                        # Skill Registry (C2)
    registry_v1_0.py             # Catalog, versioning, dependency resolution
  state/                         # State Machine (C3)
    session_v1_0.py              # Session coordinator (does NOT merge stores)
    phase_v1_0.py                # Generic phase gate enforcement
  hooks/                         # Hook Engine (C4)
    engine_v1_0.py               # Programmatic hook registration + execution
  sae/                           # Self-Audit Engine (C5)
    confidence_v1_0.py           # Generalized confidence scoring
    judge_v1_0.py                # LLM-as-judge (via MAL)
    cross_model_v1_0.py          # Cross-model verification (different family)
    tiers_v1_0.py                # Verification tier router with spend caps
  logic/                         # Logic Skills (C6)
    toulmin_v1_0.py              # Toulmin argument schema + validation
    cqot_v1_0.py                 # Critical Questions of Thought battery
    fallacy_v1_0.py              # 29+ fallacy taxonomy
  audit/                         # Immutable Audit Log (C7)
    schema_v1_0.py               # AuditEvent dataclass -- compliance-ready
    logger_v1_0.py               # Append-only JSONL writer
    stream_logger_v1_0.py        # Streaming open/close pattern
  recovery/                      # Error Recovery (C8)
    circuit_breaker_v1_0.py      # Error rate tracking + circuit open/close
    retry_v1_0.py                # Retry with variation
  context/                       # Context Manager (C9)
    manager_v1_0.py              # Context budget orchestrator
    compression_v1_0.py          # Aggressive context compression
    budget_v1_0.py               # Context token budget tracking
    rot_detector_v1_0.py         # Context staleness detection
    zones_v1_0.py                # Context zone management
    skill_tier_v1_0.py           # Skill-tier context allocation
    trust_preservation_v1_0.py   # Trust-aware compression
    telemetry_v1_0.py            # Context usage telemetry
  kb/                            # Knowledge Base Grounding (C10)
    manager_v1_0.py              # KB orchestrator
    storage_v1_0.py              # KB entry storage
    retrieval_v1_0.py            # KB retrieval engine
    freshness_v1_0.py            # Freshness scoring
    grounding_v1_0.py            # Output grounding against KB
    write_v1_0.py                # KB write policies
    arbitration_v1_0.py          # Conflict arbitration
    policy_v1_0.py               # KB access policies
    migration_v1_0.py            # Schema migration support
  security/                      # Security Engine (C11)
    engine_v1_0.py               # Security orchestrator
    detection_v1_0.py            # Prompt injection detection
    sanitize_v1_0.py             # Input sanitization
    gate_v1_0.py                 # Security gate enforcement
    threat_log_v1_0.py           # Threat logging
    trust_v1_0.py                # Input source trust assessment
  tool_governance/               # Tool Governance (C12)
    governor_v1_0.py             # Tool governance orchestrator
    registry_v1_0.py             # Tool registry
    locks_v1_0.py                # Resource lock manager
    rate_limit_v1_0.py           # Rate limiting
    auth_v1_0.py                 # Tool authentication
    contract_v1_0.py             # Tool contracts
    versioning_v1_0.py           # Tool versioning
  eval/                          # Eval Harness (C13)
    runner_v1_0.py               # Eval suite runner
    scenario_v1_0.py             # Scenario library
    methods_v1_0.py              # Eval method implementations
    gates_v1_0.py                # Regression gates
    isolation_v1_0.py            # Eval environment isolation
    feedback_v1_0.py             # Eval feedback collection
    scenarios/                   # Scenario definitions
      c18_scenarios.py           # C18 conformance scenarios
  coordination/                  # Multi-Agent Coordination (C14)
    protocol_v1_0.py             # Coordination protocol orchestrator
    messages_v1_0.py             # Structured message protocol
    roles_v1_0.py                # Agent role registry
    tasks_v1_0.py                # Task decomposition graph
    handoff_v1_0.py              # Handoff protocol
    loops_v1_0.py                # Loop detection
    resources_v1_0.py            # Resource coordination
  budget/                        # Cost/Latency Budget Manager (C15)
    manager_v1_0.py              # Budget orchestrator
    profiles_v1_0.py             # Task budget profiles
    ledger_v1_0.py               # Real-time budget ledger
    sla_v1_0.py                  # SLA enforcement
    routing_v1_0.py              # Budget routing signals
    telemetry_v1_0.py            # Budget telemetry
  io_schema/                     # I/O Schema Validation (C16)
    validator_v1_0.py            # Core validation engine
    registry_v1_0.py             # Schema registry
    errors_v1_0.py               # Actionable error diagnostics
    coercion_v1_0.py             # Output coercion policy
    boundaries_v1_0.py           # Boundary point definitions
    drift_v1_0.py                # Schema drift detection
  agent_trust/                   # Agent Trust & Identity (C17)
    tiers_v1_0.py                # Autonomy tiers with blast radius
    identity_v1_0.py             # HMAC-signed session tokens
    permissions_v1_0.py          # Tier-based permission enforcement
    provenance_v1_0.py           # Output provenance tracking
    anomaly_v1_0.py              # Trust anomaly detection
    engine_v1_0.py               # Agent trust orchestrator
    kill_switch_v1_0.py          # Agent termination
  conformance/                   # Spec Conformance & Drift (C18)
    engine_v1_0.py               # Conformance orchestrator
    rtm_v1_0.py                  # Requirements traceability matrix
    static_checker_v1_0.py       # CI/CD gate
    runtime_monitor_v1_0.py      # Runtime invariant monitor
    drift_reporter_v1_0.py       # Baseline + drift differential
  compliance/                    # Compliance Adapter Layer
    base_v1_0.py                 # Base adapter contract
    audit_requirements_v1_0.py   # What HIPAA/FINRA/SOC2 demand of audit
  contracts/                     # Component contracts (JSON)
  schemas/                       # I/O schemas (JSON)
  tests/                         # pytest suite (48 tests)
  docs/                          # Documentation
    decisions/                   # Architecture Decision Records
```

---

## Dependencies

**Required:** `anthropic` (for Anthropic adapter)
**Optional:** `openai` (for OpenAI/Perplexity adapters), `z3-solver` (for Tier 4 symbolic verification)
**Stdlib only:** Everything else uses Python stdlib (dataclasses, json, hashlib, pathlib, datetime, uuid, enum, typing)

---

## CriticMode Corrections Applied

| Finding | Resolution |
|---------|-----------|
| Import direction blocker | Non-issue. `config_v1_0.py` is Iron Frame's own loader. No import from Brian's code. |
| "Is this a product?" | Brian decided yes. Plan stays product-scoped. |
| Multi-agent debate fails same-family | Replaced with cross-model verification (Perplexity checks Claude). Brian's scimode pattern. |
| Streaming breaks audit | Added `stream_logger_v1_0.py` with open/close pattern. |
| No spend caps | Added `budget_v1_0.py` -- per-request, per-session, per-day caps. Router checks before escalation. |
| JSONL doesn't scale | JSONL for dev. SQLite/Parquet for production. Schema identical either way. |
| Compliance as stubs | Audit requirements documented. Schema captures compliance fields from day 1. |
| State unification fragility | State files stay separate. Coordinator reads/writes but does not merge. |
| Confidence doesn't generalize | Domain-pluggable: base scorer + domain-specific signal plugins. |
