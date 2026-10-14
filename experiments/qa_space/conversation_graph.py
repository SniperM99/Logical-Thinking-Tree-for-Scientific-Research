"""Conversation-first offline experiment; no annotated parent/action metadata in prompts."""
import json,os,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_dataset import load_inputs
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
BASE=ROOT/'.runtime/experiments/robot-qa-v1'
SYSTEM='''你判定智能制造研究的当前问答应从哪个历史问题展开。按顺序：先检查上一条真实问答；若是针对它提出的新细化问题，选它。若是解释同一问题，仍关联它但标记same_problem。若是并列方向，找共同上位问题，禁止串成链。若有“上述”“这个思路”等指代，必须结合历史问题和核心描述定位真正来源；最近不等于正确。若上一问不承接，检查历史回访，再考虑检索候选；主题相关不等于父子。跨领域插入后可以回到更早研究。独立主题内方向可归智能制造根。历史仅有时间和问答内容，不含标准答案；不要推测编号层级。输出parent_id、kind(explicit_reference/deepening/same_problem/sibling_return/history_return/new_direction/uncertain)、reason、current_quote、parent_quote；两处引用必须逐字来自两端question/core。无法确认时parent_id为空、kind=uncertain。调用resolve_parent。'''
SCHEMA={'type':'object','required':['parent_id','kind','reason','current_quote','parent_quote'],'properties':{k:{'type':'string'} for k in ['parent_id','kind','reason','current_quote','parent_quote']},'additionalProperties':False}
def main():
 out=BASE/'conversation-graph';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 raw=load_inputs(BASE/'inputs/qa.jsonl');labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];outside={l['qa_id'] for l in labels if l['node_type']=='外领域问题'};names={l['qa_id']:l['original_id'] for l in labels};cores={r['qa_id']:r['core'] for r in map(json.loads,(BASE/'descriptors/core.jsonl').read_text().splitlines())};old=json.loads((BASE/'scored-graph/graph.json').read_text());scored=json.loads((BASE/'scored-graph/assessments.json').read_text());root=old['nodes'][0]
 def desc(r):return {k:r[k] for k in ['qa_id','sequence','question']}|{'core':cores[r['qa_id']]}
 def run(i):
  r=raw[i];history=[desc(h) for h in raw[:i] if h['qa_id'] not in outside];payload={'current':desc(r),'previous_qa':desc(raw[i-1]) if i else None,'history':history,'root':{'qa_id':root['qa_id'],'question':root['question'],'core':root['core']},'retrieved_ids':scored.get(r['qa_id'],{}).get('candidate_ids',[]),'conversation_boundary':'未知真实会话边界：按原始时间流实验，不能把模拟对话段当真实会话。'}
  key=hashlib.sha256((SYSTEM+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():d=json.loads(path.read_text())
  else:
   res=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':1200,'tools':[{'type':'function','function':{'name':'resolve_parent','description':'先承接再历史检索的父节点判别','parameters':SCHEMA}}],'tool_choice':{'type':'function','function':{'name':'resolve_parent'}},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]});choice=res['choices'][0];assert choice.get('finish_reason')!='length';d=json.loads(choice['message']['tool_calls'][0]['function']['arguments']);path.write_text(json.dumps(d,ensure_ascii=False,indent=2))
  catalog={h['qa_id']:h for h in history};catalog[root['qa_id']]=payload['root'];parent=catalog.get(d['parent_id']);d['evidence_valid']=bool(parent) and all(isinstance(q,str) and len(q)>=3 and any(q in endpoint[f] for f in ['question','core']) for q,endpoint in [(d['current_quote'],payload['current']),(d['parent_quote'],parent)])
  return r['qa_id'],d
 decisions={};indices=[i for i,r in enumerate(raw) if r['qa_id'] not in outside and i>0]
 with ThreadPoolExecutor(max_workers=4) as pool:
  for future in as_completed([pool.submit(run,i) for i in indices]):
   k,d=future.result();decisions[k]=d;print('Resolved',len(decisions),'/',len(indices),flush=True)
 (out/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2))
 nodes=[root];attached={root['qa_id']};pending=[];links=[]
 for r in raw:
  key=r['qa_id']
  if key in outside:continue
  if key==raw[0]['qa_id']:d={'parent_id':root['qa_id'],'kind':'new_direction','reason':'首条主题问答','current_quote':r['question'],'parent_quote':'智能制造','evidence_valid':True}
  else:d=decisions[key]
  parent=d['parent_id'];route='conversation';score=None;gap=None
  valid=d['kind'] in ['explicit_reference','deepening','same_problem','sibling_return','history_return','new_direction'] and d['evidence_valid']
  if not valid:
   ss=scored.get(key,{}).get('scores',[])
   if ss:
    s=ss[0];gap=s['parent_score']-ss[1]['parent_score'];valid=s['relation']=='direct_parent' and s['parent_score']>=70 and gap>=5 and s['evidence_valid'];parent=s['qa_id'];score=s['parent_score'];route='retrieval_fallback'
    if valid:d={**d,'reason':s['reason'],'current_quote':s['current_quote'],'parent_quote':s['candidate_quote']}
  if not valid or parent not in attached:
   pending.append({'qa_id':key,'id':names[key],'question':r['question'],'reason':'未确认逻辑承接/引用，或拟定父节点仍待复核','proposal':d});continue
  nodes.append({**r,'id':names[key],'core':cores[key],'parent':parent,'reason':d['reason'],'evidence':d['current_quote']+' ／ '+d['parent_quote'],'relation':d['kind'],'type':'研究问答','sources':[],'score':score,'score_margin':gap,'decision_route':route});attached.add(key)
  for rank,s in enumerate(scored.get(key,{}).get('scores',[])[1:3],2):
   if s['qa_id']!=parent and s['qa_id'] in attached and s['relation'] in ['sibling','method','inspiration','validation_dependency'] and s['cross_score']>=75 and s['evidence_valid']:links.append({'source':key,'target':s['qa_id'],'type':s['relation'],'rank':rank,'score':s['cross_score'],'reason':s['reason']})
 idx={n['qa_id']:n for n in nodes};eligible=[l for l in labels if l['parent_qa_id'] and l['qa_id'] not in outside];correct=sum(l['qa_id'] in idx and idx[l['qa_id']]['parent']==l['parent_qa_id'] for l in eligible)
 report={'attached_qa':len(nodes)-1,'pending_qa':len(pending),'cross_links':len(links),'model':os.environ['XUNXU_MODEL'],'policy':'conversation-first with literal evidence; uncertain cases fall back to previous scored retrieval','scores_calibrated':False,'database_modified':False,'original_parent_labels_used_for_prediction':False,'conversation_boundaries_known':False,'evaluation':{'annotated_edges':len(eligible),'matched':correct,'attached_annotated':sum(l['qa_id'] in idx for l in eligible)},'limitations':'Original chronological stream only, not verified same-conversation experiment. Literal quotes do not establish semantic correctness; manual review required.'}
 for n in nodes:
  if n['parent']:assert idx[n['parent']]['sequence']<n['sequence']
 (out/'graph.json').write_text(json.dumps({'nodes':nodes,'pending':pending,'links':links,'report':report},ensure_ascii=False,indent=2));(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
