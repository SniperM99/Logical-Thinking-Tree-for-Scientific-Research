import unittest
from improve_retrieval import coverage,fusion,bm25
class RecallTests(unittest.TestCase):
 def test_fusion_and_coverage_do_not_invent_candidates(self):
  a=[[],[0],[0,1],[0,1,2]];b=[[],[0],[1,0],[2,1,0]]
  for method in [fusion,coverage]:
   for i,rank in enumerate(method([a,b])):self.assertEqual(set(range(i)),set(rank));self.assertEqual(i,len(rank))
  self.assertEqual([0,2,1],coverage([a,b])[3])
 def test_bm25_excludes_current_and_future_documents(self):
  result=bm25(['摩擦接触','摩擦定位','规划搜索'],['接触','摩擦','规划'])
  self.assertEqual([],result[0]);self.assertEqual([0],result[1]);self.assertEqual({0,1},set(result[2]))
if __name__=='__main__':unittest.main()
