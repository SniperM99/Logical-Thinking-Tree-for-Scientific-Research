import unittest
from resource_pool import build_pool
class PoolTests(unittest.TestCase):
 def test_suggested_node_instead_of_previous_qa(self):
  rows=[{'qa_id':k,'sequence':i,'question':k,'answer':'answer'} for i,k in enumerate(['a','b','c','d'])]
  pending=[{'qa_id':'c','reason':'unknown','proposal':{'parent_id':'a'}},{'qa_id':'d','reason':'unknown','proposal':{'parent_id':'c'}}]
  nodes=rows[:2];p=build_pool(rows,pending,nodes,{k:k for k in ['a','b','c','d']},{k:k for k in ['a','b','c','d']})
  self.assertEqual(p['node_pools'],{'a':['c']});self.assertEqual(p['stream_pool'],['d'])
  self.assertEqual(p['records'][0]['previous_qa_id'],'b')
  self.assertEqual(p['records'][1]['suggested_node_id'],'c');self.assertIsNone(p['records'][1]['storage_anchor']);self.assertNotIn('parent',p['records'][1])
 def test_missing_suggestion_never_falls_back_to_previous(self):
  rows=[{'qa_id':k,'question':k,'answer':'a'} for k in ['a','b']]
  p=build_pool(rows,[{'qa_id':'b'}],[rows[0]],{'a':'a','b':'b'},{'a':'a','b':'b'})
  self.assertEqual(p['node_pools'],{});self.assertEqual(p['stream_pool'],['b'])
if __name__=='__main__':unittest.main()
