from dataclasses import replace
from datetime import datetime, timedelta, timezone

from zero_core.engineering_orchestration import *

class FakeClock:
    def __init__(self): self.value = datetime(2025, 1, 1, tzinfo=timezone.utc)
    def now(self): return self.value
    def advance(self, seconds): self.value += timedelta(seconds=seconds)
class FakeIds:
    def __init__(self): self.count = 0
    def next_id(self): self.count += 1; return f"id-{self.count}"
class FakeCancellation:
    def __init__(self): self.value = None
    def requested(self, task_id): return self.value
class FakeQueue:
    def __init__(self): self.entries=[]; self.events=[]
    def find_idempotency(self,key): return next((item for item in self.entries if item.task.idempotency_key == key),None)
    def enqueue(self,task,ledger,maximum):
        if len(self.entries)>=maximum or any(item.task.task_id==task.task_id for item in self.entries): raise OrchestrationError("QUEUE_REJECTED")
        item=QueueEntry(task,State.QUEUED,len(self.entries)+1,ledger); self.entries.append(item); return item
    def claim(self,owner,now,duration,maximum):
        if sum(item.lease is not None and item.lease.expires_at>now for item in self.entries)>=maximum:return None
        for index,item in enumerate(self.entries):
            if item.state is State.QUEUED:
                lease=Lease(item.task.task_id,f"lease-{item.sequence}",owner,now+duration)
                self.entries[index]=replace(item,state=State.LEASED,lease=lease); return self.entries[index]
        return None
    def compare_and_swap(self,entry,lease,state,ledger,reason):
        current=self.entries[entry.sequence-1]
        if current != entry or current.lease != lease or lease.expires_at <= clock.now(): raise OrchestrationError("CAS_REJECTED")
        if state not in TRANSITIONS.get(current.state,frozenset()):raise OrchestrationError("ILLEGAL_TRANSITION")
        saved=replace(current,state=state,ledger=ledger); self.entries[entry.sequence-1]=saved; self.events.append((state,reason)); return saved
    def recover_expired(self,now):
        count=0
        for index,item in enumerate(self.entries):
            if item.state is State.LEASED and item.lease.expires_at<=now:self.entries[index]=replace(item,state=State.REQUIRES_REVERIFICATION,lease=None);count+=1
        return count
    def renew(self,entry,lease,now,duration,maximum):
        current=self.entries[entry.sequence-1]
        if current != entry or current.lease != lease or lease.expires_at<=now or lease.renewals>=maximum: raise OrchestrationError("RENEW_REJECTED")
        renewed=replace(lease,expires_at=now+duration,renewals=lease.renewals+1)
        self.entries[entry.sequence-1]=replace(current,lease=renewed); return renewed
clock=FakeClock()
class Port:
    def __init__(self, value): self.value=value;self.calls=[]
    def validate(self,*a):self.calls.append("g1");return self.value
    def execute(self,*a):self.calls.append("g2");return self.value
    def verify(self,*a):self.calls.append("g3");return self.value
    def checkpoint(self,*a):self.calls.append("g4");return self.value
    def review(self,*a):self.calls.append("g5");return self.value
def build():
    global clock;clock=FakeClock(); ports=[Port(G1Outcome.LOW_RISK),Port(G2Outcome.SUCCESS),Port(G3Outcome.PASS),Port(G4Outcome.VERIFIED),Port(G5Outcome.APPROVED)]
    config=TrustedConfiguration("project","F:\\repo",2,1,timedelta(seconds=30),2,20,timedelta(minutes=2),2,2,2,(timedelta(seconds=1),),frozenset({"EDIT"}),"STICKY",ServiceBindings(*ports))
    return Coordinator(config,FakeQueue(),clock,FakeIds(),FakeCancellation()),ports
def task(key="key",digest="digest",task_id="task"): return OrchestrationTask(task_id,key,"project","F:\\repo","EDIT",object(),object(),object(),digest)
