import json,os,unittest
from unittest.mock import patch
from fastapi import HTTPException
from main import OwnershipRequest,qa_ownership
class OwnershipTests(unittest.TestCase):
 def request(self):
  return OwnershipRequest(qa_id='q',question='JEPA如何避免坍缩',thought={'text':'JEPA机制'},current_node_id='jepa',candidates=[{'node_id':'jepa','title':'JEPA','is_current':True}],history=[])
 def response(self,**kwargs):
  row={'decision':'accumulate','node_id':'0','title':'','research_goal':'','distinction':'','reason':'解释已有研究对象的机制，继续积累','branch_relation':'child','reference_node_id':'0'};row.update(kwargs)
  return {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'deliver_qa_ownership','arguments':json.dumps(row)}}]}}]}
 def test_accumulation_maps_only_admitted_node_with_one_call(self):
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response()) as model:
   r=qa_ownership(self.request());self.assertEqual('jepa',r['node_id']);self.assertEqual('accumulate',r['decision']);self.assertEqual(1,model.call_count)
 def test_independent_branch_requires_goal_and_distinction(self):
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response(decision='branch',title='验证实验',research_goal='验证防坍缩假设',distinction='独立对照实验')):
   self.assertEqual('branch',qa_ownership(self.request())['decision'])
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response(decision='branch',title='新知识点')):
   with self.assertRaises(HTTPException):qa_ownership(self.request())
 def test_foreign_id_and_truncation_are_rejected_without_hidden_retry(self):
  for response in [self.response(node_id='foreign'),{'choices':[{'finish_reason':'length'}]}]:
   with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=response) as model:
    with self.assertRaises(HTTPException):qa_ownership(self.request())
    self.assertEqual(1,model.call_count)
 def test_uncertain_stays_on_current_without_creating_a_branch(self):
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response(decision='uncertain',node_id='foreign')):
   r=qa_ownership(self.request());self.assertEqual('jepa',r['node_id']);self.assertEqual('',r['title'])

 def test_sibling_uses_shared_parent_even_if_model_selects_previous_node(self):
  request=OwnershipRequest(qa_id='q',question='隐空间也深度调研',thought={},current_node_id='pixel',candidates=[{'node_id':'pixel','parent_id':'taxonomy'},{'node_id':'taxonomy','parent_id':'root'},{'node_id':'root'}])
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response(decision='branch',node_id='0',title='隐空间研究',research_goal='隐空间技术谱系',distinction='与观测空间并列',branch_relation='sibling',reference_node_id='0')):
   result=qa_ownership(request);self.assertEqual('taxonomy',result['node_id']);self.assertEqual('pixel',result['reference_node_id'])
 def test_child_cannot_use_a_different_parent(self):
  request=OwnershipRequest(qa_id='q',question='验证实验',thought={},current_node_id='pixel',candidates=[{'node_id':'pixel','parent_id':'taxonomy'},{'node_id':'taxonomy'}])
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'}),patch('main.provider_request',return_value=self.response(decision='branch',node_id='1',title='实验',research_goal='验证',distinction='实验',branch_relation='child',reference_node_id='0')):
   with self.assertRaises(HTTPException):qa_ownership(request)
