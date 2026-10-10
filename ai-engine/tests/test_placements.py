import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import GrowthPlacementsRequest,growth_placements
class PlacementTests(unittest.TestCase):
 def request(self):
  return GrowthPlacementsRequest(requests=[{'id':'placement-original','child':{'title':'JEPA'},'candidates':[{'node_id':'world-node','title':'世界模型','similarity':0.61,'evidence':[{'turn_index':1,'question':'世界模型研究方向'}]}],'sequence':[{'turn_index':1},{'turn_index':3}]}])
 def result(self,parent='0',decision='deepen'):
  return {'choices':[{'message':{'content':json.dumps({'decisions':[{'id':'0','decision':decision,'parent_id':parent,'branch_start_turn':3,'parent_evidence_turns':[1],'reason':'第1轮建立范围，第3轮深入方法，语义候选支持'}]})}}]}
 def test_one_request_maps_candidate_back_without_performing_write(self):
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.result()) as provider:
   result=growth_placements(self.request());self.assertEqual('world-node',result['decisions'][0]['parent_id']);self.assertEqual('placement-original',result['decisions'][0]['id']);self.assertFalse(result['writes_performed']);self.assertEqual(1,provider.call_count)
 def test_unadmitted_parent_and_switch_parent_are_rejected(self):
  future=self.result();future['choices'][0]['message']['content']=json.dumps({'decisions':[{'id':'0','decision':'deepen','parent_id':'0','branch_start_turn':1,'parent_evidence_turns':[1],'reason':'不能用同轮作为祖先'}]})
  for result in [self.result('invented'),self.result('0','switch'),future]:
   with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=result):
    with self.assertRaises(HTTPException):growth_placements(self.request())

 def test_forced_tool_contract_has_all_temporal_fields(self):
  content=self.result()['choices'][0]['message']['content']
  payload={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'deliver_growth_placements','arguments':content}}]}}]}
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=payload) as provider:
   result=growth_placements(self.request());self.assertEqual(3,result['decisions'][0]['branch_start_turn']);self.assertEqual([1],result['decisions'][0]['parent_evidence_turns']);self.assertEqual(1,provider.call_count);self.assertEqual('deliver_growth_placements',provider.call_args.args[1]['tool_choice']['function']['name'])
