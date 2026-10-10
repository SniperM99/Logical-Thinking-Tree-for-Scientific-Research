#!/usr/bin/env python3
"""Stdlib polling device worker: Java core owns all research state writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

class Agent:
    def __init__(self,args):
        self.args=args;self.workspace=Path(args.workspace).resolve();self.workspace.mkdir(parents=True,exist_ok=True)
        self.state=self.workspace/'.xunxu-agent.json'
        if self.state.exists():
            saved=json.loads(self.state.read_text());self.identity=saved['identity']
            if saved['server']!=args.server: raise ValueError('State belongs to another server; use a separate workspace')
        else:
            self.identity=self.api('/api/devices/register',{'name':args.name,'workspace':str(self.workspace)})
            self.save()
    def save(self,active=None):
        temp=self.state.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'server':self.args.server,'identity':self.identity,'active':active},f)
        os.replace(temp,self.state);os.chmod(self.state,0o600)
    def api(self,path,data):
        headers={'Content-Type':'application/json'}
        token=os.environ.get('XUNXU_DEVICE_SERVER_TOKEN')
        if token: headers['Authorization']='Bearer '+token
        req=urllib.request.Request(self.args.server.rstrip('/')+path,data=json.dumps(data).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=30) as res:return json.load(res)
    def report(self,job,seq,status,result=None):
        payload={**self.identity,'job_id':job['id'],'event_id':job['id']+':'+str(seq),'sequence':seq,'status':status,'message':'设备执行状态：'+status}
        if result is not None:payload['result']=result
        # Retry same idempotency key; never execute the command again.
        for attempt in range(5):
            try:return self.api('/api/runs/'+job['run_id']+'/report',payload)
            except Exception:
                if attempt==4:raise
                time.sleep(min(2**attempt,10))
    def execute(self,job):
        self.save({'job_id':job['id'],'run_id':job['run_id'],'status':'claimed'})
        self.report(job,1,'running')
        result={'exit_code':None};success=False
        try:
            argv=job['argv'];cwd=(self.workspace/job.get('cwd','.')).resolve()
            if not cwd.is_relative_to(self.workspace):raise ValueError('cwd escapes approved workspace')
            if not isinstance(argv,list) or not argv or not all(isinstance(s,str) for s in argv):raise ValueError('argv must be a list of strings')
            logs=self.workspace/'.xunxu-runs'/job['id'];logs.mkdir(parents=True,exist_ok=True)
            out=logs/'stdout.log';err=logs/'stderr.log'
            env=os.environ.copy();env.pop('XUNXU_DEVICE_SERVER_TOKEN',None)
            with out.open('wb') as stdout,err.open('wb') as stderr:
                proc=subprocess.Popen(argv,cwd=cwd,stdout=stdout,stderr=stderr,env=env,shell=False,start_new_session=True)
                try:code=proc.wait(timeout=job.get('timeout_seconds',300))
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait();code=-9;result['error']='execution timeout'
            result['exit_code']=code;success=code==0
            for name,path in [('stdout',out),('stderr',err)]:
                digest=hashlib.sha256()
                with path.open('rb') as f:
                    for chunk in iter(lambda:f.read(65536),b''):digest.update(chunk)
                    f.seek(max(0,path.stat().st_size-10000));result[name]=f.read().decode('utf-8','replace')
                result[name+'_sha256']=digest.hexdigest();result[name+'_path']=str(path)
        except Exception as exc:result['error']=str(exc)
        self.report(job,2,'returning',result);self.report(job,3,'verifying');self.report(job,4,'completed' if success else 'failed',result);self.save()
    def run(self):
        # Unknown execution after process restart requires human review, never replay.
        if json.loads(self.state.read_text()).get('active'):raise RuntimeError('Unfinished claimed job. Inspect server Run and logs before clearing active state; command will not replay.')
        while True:
            self.api('/api/devices/heartbeat',self.identity)
            job=self.api('/api/jobs/claim',self.identity).get('job')
            if job:self.execute(job)
            if self.args.once:return
            if not job:time.sleep(self.args.poll_seconds)

def main():
    p=argparse.ArgumentParser();p.add_argument('--server',default='http://127.0.0.1:8765');p.add_argument('--workspace',required=True);p.add_argument('--name',default='local-device');p.add_argument('--once',action='store_true');p.add_argument('--poll-seconds',type=float,default=3)
    args=p.parse_args();Agent(args).run()
if __name__=='__main__':main()
