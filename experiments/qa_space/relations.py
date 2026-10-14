"""Experimental relation adjudication over multi-view semantic candidates, no graph writes."""
import json,os,sys,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request

def candidate_union(vectors,index,per_view=5):
 scores={};support={}
 for name,v in vectors.items():
  similarity=v[index]@v[:index].T
  for rank,j in enumerate(np.argsort(-similarity)[:per_view],1):
   j=int(j);scores[j]=scores.get(j,0)+1/(60+rank);support.setdefault(j,[]).append(name)
 return sorted(scores,key=lambda j:-scores[j]),support

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--experiment',required=True);args=p.parse_args();out=Path(args.experiment)
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 rows=json.loads(Path(args.data).read_text())[0]['rows'][1:];cores=json.loads((out/'core80.json').read_text());vectors=dict(np.load(out/'vectors.npz'));ids={r[0]:i for i,r in enumerate(rows)};queries=[i for i,r in enumerate(rows) if '.' in r[0]]
 cache=out/'relations-cache';cache.mkdir(exist_ok=True)
 def run(start):
  subset=queries[start:start+6];file=cache/f'{start:03}.json'
  if file.exists():return json.loads(file.read_text())
  cases=[];lookup={}
  for i in subset:
   candidates,_=candidate_union(vectors,i);lookup[i]=candidates
   cases.append({'item':i,'question':rows[i][1],'core':cores[i]['core'],'candidates':[{'candidate':j,'question':rows[j][1],'core':cores[j]['core']} for j in candidates]})
  schema={'type':'object','additionalProperties':False,'required':['items'],'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['item','relation','candidate','reason'],'properties':{'item':{'type':'integer'},'relation':{'type':'string','enum':['same_problem','child','sibling','cross_source','uncertain']},'candidate':{'type':'integer'},'reason':{'type':'string'}}}}}}
  result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'judge_relations','description':'判断研究范围关系，绝不修改研究图','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'judge_relations'}},'messages':[{'role':'system','content':'每个case独立判断当前问答与候选的研究范围关系。只使用问题和核心描述，整数只是无语义引用键，不代表层级或顺序。优先选择最直接的已有上位问题而不是最相似的细节。child表示当前问题具体展开候选的一个子问题；same_problem表示同一持续研究问题的解释、证据或追问；sibling表示同一个上位范围的不同方向，不能把参照兄弟当父节点；cross_source表示外领域启发来源，不能替代主研究问题父节点；uncertain表示候选缺失或证据不足，candidate填-1。区分语义相似与范围包含。不要机械选择最近提问。每条reason说明范围依据，限80字。所有case必须输出，调用judge_relations。'},{'role':'user','content':json.dumps(cases,ensure_ascii=False)}]})
  choice=result['choices'][0];assert choice.get('finish_reason')!='length';m=choice['message'];payload=m['tool_calls'][0]['function']['arguments'] if m.get('tool_calls') else m['content'];items=json.loads(payload)['items'];assert {d['item'] for d in items}==set(subset) and len(items)==len(subset)
  for d in items:
   assert d['relation'] in ['same_problem','child','sibling','cross_source','uncertain'];assert d['candidate'] in lookup[d['item']] or (d['relation']=='uncertain' and d['candidate']==-1)
   d['admitted_candidates']=lookup[d['item']]
  file.write_text(json.dumps(items,ensure_ascii=False,indent=2));return items
 decisions=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  for f in as_completed([pool.submit(run,i) for i in range(0,len(queries),6)]):decisions.extend(f.result());print('Relation cases completed',len(decisions),'/',len(queries),flush=True)
 evaluated=[]
 for d in sorted(decisions,key=lambda x:x['item']):
  i=d['item'];parent=ids[rows[i][0].rsplit('.',1)[0]];evaluated.append({**d,'id':rows[i][0],'reference_parent':rows[parent][0],'selected':rows[d['candidate']][0] if d['candidate']>=0 else None,'reference_available':parent in d['admitted_candidates'],'reference_parent_selected':d['candidate']==parent})
 report={'cases':len(evaluated),'reference_recall':sum(d['reference_available'] for d in evaluated)/len(evaluated),'reference_parent_selection':sum(d['reference_parent_selected'] for d in evaluated)/len(evaluated),'relation_counts':{kind:sum(d['relation']==kind for d in evaluated) for kind in ['same_problem','child','sibling','cross_source','uncertain']},'decisions':evaluated,'limitations':['Semantic parent choices are compared against identifier hierarchy only.','same_problem can deliberately select the reference parent while declining to create a new node.','This single synthetic dataset cannot establish optimality or calibrate production confidence.']}
 (out/'relations.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='decisions'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
