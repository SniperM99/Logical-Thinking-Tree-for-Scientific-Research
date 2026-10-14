"""AI reconstructs an offline single-root QA tree. Original parent labels never enter prompts."""
import argparse,json,os,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
from prepare_dataset import load_inputs
from describe_dataset import validate_descriptors
ROOT_ID='smart-manufacturing'
def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args();base=Path(a.dataset);out=base/'single-root-ai';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 rows=load_inputs(base/'inputs/qa.jsonl');cores=[json.loads(l) for l in (base/'descriptors/core.jsonl').read_text().splitlines()];validate_descriptors(rows,cores);core={r['qa_id']:r['core'] for r in cores}
 # Scope exclusion is authoritative dataset metadata, not a model accuracy claim.
 external=json.loads((base/'evaluation/cross_domain.json').read_text());original_labels=[json.loads(l) for l in (base/'evaluation/labels.jsonl').read_text().splitlines()];outside={l['qa_id'] for l in original_labels if l['original_id'] in {r['编号'] for r in external}};in_scope=[r for r in rows if r['qa_id'] not in outside]
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 accepted={ROOT_ID:{'qa_id':ROOT_ID,'question':'智能制造','core':'以智能制造为唯一主题根节点，当前研究围绕柔性制造自主移动操作机器人、世界模型、实验、复现及科研组织展开。','parent_id':None}};decisions=[]
 schema={'type':'object','additionalProperties':False,'required':['items'],'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['qa_id','decision','parent_id','relation','reason','evidence'],'properties':{'qa_id':{'type':'string'},'decision':{'type':'string','enum':['attach','defer']},'parent_id':{'type':'string'},'relation':{'type':'string','enum':['root_direction','specialization','followup','uncertain']},'reason':{'type':'string'},'evidence':{'type':'string'}}}}}}
 system='构建以智能制造为唯一根的研究问题树。所有输入已按用户指定排除独立外领域问题，当前问答来自智能制造机器人研究及其支撑工作。只根据问答语义、已有树和研究范围推断，整数或qa_id仅作引用，不含层级意义。28个上层问答也必须重新判断，不默认平行。优先选择最直接且能涵盖当前问题的已有研究问题为父节点。相同领域、词语接近、刚刚提问都不足以成为父子依据。并列问题应选择共同上位问题，不能接成顺序链。问答对作为过程节点，解释追问可用followup，独立子问题用specialization。只有缺少合适已有上位问题而确实是主题方向时挂smart-manufacturing并标root_direction。输入顺序是实际提问顺序，每条只能以此前已存在节点或同批此前项目为父节点，禁止未来、自引用、合并或移动历史节点。依据不足时defer，parent_id空字符串，relation uncertain。reason说明具体研究范围或承接，80字以内。evidence引用父候选question或core中的原文短片段，必须逐字一致；根节点可引用智能制造。调用deliver_tree，完整输出每条当前项目。'
 for start in range(0,len(in_scope),8):
  batch=in_scope[start:start+8];catalog=[{'qa_id':n['qa_id'],'question':n['question'],'core':n['core'],'parent_id':n['parent_id']} for n in accepted.values()];payload={'root':ROOT_ID,'existing_tree':catalog,'current_items':[{'qa_id':r['qa_id'],'question':r['question'],'answer':r['answer'],'core':core[r['qa_id']]} for r in batch]};key=hashlib.sha256((system+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest();file=cache/(key+'.json')
  if file.exists():items=json.loads(file.read_text())
  else:
   result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'deliver_tree','description':'提出单根研究问题树连线','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_tree'}},'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]});choice=result['choices'][0]
   if choice.get('finish_reason')=='length':raise ValueError('Truncated model output')
   m=choice['message'];text=m['tool_calls'][0]['function']['arguments'] if m.get('tool_calls') else m['content'];items=json.loads(text)['items'];file.write_text(json.dumps(items,ensure_ascii=False,indent=2))
  if len(items)!=len(batch) or {d['qa_id'] for d in items}!={r['qa_id'] for r in batch}:raise ValueError('Output identity mismatch')
  by_id={d['qa_id']:d for d in items}
  for r in batch:
   d=by_id[r['qa_id']];assert d['decision'] in ['attach','defer'];reason=d.get('reason','').strip();assert reason
   if d['decision']=='attach':
    parent=accepted.get(d['parent_id']);evidence=d.get('evidence','').strip()
    sources=[] if parent is None else [('parent_'+field,str(parent.get(field,''))) for field in ['question','core','answer']]+[('current_'+field,str(r.get(field,core[r['qa_id']] if field=='core' else ''))) for field in ['question','core','answer']]
    matches=[name for name,text in sources if evidence and evidence in text]
    d['evidence_locations']=matches
    if parent is None or not evidence or not matches:
     d={**d,'decision':'defer','parent_id':'','relation':'uncertain','validation_failure':'Parent unavailable or evidence quote absent from both QA endpoints'}
    else:
     assert d['relation'] in ['root_direction','specialization','followup'];assert (d['parent_id']==ROOT_ID)==(d['relation']=='root_direction');accepted[r['qa_id']]={**r,'core':core[r['qa_id']],'parent_id':d['parent_id']}
   decisions.append({**d,'sequence':r['sequence'],'model':os.environ['XUNXU_MODEL']})
  (out/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2));print('Processed',len(decisions),'/',len(in_scope),'attached',len(accepted)-1,'pending',sum(d['decision']=='defer' for d in decisions),flush=True)
 labels={l['qa_id']:l for l in original_labels};nodes=[]
 for key,n in accepted.items():
  if key==ROOT_ID:nodes.append({'qa_id':key,'id':'智能制造','question':'智能制造','answer':'用户指定的唯一主题根节点。','core':n['core'],'parent':None,'sequence':0,'type':'主题根节点','sources':[],'reason':'用户指定主题根节点','evidence':'智能制造','relation':'root'})
  else:
   d=next(d for d in decisions if d['qa_id']==key);l=labels[key];nodes.append({**n,'id':l['original_id'],'parent':n['parent_id'],'type':'研究问答','sources':[s for s in l['source_qa_ids'] if s!=l['parent_qa_id']],'reason':d['reason'],'evidence':d['evidence'],'evidence_locations':d.get('evidence_locations',[]),'relation':d['relation']})
 depths={ROOT_ID:0}
 for n in nodes:
  if n['qa_id']!=ROOT_ID:depths[n['qa_id']]=depths[n['parent']]+1
  n['level']=depths[n['qa_id']]
 report={'root':'智能制造','source_qa_count':127,'excluded_outside_domain_count':len(outside),'scope_rule':'Exclude the 13 explicitly annotated external-domain source questions as instructed; no AI relevance accuracy claim.','eligible_count':len(in_scope),'attached_count':len(nodes)-1,'pending_count':sum(d['decision']=='defer' for d in decisions),'root_children':sum(n['parent']==ROOT_ID for n in nodes),'max_depth':max(depths.values()),'old_parent_labels_in_model_inputs':False,'model':os.environ['XUNXU_MODEL'],'validation':'All accepted parents predate their child; evidence quotes match at least one QA endpoint (location recorded); one root and no cycles. Quote matching does not prove semantic relation correctness.','limitations':'AI-inferred hierarchy, not an independently validated reference tree; original parent annotations are not binding for this reconstruction.','database_written':False}
 (out/'tree.json').write_text(json.dumps({'nodes':nodes,'pending':[d for d in decisions if d['decision']=='defer'],'excluded':[labels[k]['original_id'] for k in outside],'report':report,'source_records':[{**r,'id':labels[r['qa_id']]['original_id']} for r in rows if r['qa_id'] in outside]},ensure_ascii=False,indent=2));(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
