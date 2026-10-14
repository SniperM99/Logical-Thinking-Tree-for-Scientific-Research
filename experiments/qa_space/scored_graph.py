"""Offline scored parent/cross-link experiment; scores are uncalibrated, never probabilities."""
import json,sys,os,hashlib,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_dataset import load_inputs
from improve_retrieval import bm25
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
POLICY='scored-graph-v1:parent>=70:margin>=5:cross>=75:only-ranks-2-3'
SYSTEM='智能制造根节点是常驻候选，允许独立的新研究方向挂到根；有直接已有上位问题时优先选它，禁止为凑树挂根。根候选的direct_parent表示主题方向归属。你为智能制造单根科研树判别候选关系。当前问答与候选都属于该研究及支撑活动。每条候选独立输出parent_score(0-100)表示作为最直接父问题的适配度：研究范围包含、明确承接、直接程度；cross_score(0-100)表示其他明确关联的强度。分数非概率。relation可为direct_parent(直接上位)、sibling(同一上位下并列)、method(方法借鉴)、inspiration(综合启发)、validation_dependency(验证依赖)、topic_related(仅主题相关)、none。父问题必须能说明当前问题展开其哪部分；不能因词语相似或刚提问就判父子。并列禁止视为父子，宽泛祖先不能替代直接父问题。对每个候选给出具体reason以及current_quote和candidate_quote，分别逐字引用当前、候选question/core/answer_excerpt。没有具体依据时低分、none、引用空字符串。每个候选必须输出，不增加候选，调用score_candidates。'
def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args();base=Path(a.dataset);out=base/'scored-graph';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 raw=load_inputs(base/'inputs/qa.jsonl');labels=[json.loads(l) for l in (base/'evaluation/labels.jsonl').read_text().splitlines()];outside={l['qa_id'] for l in labels if l['node_type']=='外领域问题'};rows=[r for r in raw if r['qa_id'] not in outside];cores={r['qa_id']:r['core'] for r in map(json.loads,(base/'descriptors/core.jsonl').read_text().splitlines())};names={l['qa_id']:l['original_id'] for l in labels};lookup={r['qa_id']:r for r in rows};ranking=bm25(['问题：'+r['question']+'\n回答：'+r['answer'] for r in rows],[r['question'] for r in rows])
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 def desc(r):return {'qa_id':r['qa_id'],'question':r['question'],'core':cores[r['qa_id']],'answer_excerpt':r['answer'][:400]}
 schema={'type':'object','additionalProperties':False,'required':['scores'],'properties':{'scores':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['qa_id','parent_score','cross_score','relation','reason','current_quote','candidate_quote'],'properties':{'qa_id':{'type':'string'},'parent_score':{'type':'integer'},'cross_score':{'type':'integer'},'relation':{'type':'string','enum':['direct_parent','sibling','method','inspiration','validation_dependency','topic_related','none']},'reason':{'type':'string'},'current_quote':{'type':'string'},'candidate_quote':{'type':'string'}}}}}}
 def run(i):
  current=desc(rows[i]);candidates=[desc(rows[j]) for j in ranking[i][:10]]+[{'qa_id':'smart-manufacturing','question':'智能制造','core':'智能制造主题：柔性制造自主移动操作机器人、世界模型、实验验证、文献复现与科研组织支撑。','answer_excerpt':'唯一主题根节点，新的相关研究方向可直接从此展开。'}];payload={'current':current,'candidates':candidates};key=hashlib.sha256((SYSTEM+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():scores=json.loads(path.read_text())
  else:
   result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'score_candidates','description':'逐对判别父子与交叉关系','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'score_candidates'}},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]});c=result['choices'][0];assert c.get('finish_reason')!='length';m=c['message'];text=m['tool_calls'][0]['function']['arguments'] if m.get('tool_calls') else m['content'];scores=json.loads(text)['scores'];path.write_text(json.dumps(scores,ensure_ascii=False,indent=2))
  assert len(scores)==len(candidates) and {s['qa_id'] for s in scores}=={c['qa_id'] for c in candidates}
  admitted={c['qa_id']:c for c in candidates}
  for s in scores:
   assert isinstance(s['parent_score'],int) and 0<=s['parent_score']<=100 and isinstance(s['cross_score'],int) and 0<=s['cross_score']<=100
   s['evidence_valid']=all(isinstance(s.get(key),str) and len(s[key])>=3 and any(s[key] in r[field] for field in ['question','core','answer_excerpt']) for key,r in [('current_quote',current),('candidate_quote',admitted[s['qa_id']])])
  scores.sort(key=lambda s:(-s['parent_score'],next(j for j,c in enumerate(candidates) if c['qa_id']==s['qa_id'])))
  return {'qa_id':rows[i]['qa_id'],'scores':scores,'candidate_ids':[c['qa_id'] for c in candidates]}
 assessments={}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for future in as_completed([pool.submit(run,i) for i in range(1,len(rows))]):
   r=future.result();assessments[r['qa_id']]=r;print('Scored',len(assessments),'/',len(rows)-1,flush=True)
 (out/'assessments.json').write_text(json.dumps(assessments,ensure_ascii=False,indent=2))
 root={'qa_id':'smart-manufacturing','id':'智能制造','question':'智能制造','answer':'用户指定唯一主题根。','core':'智能制造主题：柔性制造自主移动操作机器人、世界模型、实验验证、文献复现与科研组织支撑。','parent':None,'sequence':0,'type':'主题根','sources':[],'reason':'用户指定','evidence':'智能制造','relation':'root'};nodes=[root];attached={root['qa_id']};pending=[];links=[]
 # The first on-topic overview has no prior QA candidate, explicitly anchored to the user root.
 first=rows[0];nodes.append({**first,'id':names[first['qa_id']],'core':cores[first['qa_id']],'parent':root['qa_id'],'reason':'首个主题内问答，无历史候选，作为研究入口','evidence':first['question'],'relation':'root_direction','type':'研究问答','sources':[],'score':None});attached.add(first['qa_id'])
 for r in rows[1:]:
  ranked=assessments[r['qa_id']]['scores'];top=ranked[0];gap=top['parent_score']-(ranked[1]['parent_score'] if len(ranked)>1 else 0);accepted=top['relation']=='direct_parent' and top['parent_score']>=70 and gap>=5 and top['evidence_valid'] and top['qa_id'] in attached
  if not accepted:pending.append({'qa_id':r['qa_id'],'id':names[r['qa_id']],'question':r['question'],'proposal':top,'margin':gap,'reason':'最高分候选未同时满足父子类型、70分、5分差、引用校验或父节点已关联要求'});continue
  nodes.append({**r,'id':names[r['qa_id']],'core':cores[r['qa_id']],'parent':top['qa_id'],'reason':top['reason'],'evidence':top['current_quote']+' ／ '+top['candidate_quote'],'relation':'specialization','type':'研究问答','sources':[],'score':top['parent_score'],'score_margin':gap});attached.add(r['qa_id'])
  for rank,s in enumerate(ranked[1:3],2):
   if s['relation'] in ['sibling','method','inspiration','validation_dependency'] and s['cross_score']>=75 and s['evidence_valid'] and s['qa_id'] in attached:links.append({'source':r['qa_id'],'target':s['qa_id'],'type':s['relation'],'rank':rank,'score':s['cross_score'],'reason':s['reason'],'current_quote':s['current_quote'],'candidate_quote':s['candidate_quote']})
 report={'policy':POLICY,'model':os.environ['XUNXU_MODEL'],'eligible_qa':len(rows),'attached_qa':len(nodes)-1,'pending_qa':len(pending),'cross_links':len(links),'root_rule':'First on-topic overview is anchored to the user root; later cases may abstain, no forced root fallback.','scores_calibrated':False,'original_parent_labels_used_for_prediction':False,'root_is_always_candidate':True,'qa_candidates_per_query':10,'thresholds_exploratory':True,'original_external_labels_used_for_scope_filter':True,'database_modified':False,'limitations':'This intentionally conservative policy can cascade abstentions when a proposed parent is pending. No independent gold-standard cross-link evaluation.'}
 (out/'graph.json').write_text(json.dumps({'nodes':nodes,'pending':pending,'links':links,'report':report},ensure_ascii=False,indent=2));(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
