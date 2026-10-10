import unittest,math
from unittest.mock import patch
from fastapi import HTTPException
from embeddings import local_embedding
from main import coordinates,project,ProjectRequest,IntentMatches,IntentPair,IntentDescription,ScopedContext,intent_matches
class SemanticMeasurement(unittest.TestCase):
 def test_real_local_space_has_normalized_finite_vectors_and_semantic_order(self):
  texts=['JEPA在表征空间进行预测，避免像素级重建。','联合嵌入预测架构通过预测潜在表示学习世界结构。','烘焙面包需要控制发酵时间和烤箱温度。']
  vectors=local_embedding.encode(texts)
  for v in vectors:
   self.assertEqual(len(v),512);self.assertTrue(all(math.isfinite(x) for x in v));self.assertAlmostEqual(sum(x*x for x in v),1,places=5)
  related=sum(a*b for a,b in zip(vectors[0],vectors[1]));unrelated=sum(a*b for a,b in zip(vectors[0],vectors[2]));self.assertGreater(related,unrelated+0.1)
 def test_pca_is_finite_deterministic_and_not_original_coordinate(self):
  req=ProjectRequest(vectors=[[1,0,0],[0,1,0],[0,0,1]])
  result=project(req);self.assertEqual(result,project(req));self.assertEqual(result['dimension'],3);self.assertEqual(len(result['points']),3);self.assertEqual(len(result['explained_variance']),2)
  self.assertEqual(project(ProjectRequest(vectors=[[1,0]]))['points'],[{'x':0.,'y':0.}])
  with self.assertRaises(HTTPException):project(ProjectRequest(vectors=[[1,0],[1]]))
 def test_no_model_never_claims_same_intent(self):
  with patch.dict('os.environ',{},clear=True):
   req=IntentMatches(pairs=[IntentPair(id='a',left=IntentDescription(topic='JEPA机制'),right=IntentDescription(topic='JEPA应用'))],context=ScopedContext(space_id='s',node_id='r'))
   self.assertEqual(intent_matches(req)['decisions'][0]['decision'],'not_evaluated')
if __name__=='__main__':unittest.main()
