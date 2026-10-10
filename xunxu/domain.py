"""XunXu V1.1 local domain: atomic SQLite storage and auditable graph operations."""
from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid

COLLECTIONS = ('spaces','nodes','relations','conversations','qas','thoughts','clusters','refs','runs','events','resources','proposals','audit','transplants','summaries')

class DomainError(ValueError):
    pass

def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex[:16]

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def required(value, name, limit=20000):
    if not isinstance(value,str) or not value.strip():
        raise DomainError(name+'不能为空')
    if len(value)>limit:
        raise DomainError(name+'过长')
    return value.strip()

def lexical_vector(text):
    """Experimental deterministic bigram hashing; deliberately NOT semantic embeddings."""
    text=re.sub(r'\s+','',text.lower())
    v=[0.0]*256
    for token in [text[i:i+2] for i in range(max(0,len(text)-1))]:
        slot=int(hashlib.sha256(token.encode()).hexdigest()[:8],16)%256
        v[slot]+=1
    norm=math.sqrt(sum(x*x for x in v)) or 1
    return [round(x/norm,7) for x in v]

def similarity(a,b):
    return sum(x*y for x,y in zip(a,b))

class Store:
    def __init__(self,path):
        self.path=str(path)
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            for name in COLLECTIONS:
                c.execute(f'CREATE TABLE IF NOT EXISTS {name} (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            c.execute("INSERT OR IGNORE INTO meta VALUES ('revision','0')")
    @contextlib.contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=30)
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()
    def load(self,c):
        return {name:{i:json.loads(body) for i,body in c.execute(f'SELECT id,body FROM {name}')} for name in COLLECTIONS}
    @contextlib.contextmanager
    def tx(self):
        with self.lock,self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            data=self.load(c)
            revision=int(c.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
            yield data,revision
            for name in COLLECTIONS:
                c.execute(f'DELETE FROM {name}')
                c.executemany(f'INSERT INTO {name} VALUES (?,?)',[(i,json.dumps(obj,ensure_ascii=False)) for i,obj in data[name].items()])
            c.execute("UPDATE meta SET value=? WHERE key='revision'",(str(revision+1),))
    def read(self):
        with self.lock,self.connect() as c:
            c.execute('BEGIN')
            return self.load(c)
    def get(self,d,table,id):
        if id not in d[table]:
            raise DomainError('对象不存在：'+table)
        return d[table][id]
    def touch(self,node):
        node['version']+=1
        node['updated_at']=now()
    def log(self,d,operation,detail,space_id=None):
        a={'id':uid('audit'),'operation':operation,'detail':detail,'space_id':space_id,'created_at':now(),'actor':'本地研究者'}
        d['audit'][a['id']]=a
        return a
    def node(self,d,id):
        return self.get(d,'nodes',id)
    def growth_children(self,d,id):
        return [n for n in d['nodes'].values() if not n.get('archived') and (n.get('parent_id')==id or id in n.get('sources',[]))]
    def descendants(self,d,id):
        result=set()
        stack=[id]
        while stack:
            k=stack.pop()
            if k in result: continue
            result.add(k)
            stack.extend(n['id'] for n in self.growth_children(d,k))
        return result
    def ensure_open(self,d,node):
        stack=[node['id']]
        seen=set()
        while stack:
            i=stack.pop()
            if i in seen: continue
            seen.add(i)
            n=self.node(d,i)
            if n.get('archived'): raise DomainError('历史节点不能继续生长')
            if n.get('frozen'): raise DomainError('该节点或祖先分支已冻结，请先解冻')
            if n.get('parent_id'): stack.append(n['parent_id'])
            stack.extend(n.get('sources',[]))
    def _space(self,d,title,goal,origin=None):
        title=required(title,'空间名称',120)
        goal=required(goal,'研究目标')
        sid=uid('space'); nid=uid('node')
        space={'id':sid,'title':title,'goal':goal,'root_id':nid,'created_at':now(),'origin':origin}
        d['spaces'][sid]=space
        n={'id':nid,'space_id':sid,'parent_id':None,'sources':[],'title':title,'kind':'thought','summary':goal,'created_at':now(),'updated_at':now(),'reason':'研究者建立独立研究空间','creation_type':'manual','version':1,'frozen':False,'hidden':False,'archived':False}
        d['nodes'][nid]=n
        self._summary(d,n,goal)
        return space
    def _summary(self,d,n,text):
        obj={'id':uid('summary'),'node_id':n['id'],'space_id':n['space_id'],'text':text,'created_at':now(),'node_version':n['version'],'scope':'direct'}
        d['summaries'][obj['id']]=obj
    def create_space(self,title,goal):
        with self.tx() as (d,r):
            s=self._space(d,title,goal)
            self.log(d,'create_space',{'space_id':s['id']},s['id'])
            return s
    def _new_node(self,d,data,creation_type='manual',evidence=None):
        parent=self.node(d,data['parent_id'])
        self.ensure_open(d,parent)
        sid=data.get('space_id',parent['space_id'])
        if sid!=parent['space_id']: raise DomainError('父节点必须属于当前空间')
        kind=data.get('kind','thought')
        if kind not in ('thought','action'): raise DomainError('未知节点类型')
        n={'id':uid('node'),'space_id':sid,'parent_id':parent['id'],'sources':[],'title':required(data.get('title'),'节点标题',120),'kind':kind,'summary':data.get('summary',''),'created_at':now(),'updated_at':now(),'reason':data.get('reason','研究者主动定义研究方向'),'creation_type':creation_type,'evidence':evidence or [],'version':1,'frozen':False,'hidden':False,'archived':False}
        d['nodes'][n['id']]=n
        self.touch(parent)
        self._summary(d,n,n['summary'])
        return n
    def create_node(self,data):
        with self.tx() as (d,r):
            n=self._new_node(d,data)
            self.log(d,'create_node',{'node_id':n['id'],'reason':n['reason']},n['space_id'])
            return n
    def _context(self,d,id):
        n=self.node(d,id)
        ancestors=[]
        current=n
        seen=set()
        while current.get('parent_id'):
            p=current['parent_id']
            if p in seen: raise DomainError('研究图存在循环')
            seen.add(p)
            current=self.node(d,p)
            ancestors.append({'id':current['id'],'title':current['title'],'summary':current['summary'],'version':current['version']})
        ancestors.reverse()
        sources=n.get('source_context',[])
        nutrition=next((t['context_md'] for t in d['transplants'].values() if t['new_space_id']==n['space_id']),None)
        return {'node_id':id,'direct':n['summary'],'ancestors':ancestors,'sources':sources,'nutrition':nutrition,'scope':'祖先路径＋当前节点；不包含子孙研究成果'}
    def context(self,id): return self._context(self.read(),id)
    def create_conversation(self,data):
        with self.tx() as (d,r):
            n=self.node(d,data['node_id']); self.ensure_open(d,n)
            c={'id':uid('conv'),'space_id':n['space_id'],'anchor_id':n['id'],'title':data.get('title') or n['title']+' · 研究会话','created_at':now(),'context_snapshot':self._context(d,n['id'])}
            d['conversations'][c['id']]=c
            self.log(d,'create_conversation',{'conversation_id':c['id'],'anchor_id':n['id']},n['space_id'])
            return c
    def _ref(self,d,node_id,qa_id,thought_id,strength='weak'):
        existing=next((x for x in d['refs'].values() if x['node_id']==node_id and x['thought_id']==thought_id),None)
        if existing: return existing
        ref={'id':uid('ref'),'space_id':self.node(d,node_id)['space_id'],'node_id':node_id,'qa_id':qa_id,'thought_id':thought_id,'strength':strength,'created_at':now()}
        d['refs'][ref['id']]=ref
        return ref
    def add_qa(self,data):
        with self.tx() as (d,r):
            conv=self.get(d,'conversations',data['conversation_id'])
            anchor=self.node(d,conv['anchor_id']); self.ensure_open(d,anchor)
            q=required(data.get('question'),'问题')
            a=required(data.get('answer'),'回答')
            request_id=data.get('request_id')
            if request_id:
                old=next((x for x in d['qas'].values() if x.get('request_id')==request_id and x['conversation_id']==conv['id']),None)
                if old:return {'qa':old,'created_nodes':[],'idempotent':True}
            qa={'id':uid('qa'),'conversation_id':conv['id'],'space_id':conv['space_id'],'title':data.get('title') or q[:48],'question':q,'answer':a,'created_at':now(),'user_message_id':uid('msg'),'answer_message_id':uid('msg'),'request_id':request_id,'mode':data.get('mode','manual')}
            d['qas'][qa['id']]=qa
            specs=data.get('thoughts') or [{'text':q,'topic':data.get('topic') or q[:40],'node_id':data.get('node_id',anchor['id'])}]
            if not isinstance(specs,list) or not 1<=len(specs)<=8: raise DomainError('思想坐标数量应为 1～8')
            created=[]
            for i,spec in enumerate(specs):
                text=required(spec.get('text'),'思想描述')
                # A coordinate is a textual thought, linked to the whole immutable QA plus exact excerpts.
                excerpt=spec.get('excerpt','')
                if excerpt and excerpt not in q and excerpt not in a: raise DomainError('引用片段必须来自原始问答')
                topic=spec.get('topic') or text[:40]
                destination=self.node(d,spec.get('node_id',anchor['id']))
                if destination['space_id']!=anchor['space_id']:raise DomainError('思想不能自动进入其他研究空间')
                th={'id':uid('thought'),'qa_id':qa['id'],'space_id':anchor['space_id'],'role':'main' if i==0 else 'auxiliary','text':text,'topic':topic,'excerpt':excerpt,'original_vector':lexical_vector(text),'working_vector':lexical_vector(text),'vector_method':'experimental-lexical-hash-256','created_at':now()}
                d['thoughts'][th['id']]=th
                try:
                    self.ensure_open(d,destination)
                except DomainError:
                    rel={'id':uid('relation'),'space_id':anchor['space_id'],'source_id':anchor['id'],'target_id':destination['id'],'qa_id':qa['id'],'thought_id':th['id'],'type':'external_reference','created_at':now()}
                    d['relations'][rel['id']]=rel
                    continue
                self._ref(d,destination['id'],qa['id'],th['id'])
                # Explicit research intent labels drive deterministic clustering; vector similarity is diagnostic only.
                cluster=next((c for c in d['clusters'].values() if c['space_id']==anchor['space_id'] and c['anchor_id']==destination['id'] and c['topic']==topic),None)
                if not cluster:
                    cluster={'id':uid('cluster'),'space_id':anchor['space_id'],'anchor_id':destination['id'],'topic':topic,'members':[],'node_id':None,'version':0}
                    d['clusters'][cluster['id']]=cluster
                cluster['members'].append(th['id']);cluster['version']+=1
                unique_qas={d['thoughts'][x]['qa_id'] for x in cluster['members']}
                existing=next((n for n in d['nodes'].values() if n['space_id']==anchor['space_id'] and n['title']==topic and not n['archived'] and (n['id']==destination['id'] or n.get('parent_id')==destination['id'])),None)
                if existing and not cluster['node_id']: cluster['node_id']=existing['id']
                try: self.ensure_open(d,destination)
                except DomainError: continue # evidence remains external; frozen nodes never receive growth
                if (len(unique_qas)>=2 or spec.get('novel') is True) and not cluster['node_id']:
                    n=self._new_node(d,{'parent_id':destination['id'],'title':topic,'summary':text,'reason':('人工标记独立新思想' if spec.get('novel') else '至少两个独立问答具有相同明确研究意图标签')+'；触发簇 '+cluster['id']},'new_thought' if spec.get('novel') else 'cluster',cluster['members'][:])
                    cluster['node_id']=n['id'];created.append(n)
                if cluster['node_id']:
                    target=self.node(d,cluster['node_id'])
                    try:self.ensure_open(d,target)
                    except DomainError:continue
                    for ti in cluster['members']:
                        ref=self._ref(d,target['id'],d['thoughts'][ti]['qa_id'],ti,'strong')
                        ref['strength']='strong'
                # No descendant results ever roll up into ancestor summaries.
            self.log(d,'add_qa',{'qa_id':qa['id'],'created_node_ids':[n['id'] for n in created],'mode':qa['mode']},anchor['space_id'])
            return {'qa':qa,'created_nodes':created}
    def _fingerprint(self,d,space_id):
        fields=[{k:n.get(k) for k in ('id','version','parent_id','sources','frozen','hidden','archived','space_id')} for n in d['nodes'].values() if n['space_id']==space_id]
        return hashlib.sha256(json.dumps(sorted(fields,key=lambda x:x['id']),sort_keys=True).encode()).hexdigest()
    def _nutrient(self,d,node):
        path=self._context(d,node['id'])['ancestors']+[{'id':node['id'],'title':node['title'],'summary':node['summary'],'version':node['version']}]
        lines=['# '+node['title']+' · 移植研究背景','','来源空间：'+d['spaces'][node['space_id']]['title'],'来源空间 ID：'+node['space_id'],'来源分支 ID：'+node['id'],'快照时间：'+now(),'','## 祖先路径与必要背景']
        for p in path: lines+=['','### '+p['title'],'节点 ID：'+p['id']+'；版本：'+str(p['version']),p['summary'] or '尚未记录直接研究总结。']
        if node.get('source_context'):
            lines+=['','## 已批准的汇合来源背景',json.dumps(node['source_context'],ensure_ascii=False,indent=2)]
        lines+=['','## 新树研究目标',node['summary'] or node['title'],'','## 发展指引','围绕上述目标继续明确问题、补充证据或开展实验。此段为一般性指引，非已验证结论。','','## 知识边界','仅继承祖先路径必要背景与被移植子树资料；不包含原树兄弟分支。后代成果仍留在后代节点，不自动进入新根总结。','','## 原始证据索引']
        for ref in d['refs'].values():
            if ref['node_id'] in self.descendants(d,node['id']):
                lines+=['- '+ref['qa_id']+' / '+ref['thought_id']]
        return '\n'.join(lines)+'\n'
    def _validate(self,d,p):
        op=p['operation']; node=self.node(d,p['node_id']); sid=node['space_id']
        if node['archived']:raise DomainError('不能操作已归档的历史身份')
        root=d['spaces'][sid]['root_id']
        target=self.node(d,p['target_id']) if p.get('target_id') else None
        if target and (target['space_id']!=sid or target['archived']):raise DomainError('目标必须是同空间有效节点')
        if op in ('move','merge','transplant','hide') and node['id']==root:raise DomainError('根节点不可移动、合并、隐藏或剪出')
        if op=='move':
            if not target:raise DomainError('请选择目标父节点')
            if node.get('sources'):raise DomainError('共同分支不能改成普通子节点')
            if target['id'] in self.descendants(d,node['id']):raise DomainError('移动会形成循环')
            self.ensure_open(d,target)
        if op=='merge':
            if not target or target['id']==node['id']:raise DomainError('请选择另一个叶子节点')
            if self.growth_children(d,node['id']) or self.growth_children(d,target['id']):raise DomainError('仅允许末端叶子合并，中间节点请建立共同分支')
            if node.get('sources') or target.get('sources'):raise DomainError('本版不合并具有汇合来源的节点，使用新共同分支')
            if node['parent_id']!=target['parent_id']:raise DomainError('跨父节点合并需明确归属，本版请先审核移动或创建共同分支')
            self.ensure_open(d,node);self.ensure_open(d,target)
        if op=='confluence':
            sources=p.get('sources',[])
            if len(set(sources)) not in (2,3) or len(sources)!=len(set(sources)):raise DomainError('共同分支需要 2～3 个不同核心来源')
            for i in sources:
                n=self.node(d,i)
                if n['space_id']!=sid:raise DomainError('共同分支来源必须在同一空间')
                self.ensure_open(d,n)
        if op=='transplant':
            subtree=self.descendants(d,node['id'])
            for nid in subtree:
                n=self.node(d,nid)
                if any(src not in subtree for src in n.get('sources',[])):raise DomainError('汇合来源跨越移植边界，请先明确来源准入；本版拒绝不完整移植')
            if any(run['node_id'] in subtree and run['status'] not in ('completed','failed','cancelled') for run in d['runs'].values()):raise DomainError('存在未结束的 Run，请等待完成或人工结束后移植')
        if op not in ('freeze','unfreeze','hide','restore','move','merge','confluence','transplant','coordinate_move'):raise DomainError('未知结构操作')
        if op=='coordinate_move':
            th=self.get(d,'thoughts',p.get('thought_id'))
            if th['space_id']!=sid:raise DomainError('坐标不属于当前空间')
            vector=p.get('vector')
            if not isinstance(vector,list) or len(vector)!=256 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in vector):raise DomainError('工作坐标需要 256 维有限数值')
    def propose(self,data):
        with self.tx() as (d,r):
            node=self.node(d,data['node_id'])
            p={k:data[k] for k in ('operation','node_id','target_id','sources','title','thought_id','vector') if k in data}
            p.update({'id':uid('proposal'),'space_id':node['space_id'],'reason':required(data.get('reason'),'操作原因'),'status':'pending','created_at':now(),'fingerprint':self._fingerprint(d,node['space_id'])})
            self._validate(d,p)
            subtree=self.descendants(d,node['id'])
            p['preview']={'before':{'title':node['title'],'parent_id':node['parent_id'],'sources':node.get('sources',[]),'summary':node['summary']},'after':{'operation':p['operation'],'target_id':p.get('target_id'),'sources':p.get('sources'),'title':p.get('title')},'affected_nodes':[{'id':i,'title':d['nodes'][i]['title']} for i in sorted(subtree)],'context_before':self._context(d,node['id']),'history':'原始问答、会话锚点与节点历史永久保留'}
            if p.get('target_id'):p['preview']['target_context']=self._context(d,p['target_id'])
            if p['operation']=='confluence':p['preview']['source_context']=[{'id':i,'title':self.node(d,i)['title'],'context':self._context(d,i)} for i in p['sources']]
            if p['operation']=='transplant':p['preview']['context_md']=self._nutrient(d,node)
            if p['operation']=='coordinate_move':p['preview'].update({'before_vector':d['thoughts'][p['thought_id']]['working_vector'],'after_vector':p['vector']})
            d['proposals'][p['id']]=p
            return p
    def reject(self,id):
        with self.tx() as (d,r):
            p=self.get(d,'proposals',id)
            if p['status']!='pending':raise DomainError('建议已经处理')
            p['status']='rejected';p['decided_at']=now()
            self.log(d,'reject',{'proposal_id':id},p['space_id'])
            return p
    def approve(self,id):
        with self.tx() as (d,r):
            p=self.get(d,'proposals',id)
            if p['status']=='approved':return p
            if p['status']!='pending':raise DomainError('建议不是待审核状态')
            if self._fingerprint(d,p['space_id'])!=p['fingerprint']:raise DomainError('研究结构已变化，请重新生成预览后审核')
            self._validate(d,p)
            before={name:json.loads(json.dumps(d[name])) for name in COLLECTIONS if name!='audit'}
            node=self.node(d,p['node_id']);op=p['operation'];subtree=self.descendants(d,node['id'])
            if op in ('freeze','unfreeze','hide','restore'):
                field='frozen' if op in ('freeze','unfreeze') else 'hidden'
                for nid in subtree:
                    d['nodes'][nid][field]=op in ('freeze','hide');self.touch(d['nodes'][nid])
            elif op=='move':
                node['parent_id']=p['target_id'];self.touch(node)
            elif op=='coordinate_move':
                th=d['thoughts'][p['thought_id']]
                th.setdefault('vector_history',[]).append({'vector':th['working_vector'],'at':now(),'proposal_id':id})
                th['working_vector']=p['vector'];self.touch(node)
            elif op=='merge':
                other=self.node(d,p['target_id'])
                n=self._new_node(d,{'parent_id':node['parent_id'],'title':p.get('title') or node['title']+' / '+other['title'],'kind':node['kind'],'summary':node['summary']+'\n\n'+other['summary'],'reason':p['reason']},'approved_merge',[node['id'],other['id']])
                n['merged_from']=[node['id'],other['id']]
                for old in (node,other):old['archived']=True;old['merged_into']=n['id'];self.touch(old)
                for ref in list(d['refs'].values()):
                    if ref['node_id'] in n['merged_from']:self._ref(d,n['id'],ref['qa_id'],ref['thought_id'],ref['strength'])
                p['result_node_id']=n['id']
            elif op=='confluence':
                n={'id':uid('node'),'space_id':node['space_id'],'parent_id':None,'sources':p['sources'],'source_context':p['preview']['source_context'],'title':required(p.get('title'),'共同分支标题',120),'summary':p['reason'],'kind':'thought','reason':p['reason'],'creation_type':'approved_confluence','evidence':p['sources'],'created_at':now(),'version':1,'frozen':False,'hidden':False,'archived':False}
                d['nodes'][n['id']]=n
                for src in p['sources']:
                    rel={'id':uid('relation'),'space_id':node['space_id'],'source_id':src,'target_id':n['id'],'type':'confluence','created_at':now()}
                    d['relations'][rel['id']]=rel
                    self.touch(self.node(d,src))
                self._summary(d,n,n['summary']);p['result_node_id']=n['id']
            elif op=='transplant':
                old_space=node['space_id'];old_parent=node['parent_id'];newid=uid('space');tid=uid('transplant')
                t={'id':tid,'source_space_id':old_space,'source_node_id':node['id'],'source_parent_id':old_parent,'new_space_id':newid,'root_id':node['id'],'node_ids':sorted(subtree),'context_md':p['preview']['context_md'],'created_at':now(),'reason':p['reason'],'proposal_id':id,'source_path':p['preview']['context_before']['ancestors']}
                d['transplants'][tid]=t
                d['spaces'][newid]={'id':newid,'root_id':node['id'],'title':p.get('title') or node['title'],'goal':node['summary'],'created_at':now(),'origin':tid}
                for nid in subtree:
                    n=d['nodes'][nid];n['space_id']=newid;self.touch(n)
                node['parent_id']=None
                # Immutable original QAs / conversation anchors / thought birth-space remain unchanged.
                for ref in d['refs'].values():
                    if ref['node_id'] in subtree:ref['space_id']=newid
                for name in ('runs','resources'):
                    for obj in d[name].values():
                        if obj['node_id'] in subtree:obj['space_id']=newid
                for rel in d['relations'].values():
                    if rel['target_id'] in subtree and rel['source_id'] in subtree:rel['space_id']=newid
                # Move eligible cluster workspaces while preserving members' source QA identities.
                for cluster in d['clusters'].values():
                    if cluster['anchor_id'] in subtree:cluster['space_id']=newid
                p['result_space_id']=newid;p['transplant_id']=tid
            p['status']='approved';p['decided_at']=now();p['actor']='本地研究者'
            record=self.log(d,op,{'proposal_id':id,'node_id':node['id'],'reason':p['reason']},p['space_id'])
            record['undo_snapshot']=before;record['commit_revision']=r+1
            return p
    def undo(self,id):
        with self.tx() as (d,r):
            a=self.get(d,'audit',id)
            if not a.get('undo_snapshot'):raise DomainError('该记录不支持结构撤销')
            if a['commit_revision']!=r:raise DomainError('操作后已有新研究记录，请人工处理差异；不能用旧快照覆盖新增研究')
            snapshot=a['undo_snapshot']
            for name,rows in snapshot.items():d[name]=rows
            self.log(d,'undo',{'audit_id':id},a.get('space_id'))
            return {'ok':True}
    def create_run(self,data):
        with self.tx() as (d,r):
            n=self.node(d,data['node_id']);self.ensure_open(d,n)
            if n['kind']!='action':raise DomainError('请在行动节点上创建 Run')
            retry=data.get('retry_of')
            if retry and self.get(d,'runs',retry)['node_id']!=n['id']:raise DomainError('重试必须属于同一实验')
            run={'id':uid('run'),'node_id':n['id'],'space_id':n['space_id'],'device':data.get('device') or '人工执行端','parameters':data.get('parameters') or {},'design_snapshot':{'title':n['title'],'summary':n['summary'],'version':n['version']},'context_snapshot':self._context(d,n['id']),'status':'pending','created_at':now(),'retry_of':retry,'execution_mode':'manual_report','result':None}
            d['runs'][run['id']]=run;self.touch(n)
            self.log(d,'create_run',{'run_id':run['id'],'node_id':n['id']},n['space_id'])
            return run
    def report_event(self,run_id,data):
        with self.tx() as (d,r):
            run=self.get(d,'runs',run_id)
            eid=required(data.get('event_id'),'事件 ID',200)
            old=next((e for e in d['events'].values() if e['run_id']==run_id and e['event_id']==eid),None)
            if old:return old
            status=data.get('status',run['status'])
            allowed={'pending':{'pending','dispatched','running','failed','cancelled'},'dispatched':{'dispatched','running','failed','cancelled'},'running':{'running','paused','returning','failed','cancelled'},'paused':{'paused','running','failed','cancelled'},'returning':{'returning','verifying','failed'},'verifying':{'verifying','completed','failed'},'completed':{'completed'},'failed':{'failed'},'cancelled':{'cancelled'}}
            if status not in allowed.get(run['status'],set()):raise DomainError('不允许的运行状态转移：'+run['status']+' → '+str(status))
            sequence=data.get('sequence',max((e.get('sequence',0) for e in d['events'].values() if e['run_id']==run_id),default=0)+1)
            if not isinstance(sequence,int) or sequence<=0:raise DomainError('事件序号必须为正整数')
            if sequence<=run.get('last_sequence',0):raise DomainError('事件序号已经过期或乱序')
            e={'id':uid('event'),'event_id':eid,'run_id':run_id,'node_id':run['node_id'],'space_id':run['space_id'],'sequence':sequence,'message':data.get('message',''),'status':status,'created_at':now(),'result':data.get('result')}
            d['events'][e['id']]=e;run['status']=status;run['last_sequence']=sequence;run['updated_at']=now()
            if 'result' in data:run['result']=data['result']
            self.log(d,'run_event',{'run_id':run_id,'event_id':eid,'status':status},run['space_id'])
            return e
    def add_resource(self,data):
        with self.tx() as (d,r):
            n=self.node(d,data['node_id']);self.ensure_open(d,n)
            url=data.get('url','')
            if url and not re.match(r'^(https?://|/)',url):raise DomainError('资源地址须为 HTTP(S) 或绝对文件路径')
            res={'id':uid('resource'),'node_id':n['id'],'space_id':n['space_id'],'title':required(data.get('title'),'资源标题',200),'url':url,'type':data.get('type','document'),'created_at':now()}
            d['resources'][res['id']]=res;self.touch(n)
            self.log(d,'add_resource',{'resource_id':res['id']},n['space_id'])
            return res
    def state(self,space_id=None):
        d=self.read()
        spaces=list(d['spaces'].values())
        space_id=space_id or (spaces[0]['id'] if spaces else None)
        if space_id and space_id not in d['spaces']:raise DomainError('研究空间不存在')
        nodes=[n for n in d['nodes'].values() if n['space_id']==space_id]
        ids={n['id'] for n in nodes}
        refs=[r for r in d['refs'].values() if r['node_id'] in ids]
        qaids={r['qa_id'] for r in refs}
        # Include all original messages of local anchored conversations only when origin remains this space.
        conversations=[c for c in d['conversations'].values() if c['anchor_id'] in ids or any(d['qas'][q]['conversation_id']==c['id'] for q in qaids)]
        conv_ids={c['id'] for c in conversations if c['space_id']==space_id and c['anchor_id'] in ids}
        qas=[q for q in d['qas'].values() if q['id'] in qaids or q['conversation_id'] in conv_ids]
        output={'spaces':spaces,'space_id':space_id,'nodes':nodes,'conversations':conversations,'qas':qas,'refs':refs}
        for name in COLLECTIONS:
            if name not in output:
                output[name]=[o for o in d[name].values() if o.get('space_id')==space_id]
        thought_ids={ref['thought_id'] for ref in refs}
        output['thoughts']=[t for t in d['thoughts'].values() if t['space_id']==space_id or t['id'] in thought_ids]
        output['events']=[e for e in d['events'].values() if e['node_id'] in ids]
        output['transplants']=[t for t in d['transplants'].values() if space_id in (t['source_space_id'],t['new_space_id'])]
        output['audit']=[{k:v for k,v in a.items() if k!='undo_snapshot'} for a in d['audit'].values() if a.get('space_id')==space_id]
        output['metrics']=self.metrics(d,space_id)
        output['provider']={'configured':all(os.environ.get(x) for x in ('XUNXU_API_KEY','XUNXU_API_BASE','XUNXU_MODEL')),'model':os.environ.get('XUNXU_MODEL',''),'base_url':os.environ.get('XUNXU_API_BASE',''),'growth_mode':'明确研究意图标签聚类＋实验性词面坐标','remote_execution':'人工回报模式，设备 Agent 尚未接入'}
        return output
    def metrics(self,d,sid):
        nodes={n['id']:n for n in d['nodes'].values() if n['space_id']==sid and not n['archived']}
        depths={}
        def depth(i,visited=None):
            if i in depths:return depths[i]
            visited=(visited or set())|{i}
            n=nodes[i];parents=([n['parent_id']] if n.get('parent_id') else [])+n.get('sources',[])
            if any(p in visited for p in parents):raise DomainError('研究图存在循环')
            depths[i]=1+max((depth(p,visited) for p in parents if p in nodes),default=-1)
            return depths[i]
        for i in nodes:depth(i)
        layers={}
        for level in depths.values():layers[level]=layers.get(level,0)+1
        h=max(depths.values(),default=0);w=max(layers.values(),default=0)
        return {'nodes':len(nodes),'depth':h,'width':w,'width_depth_ratio':round(w/max(h,1),2),'layers':layers,'hidden':sum(n['hidden'] for n in nodes.values()),'frozen':sum(n['frozen'] for n in nodes.values())}
    def seed(self):
        if self.read()['spaces']:return
        space=self.create_space('循序 · 系统构建','以真实科研活动驱动研究树生长，保留思想来源与独立上下文。以下为可操作的示例空间，可另建你的真实研究空间。')
        root=space['root_id']
        a=self.create_node({'parent_id':root,'title':'思想坐标与自动生长','summary':'问答证据唯一，一主多辅思想坐标；有效新簇生成节点，既有簇扩张补充证据。'})
        b=self.create_node({'parent_id':root,'title':'研究空间与独立移植','summary':'祖先路径营养包、完整子树资料与新空间独立生长分开。'})
        c=self.create_node({'parent_id':root,'title':'跨设备实验验证','kind':'action','summary':'实验节点承载目的与设计，每次执行拥有独立 Run，结果不反写祖先。'})
        self.create_node({'parent_id':a['id'],'title':'问答证据与精确溯源','summary':'每个问答有标题和原始消息定位标识，会话锚点永久保留。'})
        self.create_node({'parent_id':a['id'],'title':'节点去重与证据强化','summary':'已被承载的簇不重复生成节点，新增证据按明确研究意图关联。'})
        self.create_node({'parent_id':b['id'],'title':'祖先路径营养包','summary':'沿原根至裁剪节点提取背景，不纳入兄弟分支结论。'})
        conv=self.create_conversation({'node_id':a['id'],'title':'示例 · 研究组织规则'})
        self.add_qa({'conversation_id':conv['id'],'question':'如何保留研究过程中的独立思想？','answer':'完整问答保留为证据，独立思想可形成研究节点并保存来源；此条是系统内置示例，非实时模型回复。','thoughts':[{'text':'思想证据保持唯一','topic':'思想坐标与自动生长','node_id':a['id']}]})
