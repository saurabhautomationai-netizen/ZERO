from zero_core.orchestrator import Orchestrator

def test_zero_orchestrator():
    orch = Orchestrator()
    res = orch.run('test task')
    assert res['status'] == 'completed'
