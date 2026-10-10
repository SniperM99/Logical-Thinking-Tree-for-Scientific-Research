import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import IntentMatches,IntentPair,IntentDescription,ScopedContext,intent_matches
class DirectionTests(unittest.TestCase):
 def request(self,role):
  return IntentMatches(pairs=[IntentPair(id='original',left=IntentDescription(role=role,question='讨论世界模型研究方向'),right=IntentDescription(role='main',question='哲学世界模型有哪些'))],context=ScopedContext(space_id="space",node_id="root"))
 def test_distinct_questions_can_share_direction_without_becoming_same_intent(self):
  payload={'choices':[{'message':{'content':json.dumps({'decisions':[{'id':'0','decision':'related','reason':'具体问题不同','direction_title':'世界模型','direction_reason':'原始问题同一研究对象'}]})}}]}
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=payload) as provider:
   result=intent_matches(self.request('main'))['decisions'][0]
   self.assertEqual('related',result['decision']);self.assertEqual('世界模型',result['direction_title']);self.assertEqual('original',result['id']);self.assertEqual(1,provider.call_count)
 def test_auxiliary_mentions_cannot_supply_direction_evidence(self):
  payload={'choices':[{'message':{'content':json.dumps({'decisions':[{'id':'0','decision':'related','reason':'提及同词','direction_title':'世界模型','direction_reason':'错误建议'}]})}}]}
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=payload):
   self.assertEqual('',intent_matches(self.request('auxiliary'))['decisions'][0]['direction_title'])

 def test_forced_function_contract_and_truncated_result(self):
  content=json.dumps({'decisions':[{'id':'0','decision':'related','reason':'不同具体问题','direction_title':'世界模型','direction_reason':'共同对象'}]})
  payload={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'deliver_intent_matches','arguments':content}}]}}]}
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=payload) as provider:
   self.assertEqual('世界模型',intent_matches(self.request('main'))['decisions'][0]['direction_title']);self.assertEqual(1,provider.call_count);self.assertEqual('deliver_intent_matches',provider.call_args.args[1]['tool_choice']['function']['name'])
  payload['choices'][0]['finish_reason']='length'
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=payload):
   from fastapi import HTTPException
   with self.assertRaises(HTTPException):intent_matches(self.request('main'))
