import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import standalone_lab as lab
class LabTests(unittest.TestCase):
 def test_persistence_idempotency_and_growth_only_retry(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'FILE',Path(tmp)/'state.json'),patch.object(lab.local_embedding,'encode',return_value=[[1.,0.]]):
   lab.create({'theme':'机器人研究','scope':'机器人实验'});c=lab.conversation({})
   answer={'answer':'可以测量定位误差。','core':'机器人定位误差实验'}
   d={'kind':'deepening','parent_id':'research-root','sibling_id':'','reason':'子任务','current_goal':'定位测量','parent_goal':'机器人研究','containment_explanation':'定位是机器人研究的一部分','alternative_explanation':'不是解释同题','current_quote':'机器人定位','parent_quote':'机器人研究','closer_parent_found':False,'root_check_reason':'检索空间为空，没有更直接的已有节点'}
   request={'question':'机器人定位怎么研究？','conversation_id':c['id'],'request_id':'test'}
   with patch.object(lab,'model',side_effect=[answer,RuntimeError('failure')]) as model:
    q=lab.turn(request);self.assertEqual(q['status'],'growth_failed');self.assertEqual(len(lab.workspace(lab.load())['qas']),1)
   with patch.object(lab,'model',return_value=d) as model:
    q=lab.retry({'qa_id':q['qa_id']});self.assertEqual(q['status'],'node');self.assertEqual(model.call_count,2)
    lab.turn(request);self.assertEqual(model.call_count,2)
   w=lab.workspace(lab.load());self.assertEqual(len(w['qas']),1);self.assertEqual(len(w['graph']['nodes']),2);self.assertEqual(len(w['graph']['pending']),0)
 def test_even_non_root_deepening_must_retrieve_and_compare(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'FILE',Path(tmp)/'state.json'),patch.object(lab.local_embedding,'encode',return_value=[[1.,0.]]):
   lab.create({'theme':'机器人研究','scope':'机器人实验'});db=lab.load();w=lab.workspace(db)
   old={'qa_id':'world','sequence':1,'question':'世界模型如何用于机器人研究？','answer':'预测与决策','core':'世界模型机制','id':'world','conversation_id':'old','request_id':'old','status':'node'}
   lab.commit(w['graph'],old,old['core'],{'kind':'deepening','parent_id':'research-root','reason':'方向','current_quote':'世界模型','parent_quote':'机器人研究'},True);w['qas'].append(old);w['vectors']['world']=[1.,0.];lab.save(db);c=lab.conversation({})
   local={'kind':'deepening','parent_id':'world','sibling_id':'','reason':'局部未找到','current_goal':'设备适用性','parent_goal':'机器人研究','containment_explanation':'主题相关','alternative_explanation':'不是局部补充','current_quote':'世界模型','parent_quote':'世界模型'}
   final={**local,'kind':'deepening','parent_id':'world','parent_quote':'世界模型','closer_parent_found':True,'root_check_reason':'已有世界模型节点更直接'}
   before=dict(w['graph']['nodes'][1]['position'])
   with patch.object(lab,'model',side_effect=[{'answer':'移动设备','core':'世界模型设备适用性'},local,final]) as model:
    q=lab.turn({'question':'世界模型适用于哪些设备？','conversation_id':c['id'],'request_id':'new'})
    self.assertEqual(model.call_count,3);self.assertEqual(model.call_args_list[-1].args[3]['stage'],'global');self.assertEqual(model.call_args_list[-1].args[3]['local_proposal']['kind'],'deepening')
   w=lab.workspace(lab.load());self.assertEqual(q['decision']['parent_id'],'world');self.assertTrue(q['growth_trace']['space_retrieval']);self.assertIn('world',q['growth_trace']['retrieved_qa_ids']);self.assertEqual(w['graph']['nodes'][1]['position'],before)
if __name__=='__main__':unittest.main()
