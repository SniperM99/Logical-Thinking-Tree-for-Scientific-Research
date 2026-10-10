"""Prototype protocol validator. Production writes belong to the Java core."""
import hashlib
import secrets
from .domain import DomainError, now, uid, required

class RemoteExecutor:
    def __init__(self, store): self.store=store
    def _auth(self,d,data):
        device=self.store.get(d,'devices',data.get('device_id'))
        supplied=hashlib.sha256(str(data.get('device_token','')).encode()).hexdigest()
        if not secrets.compare_digest(supplied,device['token_hash']): raise DomainError('设备认证失败')
        return device
    def register_device(self,data):
        token=secrets.token_urlsafe(32)
        with self.store.tx() as (d,r):
            obj={'id':uid('device'),'name':required(data.get('name'),'设备名称',120),'workspace':required(data.get('workspace'),'工作目录',2000),'token_hash':hashlib.sha256(token.encode()).hexdigest(),'created_at':now(),'last_seen':now()}
            d['devices'][obj['id']]=obj
            self.store.log(d,'register_device',{'device_id':obj['id']})
            return {'device_id':obj['id'],'device_token':token}
    def devices(self): return [{k:v for k,v in x.items() if k!='token_hash'} for x in self.store.read()['devices'].values()]
    def heartbeat(self,data):
        with self.store.tx() as (d,r):
            device=self._auth(d,data);device['last_seen']=now()
            return {'ok':True}
    def dispatch(self,run_id,data):
        argv=data.get('argv')
        if not isinstance(argv,list) or not argv or len(argv)>128 or not all(isinstance(s,str) and s and len(s)<10000 for s in argv): raise DomainError('命令必须为非空参数列表')
        cwd=data.get('cwd','.')
        from pathlib import PurePosixPath
        if not isinstance(cwd,str) or PurePosixPath(cwd).is_absolute() or '..' in PurePosixPath(cwd).parts: raise DomainError('执行目录必须位于设备工作目录内')
        timeout=data.get('timeout_seconds',300)
        if not isinstance(timeout,int) or not 1<=timeout<=86400: raise DomainError('执行超时须为 1～86400 秒')
        with self.store.tx() as (d,r):
            run=self.store.get(d,'runs',run_id);node=self.store.node(d,run['node_id']);self.store.ensure_open(d,node)
            if node['kind']!='action' or run['status']!='pending': raise DomainError('仅可派发待执行行动 Run')
            device=self.store.get(d,'devices',data.get('device_id'))
            job={'id':uid('job'),'run_id':run_id,'space_id':run['space_id'],'device_id':device['id'],'argv':argv,'cwd':cwd,'timeout_seconds':timeout,'status':'queued','created_at':now()}
            d['jobs'][job['id']]=job;run.update(status='dispatched',execution_mode='device_agent',device=device['name'],device_id=device['id'],job_id=job['id']);self.store.touch(node)
            self.store.log(d,'dispatch_run',{'run_id':run_id,'job_id':job['id'],'argv':argv},run['space_id'])
            return job
    def claim(self,data):
        with self.store.tx() as (d,r):
            device=self._auth(d,data);device['last_seen']=now()
            job=next((j for j in d['jobs'].values() if j['device_id']==device['id'] and j['status']=='queued'),None)
            if job: job.update(status='accepted',claimed_at=now())
            return {'job':job}
    def submit(self,run_id,data):
        # Hold process lock across domain transaction: claim/report cannot race locally.
        with self.store.lock:
            d=self.store.read();device=self._auth(d,data);job=self.store.get(d,'jobs',data.get('job_id'))
            if job['device_id']!=device['id'] or job['run_id']!=run_id or job['status']=='queued': raise DomainError('执行归属不匹配')
            event=self.store.report_event(run_id,data)
            with self.store.tx() as (d,r):
                d['jobs'][job['id']]['status']=event['status'];d['devices'][device['id']]['last_seen']=now()
            return event
