import unittest
from relation_v2 import validate_relation
class RelationEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.current={'question':'如何评价装配成功率？','core':'定位误差与装配成功率'}
  self.catalog={'parent':{'question':'移动操作的关键技术问题','core':'研究定位误差与操作表现'},'sibling':{'question':'如何测量定位误差？','core':'定位误差的独立测量'}}
  self.decision={'parent_id':'parent','kind':'sibling_return','sibling_id':'sibling','current_quote':'装配成功率','parent_quote':'关键技术问题','current_goal':'成功率评价','parent_goal':'技术瓶颈研究','containment_explanation':'对上位问题的任务表现维度进行研究','alternative_explanation':'误差测量与成功率评价是不同目标'}
 def test_sibling_requires_distinct_historical_comparator(self):
  self.assertTrue(validate_relation(self.decision,self.catalog,self.current))
  for sibling in ['parent','missing','']:
   self.assertFalse(validate_relation({**self.decision,'sibling_id':sibling},self.catalog,self.current))
 def test_nonexistent_parent_and_fabricated_quote_rejected(self):
  self.assertFalse(validate_relation({**self.decision,'parent_id':'future'},self.catalog,self.current))
  self.assertFalse(validate_relation({**self.decision,'parent_quote':'不存在的证据'},self.catalog,self.current))
 def test_containment_and_alternative_required(self):
  for field in ['containment_explanation','alternative_explanation']:
   self.assertFalse(validate_relation({**self.decision,field:''},self.catalog,self.current))
if __name__=='__main__':unittest.main()
