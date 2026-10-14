"""Sequential, append-only research growth. No baseline graph or parent annotations in prediction."""
import argparse,json,os,sys,time,hashlib,math,re
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
from embeddings import local_embedding,METHOD
from prepare_dataset import load_inputs
SYSTEM='''你负责研究树的单条增量生长，已有树不可移动或改写。根主题由root指定。先判断当前问答是否在研究范围内；域外输出out_of_scope，不为凑树收录。提供的context是最新已提交的局部结构，不是全历史。上一问的assigned_node是实际归属；时间流不保证同一会话。当前目标相同仅补充解释或证据时same_problem，关联现有节点资源，不新建。明确研究目标是上位问题的子任务时deepening；对话承接不等于层级包含。研究不同维度且同属一个上位时sibling，应选共同上位parent_id，并给sibling_id作为比较对象。历史指代来源不在context，或找不到更直接父问题时needs_retrieval；stage=global后仍无法确认则uncertain。相关方法不是父节点。每条问答最终提交前都检索已有空间，将检索候选与局部提案比较，选最直接归属，解释采用和排除候选的理由。局部深化成立不等于整个空间最直接。独立主题方向new_direction可归root，但局部没有合适父问题不代表整个空间没有。准备挂根或创建new_direction时必须先检索已有空间；stage=global时必须比较检索候选并解释为何没有更直接归属，不能仅因与根主题相关而挂根。不能根据编号猜层级。输出kind,parent_id,sibling_id,reason,current_goal,parent_goal,containment_explanation,alternative_explanation,current_quote,parent_quote。两端引用逐字来自question/core。out_of_scope/needs_retrieval/uncertain允许引用空串。引用有效不代表语义正确，必须解释包含与并列差别。调用grow_one。'''
KINDS=['same_problem','deepening','sibling','history_return','new_direction','out_of_scope','needs_retrieval','uncertain']
FIELDS=['kind','parent_id','sibling_id','reason','current_goal','parent_goal','containment_explanation','alternative_explanation','current_quote','parent_quote']
SCHEMA={'type':'object','required':FIELDS,'additionalProperties':False,'properties':{k:({'type':'string','enum':KINDS} if k=='kind' else {'type':'string'}) for k in FIELDS}}
def needs_space_check(decision,valid,root_id='research-root'):
 return not valid or decision.get('kind') in ['needs_retrieval','uncertain','new_direction'] or (decision.get('parent_id')==root_id and decision.get('kind')!='out_of_scope')
def root_check_schema():
 return {**SCHEMA,'required':FIELDS+['closer_parent_found','root_check_reason'],'properties':{**SCHEMA['properties'],'closer_parent_found':{'type':'boolean'},'root_check_reason':{'type':'string','description':'比较检索候选，说明是否存在更直接归属'}}}
def root_confirmed(decision,root_id='research-root'):
 if decision.get('parent_id')!=root_id and decision.get('kind')!='new_direction':return True
 return decision.get('closer_parent_found') is False and bool(str(decision.get('root_check_reason','')).strip())
def tokens(text):
 return Counter(re.findall(r'[a-zA-Z][a-zA-Z0-9-]*',text.lower())+[s[i:i+2] for s in re.findall(r'[\u4e00-\u9fff]+',text) for i in range(len(s)-1)])
class OnlineIndex:
 def __init__(self):self.docs=[];self.df=Counter();self.total=0
 def add(self,key,text,vector):
  d=tokens(text);self.docs.append((key,d,vector));self.df.update(d.keys());self.total+=sum(d.values())
 def search(self,text,vector,budget):
  n=len(self.docs)
  if not n:return []
  q=tokens(text);avg=self.total/n;lex=[];dense=[]
  for key,d,v in self.docs:
   score=sum(math.log(1+(n-self.df[t]+.5)/(self.df[t]+.5))*d[t]*2.2/(d[t]+1.2*(.25+.75*sum(d.values())/max(avg,1))) for t in q if t in d)
   lex.append((key,score));dense.append((key,float(np.dot(vector,v))))
  fused=Counter()
  for ranking in [sorted(lex,key=lambda x:-x[1]),sorted(dense,key=lambda x:-x[1])]:
   for rank,(key,_) in enumerate(ranking,1):fused[key]+=1/(60+rank)
  return [key for key,_ in fused.most_common(budget)]
def new_state(theme,scope):
 root={'qa_id':'research-root','id':theme,'question':theme,'core':scope,'answer':'用户配置的研究主题','parent':None,'sequence':0,'sources':[],'relation':'root','type':'主题根','reason':'配置','evidence':theme,'position':{'x':1000,'y':100000}}
 return {'nodes':[root],'pending':[],'resources':[],'outside':[],'processed':[],'assignments':{},'events':[],'links':[],'revision':0}
def validate(d,current,context):
 if d.get('kind') not in KINDS:return False
 if d['kind'] in ['out_of_scope','needs_retrieval','uncertain']:return True
 by={n['qa_id']:n for n in context};p=by.get(d.get('parent_id'))
 if not p:return False
 if d['kind']=='sibling' and (d.get('sibling_id') not in by or d['sibling_id']==p['qa_id']):return False
 if any(not str(d.get(k,'')).strip() for k in ['current_goal','parent_goal','containment_explanation','alternative_explanation']):return False
 return all(isinstance(q,str) and len(q)>=3 and any(q in endpoint[f] for f in ['question','core']) for q,endpoint in [(d.get('current_quote'),current),(d.get('parent_quote'),p)])
def commit(state,row,core,d,valid):
 if row['qa_id'] in state['processed']:
  existing=next(r for r in state['nodes']+state['resources']+state['pending']+state['outside'] if r['qa_id']==row['qa_id'])
  assert all(existing[k]==row[k] for k in ['question','answer']), 'QA identity reused with changed content'
  return next(e for e in state['events'] if e['qa_id']==row['qa_id'])
 before={n['qa_id']:(n['parent'],dict(n['position'])) for n in state['nodes']};by={n['qa_id']:n for n in state['nodes']};kind=d['kind'];parent=d.get('parent_id');key=row['qa_id'];action='pending'
 record={**row,'core':core,'proposal':d,'reason':d['reason'],'id':key}
 if kind=='out_of_scope' and valid:state['outside'].append(record);action='outside'
 elif valid and parent in by and kind not in ['uncertain','needs_retrieval']:
  if kind=='same_problem':state['resources'].append({**record,'storage_anchor':parent,'status':'同问题补充'});state['assignments'][key]=parent;action='resource'
  else:
   p=by[parent];depth=p.get('depth',0)+1;y=100000-depth*140;x=p['position']['x'];occupied={n['position']['x'] for n in state['nodes'] if n['position']['y']==y};offset=0
   while x in occupied:
    offset+=1;x=p['position']['x']+(1 if offset%2 else -1)*((offset+1)//2)*200
   state['nodes'].append({**record,'parent':parent,'sources':[],'relation':kind,'type':'研究问答','evidence':d['current_quote']+' ／ '+d['parent_quote'],'position':{'x':x,'y':y},'depth':depth,'relation_analysis':d});state['assignments'][key]=key;action='node'
 else:state['pending'].append({**record,'storage_anchor':parent if parent in by else None,'status':'待判定，非父子关系'})
 state['revision']+=1;state['processed'].append(key)
 assert all((n['parent'],n['position'])==before[n['qa_id']] for n in state['nodes'] if n['qa_id'] in before)
 event={'revision':state['revision'],'qa_id':key,'action':action,'suggested_parent':parent,'existing_nodes_moved':0,'existing_edges_changed':0};state['events'].append(event);return event

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dataset',default=str(ROOT/'.runtime/experiments/robot-qa-v1'));ap.add_argument('--theme',default='智能制造');ap.add_argument('--scope',default='智能制造及自主移动操作机器人研究，包含研究设计、仿真、实验验证及相关方法；独立的其他领域问答不自动属于此研究。');ap.add_argument('--budget',type=int,default=10);ap.add_argument('--limit',type=int);a=ap.parse_args();base=Path(a.dataset);out=base/'incremental-growth';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 rows=load_inputs(base/'inputs/qa.jsonl');cores={r['qa_id']:r['core'] for r in map(json.loads,(base/'descriptors/core.jsonl').read_text().splitlines())};config={'theme':a.theme,'scope':a.scope,'budget':a.budget,'model':os.environ['XUNXU_MODEL'],'system':SYSTEM,'embedding':METHOD,'input_hash':hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()+(base/'descriptors/core.jsonl').read_bytes()).hexdigest()};checkpoint=out/'checkpoint.json'
 if checkpoint.exists():saved=json.loads(checkpoint.read_text());assert saved['config']==config,'Configuration changed: use separate output directory';state=saved['state'];stats=saved['stats']
 else:state=new_state(a.theme,a.scope);stats={'model_requests':0,'cache_hits':0,'input_tokens':0,'output_tokens':0,'embedding_new':0,'global_queries':0,'steps':[]}
 def vector(r):
  text=r['question']+'\n'+cores[r['qa_id']];key=hashlib.sha256((METHOD+text).encode()).hexdigest();path=cache/(key+'.npy')
  if path.exists():return np.load(path)
  v=np.asarray(local_embedding.encode([text])[0]);np.save(path,v);stats['embedding_new']+=1;return v
 index=OnlineIndex();rowby={r['qa_id']:r for r in rows}
 for key in state['processed']:
  r=rowby[key];index.add(key,r['question']+'\n'+cores[key],vector(r))
 def brief(n):return {k:n[k] for k in ['qa_id','question','core','parent']}
 def ask(payload):
  key=hashlib.sha256((json.dumps(config,ensure_ascii=False)+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():stats['cache_hits']+=1;return json.loads(path.read_text())['decision']
  result=provider_request('chat/completions',{'model':config['model'],'temperature':0.1,'max_tokens':1600,'tools':[{'type':'function','function':{'name':'grow_one','description':'单条增量生长判别','parameters':root_check_schema() if payload['stage']=='global' else SCHEMA}}],'tool_choice':{'type':'function','function':{'name':'grow_one'}},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]});stats['model_requests']+=1;usage=result.get('usage',{});stats['input_tokens']+=usage.get('prompt_tokens',0);stats['output_tokens']+=usage.get('completion_tokens',0);choice=result['choices'][0];assert choice.get('finish_reason')!='length';d=json.loads(choice['message']['tool_calls'][0]['function']['arguments']);path.write_text(json.dumps({'decision':d,'usage':usage},ensure_ascii=False,indent=2));return d
 for i,r in enumerate(rows):
  if r['qa_id'] in state['processed']:continue
  if a.limit and i>=a.limit:break
  start=time.monotonic();by={n['qa_id']:n for n in state['nodes']};prev=rows[i-1] if i else None;anchor=state['assignments'].get(prev['qa_id']) if prev else None;ids=['research-root']
  if anchor:
   ids.append(anchor);parent=by[anchor]['parent']
   if parent:ids.append(parent)
   ids.extend(n['qa_id'] for n in state['nodes'] if n['parent']==anchor or (parent and n['parent']==parent))
  else:ids.extend(n['qa_id'] for n in state['nodes'] if n['parent']=='research-root')
  ids=list(dict.fromkeys(ids))[:16];current={**r,'core':cores[r['qa_id']]};payload={'stage':'local','revision':state['revision'],'root':brief(state['nodes'][0]),'current':{k:current[k] for k in ['qa_id','question','core']},'previous_qa':({'question':prev['question'],'core':cores[prev['qa_id']],'assigned_node':anchor} if prev else None),'conversation_boundary':'未知会话ID，按时间流实验','context':[brief(by[k]) for k in ids]};d=ask(payload);valid=validate(d,payload['current'],payload['context']);v=vector(r);global_used=False
  stats['global_queries']+=1;global_used=True;candidates=index.search(r['question']+'\n'+cores[r['qa_id']],v,a.budget)
  for key in candidates:
   node=state['assignments'].get(key)
   for _ in range(3):
    if not node:break
    ids.append(node);node=by[node]['parent']
  ids=list(dict.fromkeys(ids));payload={**payload,'stage':'global','local_proposal':dict(d),'retrieved_questions':[{'qa_id':k,'question':rowby[k]['question'],'core':cores[k],'assigned_node':state['assignments'].get(k)} for k in candidates],'context':[brief(by[k]) for k in ids]};d=ask(payload);valid=validate(d,payload['current'],payload['context'])
  if global_used and not root_confirmed(d):valid=False
  if d['kind']=='needs_retrieval':d['kind']='uncertain'
  event=commit(state,r,cores[r['qa_id']],d,valid);index.add(r['qa_id'],r['question']+'\n'+cores[r['qa_id']],v);stats['steps'].append({**event,'seconds':time.monotonic()-start,'global_used':global_used,'context_nodes':len(payload['context'])});tmp=out/'checkpoint.tmp';tmp.write_text(json.dumps({'config':config,'state':state,'stats':stats},ensure_ascii=False));tmp.replace(checkpoint);print('Committed',state['revision'],'/',len(rows),event['action'],flush=True)
 report={'attached_qa':len(state['nodes'])-1,'pending_qa':len(state['pending']),'resource_qa':len(state['resources']),'outside_qa':len(state['outside']),'cross_links':0,'processed':len(state['processed']),'model':config['model'],'stats':stats,'database_modified':False,'parent_labels_used_for_prediction':False,'scope_labels_used_for_prediction':False,'existing_nodes_moved':0,'existing_edges_changed':0,'limitations':'Offline chronological stream; true conversation boundaries unknown. Core descriptions prepared earlier; their cost excluded. Retrieval is incremental index with linear historical similarity scan, not ANN.'}
 graph={**state,'report':report};(out/'graph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2));(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='stats'},ensure_ascii=False))
if __name__=='__main__':main()
