import dataclasses,json,tempfile,unittest
from pathlib import Path
from rac_ai_scientist.conditions import Condition
from rac_ai_scientist.policy import SharedPolicy
from rac_ai_scientist.schemas import Action,InvocationResult,Issue,Verdict
from rac_ai_scientist.artifacts import snapshot_workspace
from rac_ai_scientist.runner import EpisodeRunner
from rac_ai_scientist.ledger import JsonlLedger
from rac_ai_scientist.hosts.ark import render_contract_prompt
from rac_ai_scientist.sharednet import SharedNetSession,SharedNetInvite,_decode
from rac_ai_scientist.cli import _uses_sharednet,build_parser
from test_policy import checkpoint
from test_runner import FakeBridge
from test_sharednet import FakeRoomClient

class AblationTests(unittest.TestCase):
 def test_feature_matrix_preserves_original_conditions(self):
  expected={'N0':(0,0,0,0),'R1':(1,0,0,0),'R2':(1,1,0,0),'R3':(1,1,1,1),'R2+C':(1,1,1,0),'R2+V':(1,1,0,1)}
  for name,flags in expected.items():
   with self.subTest(name=name):self.assertEqual(tuple(Condition.parse(name).features().values()),flags)
  self.assertEqual(Condition.parse('R2_C'),Condition.parse('R2+C'))
  self.assertEqual(Condition.parse('R2_V'),Condition.parse('R2+V'))

 def test_routing_identical_and_criteria_frozen_before_execution(self):
  cp=checkpoint([Issue('scope','experiment','missing baseline')]);ds={s:SharedPolicy(s).decide(cp) for s in ('R2','R2+C','R2+V','R3')}
  self.assertEqual(len({d.capability_id for d in ds.values()}),1)
  self.assertIsNone(ds['R2'].contract);self.assertIsNone(ds['R2+V'].contract)
  self.assertIsNone(ds['R2+C'].verification_spec)
  self.assertEqual(ds['R2+C'].contract,ds['R3'].contract)
  self.assertEqual(ds['R2+V'].verification_spec,ds['R3'].contract)
  before=ds['R2+V'].verification_spec
  cp.issues.clear()
  self.assertEqual(before.issue_ids,('scope',))

 def test_verifier_only_matches_r3_and_is_advisory(self):
  cp=checkpoint()
  for error in (None,'nonfatal execution error'):
   outcomes=[]
   for name in ('R2+V','R3'):
    policy=SharedPolicy(name);d=policy.decide(cp)
    r=InvocationResult(d.capability_id,'',(),(),error=error)
    e=policy.evaluate(cp,d,r);outcomes.append(e)
    self.assertEqual(e.action,Action.REVERIFY)
    self.assertEqual(e.verification.verdict,Verdict.REFUTED)
   self.assertEqual(outcomes[0].verification,outcomes[1].verification)

 def test_contract_only_has_r2_error_and_completion_semantics(self):
  cp=checkpoint()
  for fields in ({'proposed_done':True},{'error':'failed'},{'timed_out':True,'metrics':{'native_timeout_continuable':1.0}}):
   outcomes=[]
   for name in ('R2','R2+C'):
    p=SharedPolicy(name);d=p.decide(cp);e=p.evaluate(cp,d,InvocationResult(d.capability_id,'',(),(),**fields));outcomes.append(e)
    self.assertIsNone(e.verification)
   self.assertEqual(outcomes[0].action,outcomes[1].action)

 def test_terminal_provider_error_still_stops_both_ablations(self):
  for name in ('R2+C','R2+V'):
   p=SharedPolicy(name);cp=checkpoint();d=p.decide(cp)
   e=p.evaluate(cp,d,InvocationResult(d.capability_id,'',(),(),error='Error code: 402'))
   self.assertEqual(e.action,Action.STOP);self.assertIsNone(e.verification)

 def test_runner_contract_visibility_and_typed_advisories(self):
  for name,has_contract,has_verifier in [('R2',False,False),('R2+C',True,False),('R2+V',False,True),('R3',True,True)]:
   with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
    FakeRoomClient.reset()
    class Probe(FakeBridge):
     hop=0
     def invoke(self,capability_id,contract):
      self.seen_contract=contract
      self.prompt=self.communication_prompt(capability_id,render_contract_prompt('finish report',capability_id,contract),contract)
      result=super().invoke(capability_id,contract);self.hop+=1;return result
    bridge=Probe();bridge.sharednet=SharedNetSession(SharedNetInvite.parse('ROOM=rom_test TOKEN=rit_'+'a'*43,room_id='rom_test'),'ep',['write'],client_factory=FakeRoomClient)
    bridge.sharednet.join()
    path=Path(tmp)/'ledger.jsonl';outcome=EpisodeRunner(bridge,name,JsonlLedger(path)).run(hard_hop_limit=3)
    self.assertEqual(outcome.status,'stop');self.assertEqual(bridge.seen_contract is not None,has_contract)
    events=[_decode(m.content)[1] for m in FakeRoomClient.messages_log];events=[e for e in events if e]
    self.assertEqual(any(e['type']=='work.verification' for e in events),has_verifier)
    request=next(e for e in events if e['type']=='work.request')
    self.assertEqual('contract_id' in request,has_contract)
    if not has_contract:self.assertNotIn('current work contract',bridge.prompt)
    ledger=[json.loads(s) for s in path.read_text().splitlines()]
    decision=next(e['payload'] for e in ledger if e['type']=='decision' and e['payload'].get('capability_id'))
    if name=='R2+V':self.assertIsNone(decision['contract']);self.assertIsNotNone(decision['verification_spec'])
    if has_verifier:
     feedback=bridge.sharednet.request('write',2,'next',None)
     self.assertIn('verification advisory',feedback)

 def test_cli_and_sharednet_recognize_ablation_names(self):
  action=next(a for a in build_parser()._subparsers._group_actions[0].choices['run-one']._actions if a.dest=='condition')
  for name in ('R2+C','R2+V'):
   self.assertIn(name,action.choices)
   for host in ('agent_laboratory','evo_scientist'):self.assertTrue(_uses_sharednet(host,name))

 def test_nonfatal_error_retains_artifacts_only_with_verifier(self):
  for name,retained in [('R2',False),('R2+C',False),('R2+V',True),('R3',True)]:
   with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
    workspace=Path(tmp)/'work';workspace.mkdir()
    class ErrorBridge(FakeBridge):
     def transaction_workspace(self):return workspace
     def invoke(self,capability_id,contract):
      before=snapshot_workspace(workspace)
      (workspace/'partial.txt').write_text('partial work')
      self.done=True;self.invocations+=1
      return InvocationResult(capability_id,'partial',before,snapshot_workspace(workspace),error='nonfatal')
    outcome=EpisodeRunner(ErrorBridge(),name,JsonlLedger(Path(tmp)/'ledger')).run(hard_hop_limit=3)
    self.assertEqual((workspace/'partial.txt').exists(),retained)
    self.assertEqual(outcome.status,'stop' if retained else 'failed')
