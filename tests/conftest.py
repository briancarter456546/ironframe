import pytest


@pytest.fixture
def conformance_engine():
    from ironframe.conformance import ConformanceEngine
    return ConformanceEngine()


@pytest.fixture
def wired_engine():
    from ironframe.conformance import ConformanceEngine
    from ironframe.coordination import protocol_v1_0
    from ironframe.budget.manager_v1_0 import CostLatencyManager
    engine = ConformanceEngine()
    protocol_v1_0.register_conformance_engine(engine)
    mgr = CostLatencyManager()
    mgr.register_conformance_engine(engine)
    return engine, mgr


@pytest.fixture
def rtm_registry():
    from ironframe.conformance.rtm_v1_0 import seed_rtm
    return seed_rtm()


@pytest.fixture
def scenario_library():
    from ironframe.eval.scenario_v1_0 import ScenarioLibrary
    from ironframe.eval.scenarios.c18_scenarios import register_c18_scenarios
    lib = ScenarioLibrary()
    register_c18_scenarios(lib)
    return lib
