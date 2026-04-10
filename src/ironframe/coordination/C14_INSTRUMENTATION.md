# C14 Instrumentation Notes, Eval Scaffold, and Verification Matrix

## Instrumentation Notes by File

### 1. roles_v1_0.py
- **Responsibility:** Role registry, capability declarations, role-task compatibility checking
- **C17 integration:** `AgentRole.autonomy_tier` must come from verified SessionToken, never agent-declared
- **Trace emissions:** None directly. Role violations surface as RoleViolation exceptions caught by protocol_v1_0.py which emits CoordinationHaltEvent with halt_reason=TRUST_VIOLATION

### 2. messages_v1_0.py
- **Responsibility:** AgentMessage dataclass, `effective_tier_for_receiver()`, MessageLog
- **C16 integration:** All messages validated against `coordination.message` schema before send/receive
- **C17 integration:** `sender_trust_tier` comes from OutputProvenance. `effective_tier_for_receiver()` computes `min(receiver_tier, sender_tier)`
- **Trace emission:** Emit `CoordinationMessageEvent` after validation and before dispatch. Required fields: effective_tier computed and recorded

### 3. tasks_v1_0.py
- **Responsibility:** SubTask, TaskGraph, topological sort, cycle detection, critical path priority
- **Key invariant:** `CircularDependency` raised at `add_task()` time, not at execution time
- **Trace emissions:** None directly. Task state changes surface through protocol_v1_0.py audit events

### 4. handoff_v1_0.py
- **Responsibility:** Result submission, orchestrator acknowledgment, pending result tracking
- **Key invariant:** Self-completion without orchestrator ACK = coordination anomaly
- **Trace emission:** Audit on RESULT submission and ACK/rejection transitions via `coordination.handoff.accepted` / `coordination.handoff.rejected`

### 5. loops_v1_0.py
- **Responsibility:** Repeated assignment detection, circular query detection, stall detection
- **Trace emission:** `LoopDetectedEvent` when threshold exceeded. If disposition=HALT, also triggers `CoordinationHaltEvent` via protocol_v1_0.py

### 6. resources_v1_0.py
- **Responsibility:** Request/release wrappers around C12 ResourceLockManager, priority queue by graph position
- **C12 integration:** All locks go through `ResourceLockManager.acquire()/release()`. C14 adds priority ordering.
- **Key invariant (INV-C14-LOCK-001):** Queue order = graph_priority DESC, then assignment_timestamp ASC. Never arrival-time.
- **Trace emission:** `ResourceLockEvent` on every grant, queue, release, and denial

### 7. protocol_v1_0.py
- **Responsibility:** Orchestration entrypoint. Assignment dispatch, escalation, halt handling.
- **Key invariant (INV-C14-AUDIT-001):** All major transitions logged to C7 before operation completes
- **Key invariant (INV-C14-TRUST-001):** Never allow direct agent-to-agent privilege escalation
- **Trace emissions:** `coordination.agent_registered`, `coordination.task_decomposed`, `coordination.task_assigned`, `coordination.message_sent`, `coordination.loop_detected`

---

## C13 Eval Scaffold

```python
from ironframe.eval.scenario_v1_0 import EvalScenario

c14_eval = EvalScenario(
    scenario_id="c14-multi-agent-clean",
    name="Multi-agent coordination without tier escalation",
    description="Two agents complete assigned tasks through structured protocol. "
                "Verifies trust propagation, loop detection absence, lock ordering, "
                "and clean governance signals.",
    component="C14",
    components=["C14", "C17"],
    requirements=["IF-REQ-004", "IF-REQ-004A", "IF-REQ-004B"],
    metrics=["coordination_stability", "trust_tier_enforcement", "lock_order_correctness"],
    risk_class="HAPPY_PATH",
    eval_method="behavioral_trace",
    check_anomaly=True,
    check_arbitration=False,
    check_freshness=False,
    pass_criteria="Two agents complete assigned tasks through structured protocol, "
                  "no effective tier exceeds min(sender, receiver), "
                  "no loop_detected event, no coordination_halt event, "
                  "shared resource granted by graph priority then timestamp",
    input_data={
        "agents": [
            {"agent_id": "orch-1", "type": "orchestrator", "tier": 3},
            {"agent_id": "worker-1", "type": "specialist", "tier": 2},
        ],
        "tasks": [
            {"task_id": "t1", "type": "research", "dependencies": []},
            {"task_id": "t2", "type": "write", "dependencies": ["t1"]},
        ],
        "expected_events": [
            "coordination.agent_registered",
            "coordination.task_decomposed",
            "coordination.task_assigned",
            "coordination.handoff.accepted",
        ],
        "forbidden_events": [
            "coordination.loop_detected",
            "coordination.halt",
        ],
    },
    expected_behavior="clean_protocol_completion",
)
```

### Harness assertions on emitted trace events:
1. Every `CoordinationMessageEvent.effective_tier` <= `sender_trust_tier`
2. Every `CoordinationMessageEvent.effective_tier` <= `receiver_declared_tier`
3. Zero `LoopDetectedEvent` records
4. Zero `CoordinationHaltEvent` records
5. All `ResourceLockEvent.disposition` entries follow priority order
6. All `CoordinationMessageEvent.audit_logged` == True
7. All `ResourceLockEvent.audit_logged` == True

---

## Verification Matrix

| Check ID | Scenario | Input | Expected Outcome | Evidence |
|----------|----------|-------|-------------------|----------|
| V-C14-001 | Import smoke test | `from ironframe.coordination import CoordinationProtocol` | No import error | Python import succeeds |
| V-C14-002 | Role registration | Register agent with capabilities | Agent appears in registry with declared role | `roles.get(agent_id).agent_type == declared_type` |
| V-C14-003 | Assignment schema | Send ASSIGNMENT message | C16 schema validation passes | CoordinationMessageEvent.audit_logged == True |
| V-C14-004 | Trust propagation | T2 sender -> T3 receiver | effective_tier == 2 | `msg.effective_tier_for_receiver(3) == 2` |
| V-C14-005 | Topological sort | 3 tasks with linear deps | Correct execution order | `graph.ready_tasks()` returns only dep-free tasks |
| V-C14-006 | Cycle rejection | Tasks with A->B->A deps | CircularDependency raised | Exception at `graph.add_task()` time |
| V-C14-007 | Handoff ACK | Agent submits RESULT | Pending until orchestrator ACK | `handoff.pending_count() > 0` before ACK |
| V-C14-008 | Loop detection | Same assignment 3x | LoopDetection returned | `loop.loop_detected == True, loop.loop_type == "repeat_assignment"` |
| V-C14-009 | Resource priority | Two agents, different graph priority | Higher priority granted first | ResourceLockEvent shows correct grant order |
| V-C14-010 | Eval clean pass | c14-multi-agent-clean scenario | effective_passed == True, governance_clean == True | All behavioral trace assertions pass |
