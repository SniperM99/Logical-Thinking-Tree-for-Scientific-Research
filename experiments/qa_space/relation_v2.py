"""Conversation-first offline experiment; no annotated parent/action metadata in prompts."""
import json,os,sys,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_dataset import load_inputs
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
BASE=ROOT/'.runtime/experiments/robot-qa-v1'
OUT_NAME='relation-v2'
SYSTEM="""你为研究树判别当前问答的直接上位问题，根主题由root提供。输入包含上一问、历史问答和上一版AI结构提案；结构提案可能错误，不是标准答案。
任务是区分“对话承接”与“研究问题包含”：后问受前问启发、共享术语、因果相邻，都不自动表示子问题。
先理解当前研究目标与拟定父问题的研究目标，再检查：当前研究目标是否是拟定父问题明确包含的一个具体子任务？子问题可以通过自己的结果回答父问题的一部分；不能因为父问题答案提到了某方向，就把所有相关问题挂到它下面。
必须比较上一版拟定父问题与它的上位问题。若当前和拟定父问题是在共同上位下研究不同维度、不同评价目标或不同假设，应选共同上位，kind=sibling_return，sibling_id=被比较的历史问题。若研究同一目标，仅解释或补充，kind=same_problem。若当前确实缩小范围到拟定父问题的一部分，kind=deepening。
明确指代首先查实际历史来源，而非机械选上一问；回访可以跨过无关插入。独立主题方向可选root；找不到可靠关系则uncertain。
输出parent_id、kind(explicit_reference/deepening/same_problem/sibling_return/history_return/new_direction/uncertain)、reason、current_quote、parent_quote、current_goal、parent_goal、containment_explanation、alternative_explanation、sibling_id。current_quote与parent_quote必须逐字引用各端question/core。containment_explanation说明真正的上下位包含，不能只说相关或承接；alternative_explanation说明为什么不是另一种关系。sibling_return必须给sibling_id(历史比较节点且不同于parent_id)。禁止从编号推断层级。调用resolve_parent。"""
FIELDS=['parent_id','kind','reason','current_quote','parent_quote','current_goal','parent_goal','containment_explanation','alternative_explanation','sibling_id']
SCHEMA={'type':'object','required':FIELDS,'properties':{k:{'type':'string'} for k in FIELDS},'additionalProperties':False}
def validate_relation(d,catalog,current):
 kinds=['explicit_reference','deepening','same_problem','sibling_return','history_return','new_direction']
 parent=catalog.get(d.get('parent_id'))
 if d.get('kind') not in kinds or not parent:return False
 if any(not isinstance(d.get(k),str) or not d[k].strip() for k in ['current_goal','parent_goal','containment_explanation','alternative_explanation']):return False
 if d['kind']=='sibling_return' and (d.get('sibling_id') not in catalog or d['sibling_id']==d['parent_id']):return False
 return all(isinstance(q,str) and len(q)>=3 and any(q in endpoint[f] for f in ['question','core']) for q,endpoint in [(d.get('current_quote'),current),(d.get('parent_quote'),parent)])
def main():
 out=BASE/OUT_NAME;out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 raw=load_inputs(BASE/'inputs/qa.jsonl');labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];outside={l['qa_id'] for l in labels if l['node_type']=='外领域问题'};names={l['qa_id']:l['original_id'] for l in labels};cores={r['qa_id']:r['core'] for r in map(json.loads,(BASE/'descriptors/core.jsonl').read_text().splitlines())};old=json.loads((BASE/'scored-graph/graph.json').read_text());scored=json.loads((BASE/'scored-graph/assessments.json').read_text());root=old['nodes'][0];baseline=json.loads((BASE/'conversation-graph/graph.json').read_text());baseline_idx={n['qa_id']:n for n in baseline['nodes']}
 def desc(r):return {k:r[k] for k in ['qa_id','sequence','question']}|{'core':cores[r['qa_id']]}
 def run(i):
  r=raw[i];history=[desc(h) for h in raw[:i] if h['qa_id'] not in outside];payload={'current':desc(r),'previous_qa':desc(raw[i-1]) if i else None,'history':history,'root':{'qa_id':root['qa_id'],'question':root['question'],'core':root['core']},'retrieved_ids':scored.get(r['qa_id'],{}).get('candidate_ids',[]),'conversation_boundary':'未知真实会话边界：按原始时间流实验，不能把模拟对话段当真实会话。'}
  proposal=baseline_idx.get(r['qa_id']);ancestor=baseline_idx.get(proposal['parent']) if proposal else None;grandparent=baseline_idx.get(ancestor['parent']) if ancestor and ancestor.get('parent') else None
  payload['previous_ai_proposal']={'parent_id':proposal['parent'] if proposal else None,'parent_upper_id':grandparent['qa_id'] if grandparent else None,'warning':'旧AI推断，仅作比较，不是正确标签'}
  key=hashlib.sha256((os.environ['XUNXU_MODEL']+SYSTEM+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():d=json.loads(path.read_text())
  else:
   res=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':2200,'tools':[{'type':'function','function':{'name':'resolve_parent','description':'先承接再历史检索的父节点判别','parameters':SCHEMA}}],'tool_choice':{'type':'function','function':{'name':'resolve_parent'}},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]});choice=res['choices'][0];assert choice.get('finish_reason')!='length';d=json.loads(choice['message']['tool_calls'][0]['function']['arguments']);path.write_text(json.dumps(d,ensure_ascii=False,indent=2))
  catalog={h['qa_id']:h for h in history};catalog[root['qa_id']]=payload['root'];d['evidence_valid']=validate_relation(d,catalog,payload['current'])
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
  if not valid and d.get('kind')=='uncertain':
   ss=scored.get(key,{}).get('scores',[])
   if ss:
    s=ss[0];gap=s['parent_score']-ss[1]['parent_score'];valid=s['relation']=='direct_parent' and s['parent_score']>=70 and gap>=5 and s['evidence_valid'];parent=s['qa_id'];score=s['parent_score'];route='retrieval_fallback'
    if valid:d={**d,'reason':s['reason'],'current_quote':s['current_quote'],'parent_quote':s['candidate_quote']}
  if not valid or parent not in attached:
   pending.append({'qa_id':key,'id':names[key],'question':r['question'],'reason':'未确认逻辑承接/引用，或拟定父节点仍待复核','proposal':d});continue
  nodes.append({**r,'id':names[key],'core':cores[key],'parent':parent,'reason':d['reason'],'evidence':d['current_quote']+' ／ '+d['parent_quote'],'relation':d['kind'],'type':'研究问答','sources':[],'score':score,'score_margin':gap,'decision_route':route,'relation_analysis':d});attached.add(key)
  for rank,s in enumerate(scored.get(key,{}).get('scores',[])[1:3],2):
   if s['qa_id']!=parent and s['qa_id'] in attached and s['relation'] in ['sibling','method','inspiration','validation_dependency'] and s['cross_score']>=75 and s['evidence_valid']:links.append({'source':key,'target':s['qa_id'],'type':s['relation'],'rank':rank,'score':s['cross_score'],'reason':s['reason']})
 idx={n['qa_id']:n for n in nodes};eligible=[l for l in labels if l['parent_qa_id'] and l['qa_id'] not in outside];correct=sum(l['qa_id'] in idx and idx[l['qa_id']]['parent']==l['parent_qa_id'] for l in eligible)
 report={'attached_qa':len(nodes)-1,'pending_qa':len(pending),'cross_links':len(links),'model':os.environ['XUNXU_MODEL'],'policy':'relation-v2: goal containment versus conversational continuation; old AI proposal contrast; retrieval unchanged','scores_calibrated':False,'database_modified':False,'original_parent_labels_used_for_prediction':False,'conversation_boundaries_known':False,'evaluation':{'annotated_edges':len(eligible),'matched':correct,'attached_annotated':sum(l['qa_id'] in idx for l in eligible)},'limitations':'Original chronological stream only, not verified same-conversation experiment. Literal quotes do not establish semantic correctness; manual review required.'}
 for n in nodes:
  if n['parent']:assert idx[n['parent']]['sequence']<n['sequence']
 (out/'graph.json').write_text(json.dumps({'nodes':nodes,'pending':pending,'links':links,'report':report},ensure_ascii=False,indent=2));(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
