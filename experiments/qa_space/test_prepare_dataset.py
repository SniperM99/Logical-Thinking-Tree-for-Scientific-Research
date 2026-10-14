import unittest,tempfile,json
from pathlib import Path
from prepare_dataset import build,load_inputs
class PreparationTests(unittest.TestCase):
 def row(self,id,seq,parent='—',level=0):return {'编号':id,'问题':'研究问题','回答':'完整回答','提问顺序':seq,'父问题编号':parent,'层级':level,'节点类型':'子问题' if parent!='—' else '父问题','来源问题编号':None,'对话动作':'回访'}
 def test_inputs_hide_hierarchy_and_preserve_qa(self):
  inputs,labels=build([self.row('Q1',1),self.row('Q1.1',2,'Q1',1)],[])
  self.assertEqual({'qa_id','sequence','question','answer'},set(inputs[1]));self.assertEqual('qa_0001',labels[1]['parent_qa_id']);self.assertEqual('完整回答',inputs[1]['answer'])
 def test_bad_order_and_parent_are_rejected(self):
  for rows in [[self.row('Q1',2)],[self.row('Q1.1',1,'Q1',1)],[self.row('Q1',1),self.row('Q1.1',2,'Q1',2)]]:
   with self.assertRaises(ValueError):build(rows,[])
 def test_model_loader_rejects_labels(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.jsonl';p.write_text(json.dumps({'qa_id':'q','sequence':1,'question':'Q','answer':'A','parent_qa_id':'p'}))
   with self.assertRaises(ValueError):load_inputs(p)
if __name__=='__main__':unittest.main()
