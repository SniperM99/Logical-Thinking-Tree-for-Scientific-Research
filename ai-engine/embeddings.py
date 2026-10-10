"""Real Chinese sentence embeddings; no lexical fallback masquerading as semantics."""
import json
import hashlib
import os
from pathlib import Path
from threading import RLock
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT=Path(__file__).resolve().parents[1]/'.runtime/models/bge-small-zh-v1.5'
METHOD='local:BAAI/bge-small-zh-v1.5:onnx-int8:75c43b0:cls:l2'
class LocalEmbedding:
    def __init__(self):self.session=None;self.lock=RLock();self.error=None
    def load(self):
        with self.lock:
            if self.session is not None:return
            root=Path(os.environ.get('XUNXU_LOCAL_EMBEDDING_DIR',str(ROOT)))
            self.manifest=json.loads((root/'manifest.json').read_text())
            if self.manifest['revision']!='75c43b069aac4d136ba6bc1122f995fedcfd2781':raise ValueError('unexpected embedding revision')
            for name,meta in self.manifest['files'].items():
                if hashlib.sha256((root/name).read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('embedding asset checksum mismatch')
            self.tokenizer=Tokenizer.from_file(str(root/'tokenizer.json'))
            self.tokenizer.enable_truncation(max_length=512)
            self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            self.session=ort.InferenceSession(str(root/'onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    def health(self):
        try:self.load();return {'ready':True,'method':METHOD,'model':'BAAI/bge-small-zh-v1.5','dimension':512,'semantic_embedding':True,'revision':self.manifest['revision'],'normalization':'L2','pooling':'CLS'}
        except Exception as exc:return {'ready':False,'method':METHOD,'dimension':512,'semantic_embedding':True,'error':type(exc).__name__,'install':'python3 ai-engine/install-model.py'}
    def encode(self,texts):
        self.load();vectors=[]
        # Bound peak attention memory; tokenizer padding config is mutable, serialize batches.
        with self.lock:
            for start in range(0,len(texts),8):
                encoded=self.tokenizer.encode_batch(texts[start:start+8])
                inputs={'input_ids':np.array([e.ids for e in encoded],dtype=np.int64),'attention_mask':np.array([e.attention_mask for e in encoded],dtype=np.int64),'token_type_ids':np.array([e.type_ids for e in encoded],dtype=np.int64)}
                outputs=self.session.run(None,{i.name:inputs[i.name] for i in self.session.get_inputs()})
                hidden=outputs[0];pooled=hidden[:,0,:] if hidden.ndim==3 else hidden
                norms=np.linalg.norm(pooled,axis=1,keepdims=True)
                if pooled.shape[1]!=512 or not np.isfinite(pooled).all() or np.any(norms==0):raise ValueError('invalid model embeddings')
                vectors.extend((pooled/norms).astype(float).tolist())
        return vectors
local_embedding=LocalEmbedding()
