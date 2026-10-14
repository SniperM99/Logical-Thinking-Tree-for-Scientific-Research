import unittest
from contextual_bm25 import validate_context
class ContextTests(unittest.TestCase):
 def test_grounded_current_and_previous_quotes(self):
  record={'qa_id':'q2','question':'如何降低预测误差','answer':'需检验任务收益'};history=[{'qa_id':'q1','question':'机器人世界模型','core':'预测动作后果'}]
  item={'context':'机器人世界模型的任务相关预测误差评价','citations':[{'qa_id':'q1','field':'question','quote':'机器人世界模型'}]}
  self.assertTrue(validate_context(item,record,history))
 def test_future_citation_and_made_up_quote_rejected(self):
  r={'qa_id':'q1','question':'研究模型','answer':'模型存在误差'}
  for cite in [{'qa_id':'future','field':'question','quote':'机器人模型'},{'qa_id':'q1','field':'answer','quote':'模型没有误差'}]:
   self.assertFalse(validate_context({'context':'模型研究','citations':[cite]},r,[]))
if __name__=='__main__':unittest.main()
