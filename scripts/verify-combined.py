"""Real-model acceptance: two turns, space entry, immutable anchor and round assessments."""
import json,urllib.request,uuid,sys
from pathlib import Path
base='http://127.0.0.1:8080'
def call(path,data=None):
 req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=150) as response:return json.load(response)
if len(sys.argv)>1:
 state=call('/api/state?space_id='+sys.argv[1]);space=next(x for x in state['spaces'] if x['id']==sys.argv[1]);conv=state['conversations'][0];q=state['qas'][0]
 first_data={'conversation_id':conv['id'],'question':q['question'],'request_id':q['request_id'],'expected_turn_index':0}
 first=call('/api/qa',first_data)
else:
 space=call('/api/spaces',{'title':'合并请求验收 · 2026-10-10','goal':'验证连续科研会话的参数记忆、原始锚点和逐轮分析；这是软件接入测试。'})
 conv=call('/api/conversations',{'space_id':space['id']})
 assert conv['anchor_id']==space['root_id'] and conv['origin_scope']=='space'
 first_data={'conversation_id':conv['id'],'question':'为了测试我们的连续科研讨论，拟对小型神经网络采用固定随机种子43871进行学习率对照。请记住这个种子，只用一句话确认，这是假设设计而非已运行实验。','request_id':uuid.uuid4().hex,'expected_turn_index':0}
 first=call('/api/qa',first_data)
second=call('/api/qa',{'conversation_id':conv['id'],'question':'我刚才为这个对照设计指定的随机种子是多少？只回复数字，不添加说明。','request_id':uuid.uuid4().hex,'expected_turn_index':1})
assert first['qa']['generation']['answer_extraction_requests']==1
assert second['qa']['generation']['answer_extraction_requests']==1
assert first['assessment']['thoughts'] and second['assessment']['thoughts']
assert all(t['dimension']==512 for t in first['assessment']['thoughts'])
assert '43871' in second['qa']['answer'],second['qa']['answer']
restored=call('/api/conversations/'+conv['id'])
assert restored['conversation']['anchor_id']==space['root_id']
assert len(restored['qas'])==2 and [q['turn_index'] for q in restored['qas']]==[1,2]
assert restored['assessments'][first['qa']['id']]==first['assessment']
assert len(restored['assessments'])==2
assert call('/api/qa',first_data)['idempotent']
report={'passed':True,'answer_extraction_requests_per_turn':1,'local_coordinate_dimension':512,'usage_by_turn':[first['qa']['generation']['usage'],second['qa']['generation']['usage']],'space_id':space['id'],'conversation_id':conv['id'],'origin_scope':'space','anchor_id':space['root_id'],'turn_count':2,'followup_answer':second['qa']['answer'],'round_assessment_count':2,'first_round_assessment_preserved':True,'request_replay_idempotent':True}
Path('docs/combined-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
