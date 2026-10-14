import unittest,hashlib
from describe_dataset import validate_descriptors
class DescriptorTests(unittest.TestCase):
 def source(self):return {'qa_id':'qa_0001','question':'问题','answer':'回答'}
 def record(self):return {'qa_id':'qa_0001','core':'研究对象与限制。'*10,'character_count':80,'source_sha256':hashlib.sha256('问题\n回答'.encode()).hexdigest()}
 def test_identity_length_and_source(self):self.assertTrue(validate_descriptors([self.source()],[self.record()]))
 def test_changed_source_and_length_rejected(self):
  for key,value in [('qa_id','wrong'),('core','过短'),('source_sha256','wrong')]:
   r=self.record();r[key]=value
   with self.assertRaises(ValueError):validate_descriptors([self.source()],[r])
if __name__=='__main__':unittest.main()
