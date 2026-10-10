import json,os,unittest
from unittest.mock import patch
from fastapi import HTTPException
from main import ResearchTurnRequest,research_turn
class CombinedTurn(unittest.TestCase):
 def request(self):return ResearchTurnRequest(qa_id='q',question='继续讨论它',context={'space_id':'s','node_id':'r'},history=[{'qa_id':'prior','question':'种子为43871','answer':'已记住参数'}])
 def response(self,excerpt='预测表示'):
  return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'answer':'可以研究预测表示。','thoughts':[{'text':'研究预测表示','topic':'表示预测','excerpt':excerpt,'core_concepts':['表示预测']}]})}}],'usage':{'prompt_tokens':100,'completion_tokens':30}}
 def test_one_provider_request_contains_history_and_produces_real_coordinates(self):
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'},clear=True),patch('main.provider_request',return_value=self.response()) as provider:
   result=research_turn(self.request());self.assertEqual(provider.call_count,1);self.assertEqual(result['generation']['answer_extraction_requests'],1);self.assertEqual(result['generation']['usage']['prompt_tokens'],100)
   self.assertEqual(len(result['analysis']['thoughts'][0]['original_coordinate']),512);self.assertEqual(result['answer'],'可以研究预测表示。')
   self.assertEqual([m['role'] for m in provider.call_args.args[1]['messages']],['system','user','assistant','user'])
 def test_bad_excerpt_or_truncated_json_never_triggers_a_second_request(self):
  for response in [self.response('不存在'),{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}]:
   with patch.dict(os.environ,{'XUNXU_MODEL':'test'},clear=True),patch('main.provider_request',return_value=response) as provider:
    with self.assertRaises(HTTPException):research_turn(self.request())
    self.assertEqual(provider.call_count,1)

 def test_forced_function_arguments_return_both_parts_without_tool_execution(self):
  response=self.response();payload=response['choices'][0]['message']['content']
  response['choices'][0]['finish_reason']='tool_calls'
  response['choices'][0]['message']={'tool_calls':[{'function':{'name':'deliver_research_turn','arguments':payload}}]}
  with patch.dict(os.environ,{'XUNXU_MODEL':'test'},clear=True),patch('main.provider_request',return_value=response) as provider:
   result=research_turn(self.request());self.assertEqual(provider.call_count,1)
   self.assertEqual(result['answer'],'可以研究预测表示。')
   self.assertEqual(provider.call_args.args[1]['tool_choice']['function']['name'],'deliver_research_turn')
   self.assertNotIn('response_format',provider.call_args.args[1])
