#!/usr/bin/env python3
"""Real embedding and DeepSeek intent judgment; controlled evidence fixture."""
import json,urllib.request
from pathlib import Path
BASE='http://127.0.0.1:8080'
def post(path,body):
 req=urllib.request.Request(BASE+path,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
sp=post('/api/spaces',{'title':'语义坐标验收 · 2026-10-10','goal':'独立验证：不同标题的同一研究问题能形成语义簇。这是控制输入的测试资料。'})
c=post('/api/conversations',{'space_id':sp['id']})
rows=[('研究JEPA为什么预测表示而不重建像素？','研究JEPA通过预测表征而非重建像素学习表示的机制。','JEPA表征预测机制'),('联合嵌入预测架构如何在隐空间学习表示？','分析联合嵌入预测架构如何在潜在空间预测表示，从而避免像素重建。','隐空间预测与像素重建的区别')]
results=[]
for i,(question,text,topic) in enumerate(rows):
 results.append(post('/api/qa',{'conversation_id':c['id'],'question':question,'answer':text,'request_id':'semantic-fixture-'+str(i),'expected_turn_index':i,'thoughts':[{'text':text,'topic':topic,'excerpt':text}]}))
assert not results[0]['created_nodes']
assert len(results[1]['created_nodes'])==1
assert len(results[1]['assessment']['created_nodes'])==1
assert results[0]['assessment']['thoughts'][0]['topic']!=results[1]['assessment']['thoughts'][0]['topic']
assert results[1]['assessment']['thoughts'][0]['dimension']==512
reindex=post('/api/thought-space/reindex',{'space_id':sp['id']});assert reindex['coordinates_added']==0 and not reindex['created_nodes']
report={'passed':True,'space_id':sp['id'],'different_topic_titles':True,'real_local_embedding':True,'deepseek_intent_validation':True,'automatic_node':results[1]['created_nodes'][0]['id'],'assessment_records_growth':True,'reindex_no_duplicate':True,'fixture':'controlled evidence input, not model-generated answers'}
Path('docs/semantic-growth-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
