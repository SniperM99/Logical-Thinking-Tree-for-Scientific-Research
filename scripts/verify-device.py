#!/usr/bin/env python3
"""Real HTTP acceptance against Java core; creates an isolated acceptance space."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8081')
    args=parser.parse_args();base=args.base_url.rstrip('/')
    def api(path,data=None):
        headers={'Content-Type':'application/json'}
        token=os.environ.get('XUNXU_DEVICE_SERVER_TOKEN')
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
        with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
    health=api('/api/health')
    assert health.get('final_write_authority')=='Java Research Graph Core','Acceptance requires Java core'
    agent=Path(__file__).resolve().parents[1]/'device-agent'/'agent.py'
    with tempfile.TemporaryDirectory(prefix='xunxu-acceptance-') as workspace:
        cmd=[sys.executable,str(agent),'--server',base,'--workspace',workspace,'--name','acceptance-'+uuid.uuid4().hex[:8],'--once']
        def worker():
            completed=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
            if completed.returncode:raise AssertionError('Device Agent failed; exit code '+str(completed.returncode))
        worker() # Registers and finds no work.
        identity=json.loads((Path(workspace)/'.xunxu-agent.json').read_text())['identity']
        space=api('/api/spaces',{'title':'设备协议验收 '+uuid.uuid4().hex[:8],'goal':'真实 subprocess → Java 事件写入验收'})
        node=api('/api/nodes',{'parent_id':space['root_id'],'title':'执行 print42','kind':'action','summary':'验收独立 Agent 与有序执行事件'})
        run=api('/api/runs',{'node_id':node['id']})
        job=api('/api/runs/'+run['id']+'/dispatch',{'device_id':identity['device_id'],'argv':[sys.executable,'-c','print(42)'],'cwd':'.','timeout_seconds':10})
        worker()
        state=api('/api/state?space_id='+space['id'])
        actual=next(r for r in state['runs'] if r['id']==run['id'])
        assert actual['status']=='completed','Run did not complete'
        assert actual['result']['stdout'].strip()=='42','Unexpected subprocess stdout'
        assert actual['result']['exit_code']==0,'Subprocess failed'
        events=sorted((e for e in state['events'] if e['run_id']==run['id']),key=lambda e:e['sequence'])
        assert [e['status'] for e in events]==['running','returning','verifying','completed'],'Invalid event state ordering'
        assert [e['sequence'] for e in events]==[1,2,3,4],'Invalid sequence'
        replay={**identity,'job_id':job['id'],'event_id':events[-1]['event_id'],'sequence':4,'status':'completed','result':actual['result']}
        duplicate=api('/api/runs/'+run['id']+'/report',replay)
        assert duplicate['id']==events[-1]['id'],'Replay created a second event'
        after=api('/api/state?space_id='+space['id'])
        assert len([e for e in after['events'] if e['run_id']==run['id']])==4,'Replay altered event count'
        assert api('/api/jobs/claim',identity)['job'] is None,'Completed job was redelivered'
        try:api('/api/jobs/claim',{**identity,'device_token':'invalid-token'})
        except urllib.error.HTTPError as error:assert 400<=error.code<500,'Authentication failure must be client error'
        else:raise AssertionError('Invalid device token accepted')
        for device in api('/api/devices'):
            assert 'token_hash' not in device and 'device_token' not in device,'Device secrets leaked'
        print('PASS: Java HTTP + independent Agent + real subprocess stdout=42; four ordered events; idempotent replay; duplicate delivery prevented; invalid token rejected.')
        print('Acceptance space: '+space['id'])
        print('Run: '+run['id'])

if __name__=='__main__':main()
