# C18 v1.1 Backlog

Items deferred from post18packet.txt. Current v1.0 passes all 11 tests.

1. **Stateful lock queue tracking for INV-C14-LOCK-001** — current check is stateless (queue_position==0 for GRANTED). v1.1: maintain `resource_lock_queues: dict[str, list[dict]]`, on QUEUED append, on GRANTED verify head-of-queue.

2. **Align RTMRegistry API** — current: `seed_rtm()` factory returns pre-seeded RTMRegistry. Target: `registry.seed_requirements()` method on the instance.

3. **Align StaticChecker API** — current: `StaticConformanceChecker(rtm, contracts_dir, code_dir).run()`. Target: `StaticChecker().check(registry, scan_paths)`.

4. **Align DriftReporter API** — current: reads from shared RTM/monitor references. Target: explicit parameters per method call (`registry`, `drifts`, `traces`).

5. **Canonical DriftEvent location** — current: defined in `runtime_monitor_v1_0.py`. Target: single shared types file or `rtm_v1_0.py`, no duplication risk.

6. **ConformanceEngine explicit state** — current: engine delegates to sub-components. Target: engine owns `_drifts: list`, `_traces: list`, `_observed_requirement_ids: set` as first-class state.
