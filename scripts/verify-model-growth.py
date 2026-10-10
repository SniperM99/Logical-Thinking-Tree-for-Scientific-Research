import json,urllib.request,uuid
from pathlib import Path
base='http://127.0.0.1:8080'
def call(path,data):
 req=urllib.request.Request(base+path,data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=150) as response:return json.load(response)
space=call('/api/spaces',{'title':'DeepSeek 自动生长测试','goal':'验证学习率对小型神经网络训练稳定性的影响；这是 API 接入验收，不是已执行的科研结论。'})
conv=call('/api/conversations',{'node_id':space['root_id'],'title':'DeepSeek 自动问答与思想聚类验收'})
qas=[]
for i in range(2):
 result=call('/api/qa',{'conversation_id':conv['id'],'question':'如何通过控制变量实验验证学习率对小型神经网络训练稳定性的影响？请用150字以内说明同一个实验设计，保留为未验证假设。','request_id':uuid.uuid4().hex})
 qas.append({'qa_id':result['qa']['id'],'mode':result['qa']['mode'],'answer_length':len(result['qa']['answer']),'created_nodes':[{'id':n['id'],'title':n['title']} for n in result['created_nodes']]})
 print(json.dumps(qas[-1],ensure_ascii=False),flush=True)
report={'provider':'DeepSeek','model':'deepseek-flash','space_id':space['id'],'conversation_id':conv['id'],'qas':qas,'automatic_growth_verified':bool(qas[1]['created_nodes'])}
Path('docs/deepseek-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert report['automatic_growth_verified'],'第二个问答未形成同意图簇，请检查归属；不能强制创建节点冒充自动生长。'
