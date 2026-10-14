import unittest
from question_baseline import rankings,metrics,encode_text
class BaselineTests(unittest.TestCase):
 def test_only_previous_candidates_and_stable_ties(self):
  r,_=rankings([[1,0],[1,0],[1,0]])
  self.assertEqual([[],[0],[0,1]],r)
 def test_question_and_qa_inputs_exclude_metadata(self):
  row={'question':'原问题','answer':'原回答','parent_qa_id':'秘密标签'}
  self.assertEqual('原问题',encode_text(row,'question'));self.assertEqual('问题：原问题\n回答：原回答',encode_text(row,'full_qa'))
 def test_metrics_use_exact_denominators(self):
  m=metrics([1,2,6,11]);self.assertEqual(1,m['top1_hits']);self.assertEqual(2,m['recall5_hits']);self.assertEqual(.75,m['recall10']);self.assertAlmostEqual((1+.5+1/6+1/11)/4,m['mrr'])
if __name__=='__main__':unittest.main()
