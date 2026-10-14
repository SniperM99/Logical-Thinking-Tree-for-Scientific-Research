"""Contextual BM25 ablation: enrich documents only; preserve original query and top-10 budget."""
import argparse,json,os,sys,hashlib,csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_dataset import load_inputs
from describe_dataset import validate_descriptors
from improve_retrieval import bm25
from measure_ai_tree import evaluate
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
SYSTEM='为智能制造机器人科研问答生成用于检索的背景。只根据当前问答及此前历史识别研究对象、具体目标和适用条件，将省略指代明确化。不判断父节点，不按最近一轮强行继承主题，不补造假设。历史含跨领域插入，只有明确承接时才能使用其内容。context为一段尽量80字以内的具体背景，不写智能制造等所有问答共有的泛化开场，不复述整段回答。无法明确时保留原问题具体内容，不猜测。给出1至2个逐字引用作为依据，quote必须来自指定qa_id的question、answer或core字段，history只提供question和core。任何ID仅作引用，无层级意义。调用deliver_context，完整输出每个qa_id。'
def validate_context(item,record,history):
 allowed={r['qa_id']:r for r in history+[record]};context=item.get('context','');cites=item.get('citations',[])
 if not isinstance(context,str) or not context.strip() or len(context)>180:return False
 if not isinstance(cites,list) or not 1<=len(cites)<=2:return False
 for cite in cites:
  source=allowed.get(cite.get('qa_id'));field=cite.get('field');quote=cite.get('quote')
  if source is None or field not in ['question','answer','core'] or not isinstance(quote,str) or len(quote)<3 or quote not in source.get(field,''):return False
 return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);args=p.parse_args();base=Path(args.dataset);out=base/'contextual-bm25';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 raw=load_inputs(base/'inputs/qa.jsonl');cores=[json.loads(l) for l in (base/'descriptors/core.jsonl').read_text().splitlines()];validate_descriptors(raw,cores);core={r['qa_id']:r['core'] for r in cores};indices={r['qa_id']:i for i,r in enumerate(raw)}
 tree_bytes=(base/'ai-tree-recall/tree-snapshot.json').read_bytes();tree=json.loads(tree_bytes);membership={n['qa_id'] for n in tree['nodes'] if n['parent']};selected=[r for r in raw if r['qa_id'] in membership]
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 cases=[]
 for r in selected:
  history=[{'qa_id':q['qa_id'],'question':q['question'],'core':core[q['qa_id']]} for q in raw[max(0,indices[r['qa_id']]-8):indices[r['qa_id']]]]
  cases.append({'current':{**r,'core':core[r['qa_id']]},'history':history})
 schema={'type':'object','additionalProperties':False,'required':['items'],'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['qa_id','context','citations'],'properties':{'qa_id':{'type':'string'},'context':{'type':'string'},'citations':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['qa_id','field','quote'],'properties':{'qa_id':{'type':'string'},'field':{'type':'string','enum':['question','answer','core']},'quote':{'type':'string'}}}}}}}}}
 def run(start):
  batch=cases[start:start+1];key=hashlib.sha256((SYSTEM+json.dumps(batch,ensure_ascii=False)).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():items=json.loads(path.read_text())
  else:
   result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'deliver_context','description':'从问答生成有原文依据的检索背景','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_context'}},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(batch,ensure_ascii=False)}]});choice=result['choices'][0]
   if choice.get('finish_reason')=='length':raise ValueError('Context output truncated')
   m=choice['message'];payload=m['tool_calls'][0]['function']['arguments'] if m.get('tool_calls') else m['content'];items=json.loads(payload)['items'];path.write_text(json.dumps(items,ensure_ascii=False,indent=2))
  if len(items)!=len(batch) or {x['qa_id'] for x in items}!={x['current']['qa_id'] for x in batch}:raise ValueError('Context identity mismatch')
  records=[]
  for case in batch:
   r=case['current'];item=next(x for x in items if x['qa_id']==r['qa_id']);valid=validate_context(item,r,case['history']);records.append({**item,'sequence':r['sequence'],'citation_check':valid,'index_context':item['context'] if valid else '', 'fallback_to_baseline':not valid,'history_ids':[q['qa_id'] for q in case['history']]})
  return records
 contexts=[]
 with ThreadPoolExecutor(max_workers=4) as pool:
  for future in as_completed([pool.submit(run,i) for i in range(0,len(cases),1)]):contexts.extend(future.result());print('Contexts',len(contexts),'/',len(selected),flush=True)
 contexts.sort(key=lambda r:r['sequence']);assert [r['qa_id'] for r in selected]==[r['qa_id'] for r in contexts];(out/'contexts.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in contexts))
 docs=['问题：'+r['question']+'\n回答：'+r['answer'] for r in selected];queries=[r['question'] for r in selected];enhanced=[('背景：'+c['index_context']+'\n' if c['index_context'] else '')+d for c,d in zip(contexts,docs)]
 base_rank=bm25(docs,queries);new_rank=bm25(enhanced,queries);predictions={name:[{'qa_id':r['qa_id'],'top10':[selected[j]['qa_id'] for j in rank[i][:10]]} for i,r in enumerate(selected)] for name,rank in [('baseline',base_rank),('contextual',new_rank)]};(out/'predictions.json').write_text(json.dumps(predictions,ensure_ascii=False,indent=2));(out/'indexed-documents.jsonl').write_text(''.join(json.dumps({'qa_id':r['qa_id'],'text':text},ensure_ascii=False)+'\n' for r,text in zip(selected,enhanced)))
 # Parent edges become evaluation targets only after retrieval outputs are frozen.
 parents={n['qa_id']:n['parent'] for n in tree['nodes'] if n['parent']};names={n['qa_id']:n['id'] for n in tree['nodes']};base_m,base_d=evaluate(selected,base_rank,parents);new_m,new_d=evaluate(selected,new_rank,parents);assert base_m['recall10_hits']==97 and base_m['cases']==111
 previous=json.loads((base/'ai-tree-recall/predictions.json').read_text())['bm25'];assert [r['top10'] for r in previous]==[r['top10'] for r in predictions['baseline']]
 gains=[];losses=[];details=[]
 for old,new in zip(base_d,new_d):
  assert old['qa_id']==new['qa_id'];key=new['qa_id'];gain=old['parent_rank']>10>=new['parent_rank'];loss=new['parent_rank']>10>=old['parent_rank'];
  if gain:gains.append(names[key])
  if loss:losses.append(names[key])
  details.append({'qa_id':key,'id':names[key],'question':next(r['question'] for r in selected if r['qa_id']==key),'parent':names[new['parent_qa_id']],'baseline_rank':old['parent_rank'],'contextual_rank':new['parent_rank'],'context':next(c['index_context'] for c in contexts if c['qa_id']==key),'top10':[names[k] for k in new['top10']],'change':'新增命中' if gain else '丢失命中' if loss else '均命中' if new['parent_rank']<=10 else '均漏召回'})
 (out/'evaluation.jsonl').write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in details))
 for filename,subset in [('comparison.csv',details),('failures.csv',[d for d in details if d['contextual_rank']>10])]:
  with (out/filename).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f);w.writerow(['节点','问题','AI指定父节点','原BM25排名','增强后排名','背景补充','前十候选','变化'])
   for d in subset:w.writerow([d['id'],d['question'],d['parent'],d['baseline_rank'],d['contextual_rank'],d['context'],'；'.join(d['top10']),d['change']])
 report={'target':'AI tree parent reproduction','model':os.environ['XUNXU_MODEL'],'method':'Append source-grounded background to indexed QA only; original questions and BM25 parameters unchanged; no query rewriting.','history_window':8,'budget':10,'tree_sha256':hashlib.sha256(tree_bytes).hexdigest(),'input_sha256':hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest(),'contexts_generated':len(contexts),'citation_pass_count':sum(c['citation_check'] for c in contexts),'fallback_count':sum(c['fallback_to_baseline'] for c in contexts),'baseline':base_m,'contextual':new_m,'new_top10_hits':gains,'lost_top10_hits':losses,'limitations':['Target is the existing AI tree, not independently verified research truth.','Source quote validation checks literal grounding, not semantic correctness of every generated context.','Background model receives current QA and at most 8 preceding raw conversations, not true parents, graph paths, original IDs or future QA.','Candidate membership is the frozen tree inventory, including only previously accepted QA nodes.','No tuning to these results, no tree or database modifications.'],'files':{}}
 for file in out.iterdir():
  if file.is_file() and file.name not in ['metrics.json','report.md']:report['files'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
 (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 text='# 上下文增强BM25实验\n\n使用112条已关联问答，111条非根父关系评价，候选仍取此前已关联节点前十。索引背景只由当前问答及最多8条此前对话生成，引用逐字校验，不使用AI树父节点或原表关系标注。未改写查询。\n\n|指标|原BM25|背景增强BM25|\n|---|---:|---:|\n'
 for metric,label in [('top1','最近邻命中'),('recall5','前五召回'),('recall10','前十召回')]:text+=f"|{label}|{base_m[metric]:.2%}|{new_m[metric]:.2%}|\n"
 text+='\n新增前十命中 '+str(len(gains))+' 条，丢失 '+str(len(losses))+' 条。背景引用校验通过 '+str(report['citation_pass_count'])+'/112，失败 '+str(report['fallback_count'])+' 条保留原索引。全部上下文与逐条排名可复核。\n\n这是对现有AI树的父节点复现测量，不代表研究关系准确率。字面引用匹配也不证明全部背景解释正确。没有调整树、扩大候选预算或隐藏退步案例。\n'
 (out/'report.md').write_text(text);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
