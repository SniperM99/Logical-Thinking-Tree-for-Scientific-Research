"""Download immutable ONNX conversion revision, record SHA256 provenance."""
import hashlib,json,urllib.request
from pathlib import Path
REV='75c43b069aac4d136ba6bc1122f995fedcfd2781'
root=Path(__file__).resolve().parents[1]/'.runtime/models/bge-small-zh-v1.5'
root.mkdir(parents=True,exist_ok=True);files={}
for name in ['config.json','tokenizer.json','tokenizer_config.json','onnx/model_quantized.onnx']:
    dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
    url=f'https://huggingface.co/Xenova/bge-small-zh-v1.5/resolve/{REV}/{name}'
    if not dest.exists():
        temp=dest.with_suffix('.download')
        with urllib.request.urlopen(url,timeout=120) as response,temp.open('wb') as out:
            while chunk:=response.read(1024*1024):out.write(chunk)
        temp.replace(dest)
    files[name]={'source':url,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size}
    print(name,dest.stat().st_size)
(root/'manifest.json').write_text(json.dumps({'source_model':'BAAI/bge-small-zh-v1.5','conversion_model':'Xenova/bge-small-zh-v1.5','revision':REV,'dimension':512,'pooling':'CLS','normalization':'L2','quantization':'ONNX dynamic quantized','files':files},indent=2))
