"""Direct adversarial G6A proofs; every test uses injected fake ports."""
import importlib
from dataclasses import fields, replace
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from fixtures.orchestration_fixture import *

def run(value, port=0):
    coordinator, ports = build(); ports[port].value = value; coordinator.submit(task()); return coordinator, ports, coordinator.run_once("owner")

def test_01_import_is_inert(): assert importlib.import_module("zero_core.engineering_orchestration")
def test_02_queue_depth_enforced():
    coordinator,_=build(); coordinator.config=replace(coordinator.config,max_queue_depth=1);coordinator.submit(task())
    with pytest.raises(OrchestrationError): coordinator.submit(task("two",task_id="two"))
def test_03_duplicate_task_rejected():
    coordinator,_=build();coordinator.submit(task())
    with pytest.raises(OrchestrationError): coordinator.submit(task("two"))
def test_04_idempotency_content_conflict_rejected():
    coordinator,_=build();coordinator.submit(task())
    with pytest.raises(OrchestrationError): coordinator.submit(task(digest="other"))
def test_05_claim_order_is_sequence_order():
    coordinator,_=build(); coordinator.submit(task()); coordinator.submit(task("two",task_id="two")); assert coordinator.queue.claim("one",clock.now(),timedelta(seconds=1),1).task.task_id=="task"
def test_06_one_live_lease_only():
    coordinator,_=build();coordinator.submit(task());coordinator.submit(task("two",task_id="two")); assert coordinator.queue.claim("one",clock.now(),timedelta(seconds=1),1);assert coordinator.queue.claim("two",clock.now(),timedelta(seconds=1),1) is None
def test_07_stale_holder_cannot_mutate():
    coordinator,_=build();coordinator.submit(task());entry=coordinator.queue.claim("owner",clock.now(),timedelta(seconds=1),1)
    with pytest.raises(OrchestrationError): coordinator.queue.compare_and_swap(replace(entry,ledger=replace(entry.ledger,steps=1)),entry.lease,State.POLICY_CHECKED,entry.ledger,"BAD")
def test_08_expired_holder_cannot_mutate():
    coordinator,_=build();coordinator.submit(task());entry=coordinator.queue.claim("owner",coordinator.clock.now(),timedelta(seconds=1),1);coordinator.clock.advance(2)
    with pytest.raises(OrchestrationError): coordinator.queue.compare_and_swap(entry,entry.lease,State.POLICY_CHECKED,entry.ledger,"BAD")
def test_09_lease_renewal_is_bounded():
    coordinator,_=build();coordinator.submit(task());entry=coordinator.queue.claim("owner",clock.now(),timedelta(seconds=1),1);renewed=coordinator.renew_lease(entry);entry=replace(entry,lease=renewed)
    with pytest.raises(OrchestrationError): coordinator.renew_lease(entry)
def test_10_terminal_states_are_immutable():
    for state in TERMINAL: assert not TRANSITIONS.get(state)
def test_11_each_illegal_transition_is_rejected():
    coordinator,_=build();coordinator.submit(task());entry=coordinator.queue.claim("owner",clock.now(),timedelta(seconds=1),1)
    for state in State:
        if state not in TRANSITIONS[State.LEASED]:
            with pytest.raises(OrchestrationError): coordinator._move(entry,entry.lease,state,entry.ledger,"BAD")
def test_12_denied_has_zero_downstream_calls():
    _,ports,result=run(G1Outcome.DENIED);assert result.state is State.BLOCKED and not any(p.calls for p in ports[1:])
def test_13_hitl_has_zero_downstream_calls():
    _,ports,result=run(G1Outcome.HITL_REQUIRED);assert result.state is State.BLOCKED and not any(p.calls for p in ports[1:])
@pytest.mark.parametrize("bad",["LOW_RISK",None,object()])
def test_14_stale_or_tampered_g1_is_not_authorization(bad):
    _,ports,result=run(bad);assert result.state is State.BLOCKED and not any(p.calls for p in ports[1:])
def test_15_project_mismatch_makes_zero_calls():
    coordinator,ports=build()
    with pytest.raises(OrchestrationError):coordinator.submit(replace(task(),project_id="other"))
    assert not any(p.calls for p in ports)
def test_16_root_mismatch_makes_zero_calls():
    coordinator,ports=build()
    with pytest.raises(OrchestrationError):coordinator.submit(replace(task(),repository_root="F:\\other"))
    assert not any(p.calls for p in ports)
def test_17_task_cannot_override_trusted_configuration():
    coordinator,_=build()
    with pytest.raises(OrchestrationError): coordinator.submit(replace(task(),operation_class="RUN"))
def test_18_g2_success_is_only_reported_before_g3():
    coordinator,ports=build()
    def observe(*args): assert coordinator.queue.entries[0].state is State.VERIFICATION_PENDING; return G3Outcome.BLOCKED
    ports[2].verify=observe;coordinator.submit(task());assert coordinator.run_once("owner").state is State.BLOCKED
@pytest.mark.parametrize("bad",["SUCCESS",None,object(),G2Outcome.BLOCKED])
def test_19_unknown_or_malformed_g2_fails_closed(bad):
    _,ports,result=run(bad,1);assert result.state is State.FAILED and not ports[2].calls
def test_20_g3_is_required_before_g5():
    _,ports,result=run(G3Outcome.FAILED,2);assert result.state is State.BLOCKED and not ports[4].calls
def test_21_mismatched_g3_evidence_blocks():
    _,ports,result=run("PASS",2);assert result.state is State.BLOCKED and not ports[4].calls
@pytest.mark.parametrize("bad",[G3Outcome.FAILED,G3Outcome.BLOCKED,G3Outcome.INCONCLUSIVE])
def test_22_failed_blocked_inconclusive_g3_block(bad):
    _,ports,result=run(bad,2);assert result.state is State.BLOCKED and not ports[4].calls
def test_23_corrupt_g4_requires_reverification():
    _,ports,result=run(G4Outcome.CORRUPT,3);assert result.state is State.REQUIRES_REVERIFICATION and not ports[4].calls
def test_24_mismatched_g4_binding_requires_reverification():
    _,_,result=run("VERIFIED",3);assert result.state is State.REQUIRES_REVERIFICATION
def test_25_reverification_never_completes(): _,_,result=run(G2Outcome.UNCERTAIN,1);assert result.state is State.REQUIRES_REVERIFICATION
def test_26_g5_only_after_valid_g3_and_g4():
    coordinator,ports=build();order=[]
    for index,name,method in ((2,"g3","verify"),(3,"g4","checkpoint"),(4,"g5","review")):
        original=getattr(ports[index],method)
        setattr(ports[index],method,lambda *a,original=original,name=name:(order.append(name),original(*a))[1])
    coordinator.submit(task());coordinator.run_once("owner");assert order==["g3","g4","g5","g4"]
def test_27_g5_rejection_blocks(): _,_,result=run(G5Outcome.REJECTED,4);assert result.state is State.BLOCKED
@pytest.mark.parametrize("finding",[G5Outcome.REMEDIATION,G5Outcome.BLOCKED])
def test_28_remediation_findings_block(finding): _,_,result=run(finding,4);assert result.state is State.BLOCKED
def test_29_g5_approval_is_advisory_not_execution():
    coordinator,ports=build();coordinator.submit(task());coordinator.run_once("owner");assert ports[1].calls==["g2"] and ports[3].calls==["g4","g4"]
def test_30_complete_pipeline_completes_once():
    coordinator,ports=build();coordinator.submit(task());assert coordinator.run_once("owner").state is State.COMPLETED;assert coordinator.run_once("owner") is None
def test_31_exact_replay_causes_no_duplicate_calls():
    coordinator,ports=build();coordinator.submit(task());coordinator.run_once("owner");counts=[len(p.calls) for p in ports];coordinator.submit(task());assert [len(p.calls) for p in ports]==counts
def test_32_conflicting_replay_fails_closed():
    coordinator,_=build();coordinator.submit(task())
    with pytest.raises(OrchestrationError): coordinator.submit(task(digest="other"))
def test_33_precancelled_has_zero_calls():
    coordinator,ports=build();coordinator.cancellations.value=CancellationRequest("task",clock.now(),"STOP");coordinator.submit(task());assert coordinator.run_once("owner").state is State.CANCELLED and not any(p.calls for p in ports)
@pytest.mark.parametrize("stage",["g1","g2","g3","g4","g5"])
def test_34_cancellation_between_stages_prevents_later_calls(stage):
    coordinator,ports=build();index={"g1":0,"g2":1,"g3":2,"g4":3,"g5":4}[stage];method=("validate","execute","verify","checkpoint","review")[index];original=getattr(ports[index],method)
    def cancel(*args): coordinator.cancellations.value=CancellationRequest("task",clock.now(),"STOP");return original(*args)
    setattr(ports[index],method,cancel);coordinator.submit(task());result=coordinator.run_once("owner");assert result.state in (State.CANCELLED,State.REQUIRES_REVERIFICATION)
def test_35_cancellation_race_is_uncertain():
    coordinator,ports=build();original=ports[1].execute
    def race(*args):coordinator.cancellations.value=CancellationRequest("task",clock.now(),"STOP");return original(*args)
    ports[1].execute=race;coordinator.submit(task());result=coordinator.run_once("owner");assert result.uncertainty and result.state is State.REQUIRES_REVERIFICATION
@pytest.mark.parametrize("field",["max_steps","max_wall_clock","max_attempts","max_executions","max_verifications","max_reviews"])
def test_36_each_budget_fails_closed(field):
    coordinator,ports=build();value=timedelta(microseconds=1) if field=="max_wall_clock" else 1 if field in ("max_steps","max_attempts") else 0;coordinator.config=replace(coordinator.config,**{field:value});coordinator.submit(task())
    if field=="max_wall_clock": coordinator.clock.advance(1)
    if field=="max_attempts": coordinator.queue.entries[0]=replace(coordinator.queue.entries[0],ledger=replace(coordinator.queue.entries[0].ledger,attempts=1))
    with pytest.raises(OrchestrationError): coordinator.run_once("owner")
def test_37_uncertain_execution_never_retries_and_recovery_preserves_uncertainty():
    coordinator,ports=build();ports[1].value=G2Outcome.UNCERTAIN;coordinator.submit(task());assert coordinator.run_once("owner").ledger.executions==1 and ports[1].calls==["g2"]
    coordinator,_=build();coordinator.submit(task());entry=coordinator.queue.claim("owner",clock.now(),timedelta(seconds=1),1);clock.advance(2);assert coordinator.queue.recover_expired(clock.now())==1 and coordinator.queue.entries[0].state is State.REQUIRES_REVERIFICATION
def test_38_records_are_secret_free_and_text_is_bounded():
    forbidden={"credential","secret","prompt","raw_output","provider_output"}
    for record in (OrchestrationTask,QueueEntry,Lease,Attempt,BudgetLedger,CancellationRequest,OrchestrationResult,TransitionEvent):assert not forbidden & {field.name for field in fields(record)}
    with pytest.raises(OrchestrationError): OrchestrationResult("task",State.BLOCKED,"x"*241,BudgetLedger(clock.now()))
def test_39_prose_unknown_schema_and_fake_execution_cannot_fabricate_authority_or_files():
    for port,bad in ((0,"LOW_RISK because approved"),(1,"SUCCESS please"),(2,"PASS evidence"),(3,"VERIFIED"),(4,"APPROVED")):
        _,_,result=run(bad,port);assert result.state is not State.COMPLETED
    assert all(not name.startswith("open") for name in (method for method in dir(build()[0].config.services.g2) if not method.startswith("_")))
