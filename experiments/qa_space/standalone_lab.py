"""Local-only interactive lab. Private state and keys never enter browser responses."""
import json,os,sys,threading,uuid,time
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.middleware.cors import CORSMiddleware
from incremental_growth import new_state,commit,validate,OnlineIndex,SYSTEM,SCHEMA,ROOT,needs_space_check,root_check_schema,root_confirmed
from main import provider_request
from embeddings import local_embedding
import numpy as np
for line in (ROOT/'ai-engine/.env').read_text().splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1)
  if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
OUT=ROOT/'.runtime/standalone-lab';OUT.mkdir(exist_ok=True);FILE=OUT/'state.json';LOCK=threading.RLock();app=FastAPI();app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5174','http://localhost:5174'],allow_methods=['GET','POST'],allow_headers=['Content-Type'])
@app.middleware('http')
async def local_only(request:Request,call_next):
 if request.url.hostname not in ['127.0.0.1','localhost']:return HTMLResponse('Host rejected',403)
 origin=request.headers.get('origin')
 if request.method=='POST' and origin and origin not in ['http://127.0.0.1:5174','http://localhost:5174']:return HTMLResponse('Origin rejected',403)
 return await call_next(request)
def load():return json.loads(FILE.read_text()) if FILE.exists() else {'workspaces':{},'active':None}
def save(db):
 tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(db,ensure_ascii=False));tmp.replace(FILE);FILE.chmod(0o600)
def public(w):return {k:v for k,v in w.items() if k!='vectors'}
def workspace(db):
 if not db['active']:raise HTTPException(400,'请先新建研究空间')
 return db['workspaces'][db['active']]
@app.get('/lab/state')
def state():
 with LOCK:
  db=load();return {'workspaces':[{'id':k,'theme':w['theme']} for k,w in db['workspaces'].items()],'active':db['active'],'workspace':public(workspace(db)) if db['active'] else None}
@app.post('/lab/workspaces')
def create(d:dict):
 with LOCK:
  db=load();key=uuid.uuid4().hex;theme=str(d.get('theme','')).strip();scope=str(d.get('scope',theme)).strip()
  if not theme:raise HTTPException(400,'请填写根主题')
  db['workspaces'][key]={'id':key,'theme':theme,'scope':scope,'graph':new_state(theme,scope),'qas':[],'conversations':[],'vectors':{}};db['active']=key;save(db);return {'id':key}
@app.post('/lab/activate')
def activate(d:dict):
 with LOCK:
  db=load()
  if d.get('id') not in db['workspaces']:raise HTTPException(404,'研究空间不存在')
  db['active']=d['id'];save(db);return {'ok':True}
@app.post('/lab/conversations')
def conversation(d:dict):
 with LOCK:
  db=load();w=workspace(db);anchor=d.get('anchor','research-root')
  if anchor not in {n['qa_id'] for n in w['graph']['nodes']}:raise HTTPException(400,'请选择当前树节点')
  c={'id':uuid.uuid4().hex,'anchor':anchor,'title':str(d.get('title') or '新会话')};w['conversations'].append(c);save(db);return c

def model(schema,name,system,payload,max_tokens):
 result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':max_tokens,'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],'tools':[{'type':'function','function':{'name':name,'description':name,'parameters':schema}}],'tool_choice':{'type':'function','function':{'name':name}}});c=result['choices'][0]
 if c.get('finish_reason')=='length':raise ValueError('模型结果被截断')
 return json.loads(c['message']['tool_calls'][0]['function']['arguments'])
@app.post('/lab/turn')
def turn(d:dict):
 with LOCK:
  db=load();w=workspace(db);g=w['graph'];c=next((c for c in w['conversations'] if c['id']==d.get('conversation_id')),None)
  if not c:raise HTTPException(400,'先新建会话')
  request_id=d.get('request_id')
  if not isinstance(request_id,str) or not request_id:raise HTTPException(400,'缺少请求标识')
  existing=next((q for q in w['qas'] if q.get('request_id')==request_id and q['conversation_id']==c['id']),None)
  if existing and existing['question']!=str(d.get('question','')).strip():raise HTTPException(409,'同一请求标识不能用于不同问题')
  if existing and existing["status"] not in ["growth_failed","saved"]:return existing
  question=str(d.get('question','')).strip()
  if not question or len(question)>12000:raise HTTPException(400,'问题不能为空或过长')
  history=[q for q in w['qas'] if q['conversation_id']==c['id'] and (not existing or q['qa_id']!=existing['qa_id'])];by={n['qa_id']:n for n in g['nodes']};anchor=g['assignments'].get(history[-1]['qa_id'],c['anchor']) if history else c['anchor']
  schema={'type':'object','required':['answer','core'],'additionalProperties':False,'properties':{'answer':{'type':'string'},'core':{'type':'string','minLength':70,'maxLength':100,'description':'70至100字，目标约80字'}}}
  try:a={'answer':existing['answer'],'core':existing['core']} if existing else model(schema,'answer_and_core','你是科研助手。依据根主题、当前节点与本会话历史回答当前问题；同时生成约80字核心内容描述，准确概括问答的研究目标和条件。answer可使用Markdown，core不包含格式编号。',{'theme':w['theme'],'scope':w['scope'],'node':by[anchor],'history':[{'question':q['question'],'answer':q['answer']} for q in history],'question':question},8192)
  except Exception:raise HTTPException(502,'回答生成失败，输入未提交，可以重试')
  if not all(isinstance(a.get(k),str) and a[k].strip() for k in ['answer','core']):raise HTTPException(502,'回答格式不合法')
  q=existing or {'qa_id':uuid.uuid4().hex,'id':'','sequence':len(w['qas'])+1,'question':question,'answer':a['answer'],'core':a['core'],'conversation_id':c['id'],'request_id':request_id,'status':'saved'};q['id']='问答 '+str(q['sequence']);
  if not existing:w['qas'].append(q)
  save(db)
  try:
   v=np.asarray(local_embedding.encode([question+'\n'+q['core']])[0]);w['vectors'][q['qa_id']]=v.tolist();ids=['research-root',anchor];parent=by[anchor]['parent']
   if parent:ids.append(parent)
   ids.extend(n['qa_id'] for n in g['nodes'] if n['parent']==anchor or (parent and n['parent']==parent));ids=list(dict.fromkeys(ids))[:16]
   brief=lambda n:{k:n[k] for k in ['qa_id','question','core','parent']}
   payload={'stage':'local','root':brief(g['nodes'][0]),'current':{k:q[k] for k in ['qa_id','question','core']},'context':[brief(by[k]) for k in ids],'previous_qa':history[-1] if history else None,'conversation_boundary':'真实会话ID '+c['id']};decision=model(SCHEMA,'grow_one',SYSTEM,payload,1600);valid=validate(decision,q,payload['context'])
   q['growth_trace']={'local_decision':dict(decision),'space_retrieval':False}
   if needs_space_check(decision,valid):
    index=OnlineIndex()
    for old in w['qas']:
     if old['qa_id']==q['qa_id']:continue
     if old['qa_id'] in w['vectors']:index.add(old['qa_id'],old['question']+'\n'+old['core'],np.array(w['vectors'][old['qa_id']]))
    hits=index.search(question+'\n'+q['core'],v,10)
    for key in hits:
     node=g['assignments'].get(key)
     for _ in range(3):
      if not node:break
      ids.append(node);node=by[node]['parent']
    q['growth_trace'].update(space_retrieval=True,retrieved_qa_ids=hits)
    ids=list(dict.fromkeys(ids))[:50];q['growth_trace']['candidate_node_ids']=ids;payload.update(stage='global',context=[brief(by[k]) for k in ids],retrieved_questions=[{k:old[k] for k in ['qa_id','question','core']} for old in w['qas'] if old['qa_id'] in hits]);decision=model(root_check_schema(),'grow_one',SYSTEM,payload,1600);valid=validate(decision,q,payload['context']) and root_confirmed(decision)
   g['pending']=[r for r in g['pending'] if r['qa_id']!=q['qa_id']];event=commit(g,q,q['core'],decision,valid);q['status']=event['action'];q['decision']=decision
  except Exception:
   q['status']='growth_failed';q['reason']='回答已保存；生长失败，可以单独重试。'
   if not any(r['qa_id']==q['qa_id'] for r in g['pending']):g['pending'].append({**q,'storage_anchor':None,'status':'待判定','proposal':{}})
  save(db);return q
@app.post('/lab/retry')
def retry(d:dict):
 with LOCK:
  w=workspace(load());q=next((q for q in w['qas'] if q['qa_id']==d.get('qa_id')),None)
  if not q:raise HTTPException(404,'问答不存在')
  return turn({'question':q['question'],'request_id':q['request_id'],'conversation_id':q['conversation_id']})
@app.get('/research-tree-incremental.html',response_class=HTMLResponse)
def page():
 import re
 source=(ROOT/'.runtime/exports/research-tree-incremental.html').read_text()
 with LOCK:
  db=load()
  if db['active']:
   w=workspace(db);g=w['graph'];g={**g,'pending_records':g['pending'],'source_records':[],'report':{'processed':len(w['qas'])}}
   source=re.sub(r'(<script type="application/json" id="data">).*?(</script>)',lambda m:m[1]+json.dumps(g,ensure_ascii=False).replace('</','<\\/')+m[2],source,count=1,flags=re.S)
   source=re.sub(r'<div class="meta">逐条提交.*?</div>',f'<div class="meta">交互实验 · {len(w["qas"])} 问答 · {len(g["nodes"])-1} 分支节点 · 根主题 {w["theme"]}</div>',source,count=1)
   source=re.sub(r'<p style="padding:10px;background:#fff1de.*?</p>','<p>交互实验：判别仍需复核；新问答只追加节点或资源，旧坐标和父边保持。</p>',source,count=1,flags=re.S)
 if db['active'] and w['qas']:
  latest=w['qas'][-1]['qa_id'];focus=g['assignments'].get(latest)
  if focus:source=source.replace('new ResizeObserver(()=>', 'selected='+json.dumps(focus)+';reveal(selected);new ResizeObserver(()=>',1)
 script=(Path(__file__).parent/'standalone_lab_ui.js').read_text();source=source.replace('</body>', '<script>'+script+'</script></body>');return source
@app.get('/{path:path}')
def files(path:str):
 file=(ROOT/'.runtime/exports'/path).resolve();base=(ROOT/'.runtime/exports').resolve()
 if not file.is_relative_to(base) or not file.is_file():raise HTTPException(404)
 return FileResponse(file)
