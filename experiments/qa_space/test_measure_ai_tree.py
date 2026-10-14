import unittest
from measure_ai_tree import evaluate
class TreeEvaluationTests(unittest.TestCase):
 def test_root_is_not_in_parent_metric(self):
  m,d=evaluate([{'qa_id':'a'},{'qa_id':'b'}],[[],[0]],{'a':'root','b':'a'})
  self.assertEqual(1,m['cases']);self.assertEqual(1,m['top1_hits'])
 def test_future_parent_and_bad_candidate_inventory_rejected(self):
  with self.assertRaises(ValueError):evaluate([{'qa_id':'a'},{'qa_id':'b'}],[[],[0]],{'a':'b','b':'root'})
  with self.assertRaises(ValueError):evaluate([{'qa_id':'a'},{'qa_id':'b'}],[[],[1]],{'a':'root','b':'a'})
if __name__=='__main__':unittest.main()
