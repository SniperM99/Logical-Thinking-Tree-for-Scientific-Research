import unittest
import numpy as np
from incremental_growth import new_state,commit,OnlineIndex
class IncrementalTests(unittest.TestCase):
 def test_append_keeps_old_positions_edges_and_retry_assignment(self):
  s=new_state('主题','范围');d={'kind':'deepening','parent_id':'research-root','reason':'子问题','current_quote':'当前问','parent_quote':'主题'}
  a={'qa_id':'a','sequence':1,'question':'当前问','answer':'答'};commit(s,a,'核心',d,True)
  original=[(n['qa_id'],n['parent'],dict(n['position'])) for n in s['nodes']]
  commit(s,{'qa_id':'b','sequence':2,'question':'另一问','answer':'答'},'核心',d,True)
  self.assertEqual(original,[(n['qa_id'],n['parent'],n['position']) for n in s['nodes'][:2]])
  self.assertNotEqual(s['nodes'][1]['position'],s['nodes'][2]['position'])
  revision=s['revision'];commit(s,a,'核心',d,True);self.assertEqual(s['revision'],revision)
  commit(s,{'qa_id':'c','sequence':3,'question':'补充','answer':'答'},'核心',{**d,'kind':'same_problem','parent_id':'a'},True)
  self.assertEqual(len(s['nodes']),3);self.assertEqual(s['assignments']['c'],'a');self.assertEqual(s['resources'][0]['storage_anchor'],'a')
 def test_pending_does_not_create_node(self):
  s=new_state('主题','范围');commit(s,{'qa_id':'a','sequence':1,'question':'问','answer':'答'},'核心',{'kind':'uncertain','parent_id':'research-root','reason':'不确定'},True)
  self.assertEqual(len(s['nodes']),1);self.assertEqual(s['pending'][0]['storage_anchor'],'research-root')
 def test_online_index_only_contains_inserted_items(self):
  idx=OnlineIndex();v=np.array([1.,0.]);idx.add('a','机器人定位',v)
  self.assertEqual(idx.search('机器人',v,10),['a']);idx.add('b','植物生长',np.array([0.,1.]));self.assertEqual(len(idx.docs),2);self.assertEqual(idx.search('机器人',v,1),['a'])
if __name__=='__main__':unittest.main()
