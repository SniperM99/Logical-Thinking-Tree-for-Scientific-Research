#!/usr/bin/env python3
"""Live Java → PostgreSQL + FastAPI acceptance. Creates a dedicated audit space.
Never uses the SQLite prototype. No external model key or device execution required.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class Verification:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.checks = []
        self.created_spaces = []

    def call(self, method, path, data=None, expected=200, raw=False):
        request = urllib.request.Request(self.base+path,
            data=None if data is None else json.dumps(data,ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json'},method=method)
        try:
            with urllib.request.urlopen(request,timeout=90) as response:
                code,body=response.status,response.read().decode()
        except urllib.error.HTTPError as error:
            code,body=error.code,error.read().decode()
        if code!=expected:
            raise AssertionError(f'{method} {path}: expected {expected}, got {code}: {body[:800]}')
        return body if raw else json.loads(body)

    def passed(self,label):
        self.checks.append({'name':label,'passed':True})
        print('PASS '+label,flush=True)

    def state(self,sid):
        return self.call('GET','/api/state?'+urllib.parse.urlencode({'space_id':sid}))

    def context(self,nid):
        return self.call('GET','/api/context?'+urllib.parse.urlencode({'node_id':nid}))

    def node(self,parent,title,summary=None,kind='thought'):
        return self.call('POST','/api/nodes',{'parent_id':parent,'title':title,
            'summary':summary or title+'_DIRECT','kind':kind})

    def proposal(self,op,node,**extra):
        return self.call('POST','/api/proposals',{'operation':op,'node_id':node,
            'reason':'真实 HTTP 集成验收：明确审核范围',**extra})

    def approve(self,proposal):
        return self.call('POST',f"/api/proposals/{proposal['id']}/approve",{})

    def run(self):
        health=self.call('GET','/api/health')
        assert 'Java' in health.get('final_write_authority',''),health
        self.passed('最终写入入口是 Java Research Graph Core')
        suffix=uuid.uuid4().hex[:10]
        space=self.call('POST','/api/spaces',{'title':'HTTP 验收 '+suffix,'goal':'ROOT_BACKGROUND_'+suffix})
        sid,root=space['id'],space['root_id'];self.created_spaces.append(sid)
        parent=self.node(root,'PARENT_'+suffix)
        child=self.node(parent['id'],'CHILD_'+suffix)
        sibling=self.node(root,'SIBLING_SECRET_'+suffix)
        conversation=self.call('POST','/api/conversations',{'node_id':parent['id']})
        saved_snapshot=conversation['context_snapshot']
        topic='独立成簇_'+suffix
        base={'conversation_id':conversation['id'],'question':'如何验证一个独立问题？','answer':'保留实验条件与原始证据',
            'thoughts':[{'text':'研究 A','topic':topic,'node_id':child['id']},
                        {'text':'辅助研究 A','topic':topic,'node_id':child['id']}]}
        first=self.call('POST','/api/qa',{**base,'request_id':'q1-'+suffix})
        assert first['created_nodes']==[],first
        second=self.call('POST','/api/qa',{**base,'request_id':'q2-'+suffix})
        assert len(second['created_nodes'])==1,second
        third=self.call('POST','/api/qa',{**base,'request_id':'q3-'+suffix})
        repeated=self.call('POST','/api/qa',{**base,'request_id':'q3-'+suffix})
        assert third['created_nodes']==[] and repeated.get('idempotent'),(third,repeated)
        state=self.state(sid)
        assert len([n for n in state['nodes'] if n['title']==topic])==1
        assert len(state['qas'])==3
        self.passed('独立问答计数、增量成簇和请求去重')
        actual=self.call('GET','/api/conversations/'+conversation['id'])['conversation']
        assert actual['anchor_id']==parent['id'] and actual['context_snapshot']==saved_snapshot
        assert first['qa']['user_message_id'] and first['qa']['answer_message_id']
        self.passed('会话锚点、启动快照及消息级定位永久保留')
        parent_context=self.context(parent['id'])
        assert parent_context['direct']==parent['summary']
        rendered=json.dumps(parent_context,ensure_ascii=False)
        assert child['summary'] not in rendered and sibling['summary'] not in rendered and topic not in rendered
        self.passed('父节点上下文排除后代成果和兄弟分支')
        pending=self.proposal('move',child['id'],target_id=sibling['id'])
        self.node(root,'审核后新方向_'+suffix)
        self.call('POST','/api/proposals/'+pending['id']+'/approve',{},expected=400)
        child_after=next(n for n in self.state(sid)['nodes'] if n['id']==child['id'])
        assert child_after['parent_id']==parent['id']
        self.call('POST','/api/proposals',{'operation':'move','node_id':parent['id'],
            'target_id':child['id'],'reason':'循环应拒绝'},expected=400)
        self.passed('失效审核和生长循环被拒绝且无部分修改')
        source_a=self.node(root,'SOURCE_A_'+suffix);source_b=self.node(root,'SOURCE_B_'+suffix)
        child_a=self.node(source_a['id'],'SOURCE_A_CHILD_'+suffix)
        joined=self.approve(self.proposal('confluence',source_a['id'],
            sources=[source_a['id'],source_b['id']],title='共同方向_'+suffix))
        state=self.state(sid);nodes={n['id']:n for n in state['nodes']}
        joint=nodes[joined['result_node_id']]
        assert joint['parent_id'] is None and joint['sources']==[source_a['id'],source_b['id']]
        assert nodes[child_a['id']]['parent_id']==source_a['id']
        assert len(self.context(joint['id'])['sources'])==2
        self.passed('共同分支多来源独立表达且原子树不变')
        transplanted=self.node(root,'TRANSPLANT_'+suffix)
        transplant_child=self.node(transplanted['id'],'TRANSPLANT_CHILD_'+suffix)
        transplant_conv=self.call('POST','/api/conversations',{'node_id':transplanted['id']})
        evidence=self.call('POST','/api/qa',{'conversation_id':transplant_conv['id'],
            'question':'移植原文','answer':'不可修改的证据','request_id':'transplant-'+suffix})['qa']
        plan=self.proposal('transplant',transplanted['id'],title='独立验收空间 '+suffix)
        nutrition=plan['preview']['context_md']
        assert space['goal'] in nutrition and transplanted['summary'] in nutrition
        assert sibling['summary'] not in nutrition and transplant_child['summary'] not in nutrition
        approved=self.approve(plan);new_sid=approved['result_space_id'];self.created_spaces.append(new_sid)
        new_state=self.state(new_sid);old_state=self.state(sid)
        assert {n['id'] for n in new_state['nodes']}=={transplanted['id'],transplant_child['id']}
        assert transplanted['id'] not in {n['id'] for n in old_state['nodes']}
        old_conv=self.call('GET','/api/conversations/'+transplant_conv['id'])
        assert old_conv['conversation']['anchor_id']==transplanted['id']
        assert old_conv['conversation']['space_id']==sid
        assert next(q for q in old_conv['qas'] if q['id']==evidence['id'])==evidence
        assert {r['thought_id'] for r in new_state['refs']}.issubset({t['id'] for t in new_state['thoughts']})
        downloaded=self.call('GET','/api/transplants/'+approved['transplant_id']+'/context',raw=True)
        assert downloaded==nutrition
        self.passed('移植营养路径、完整子树、原文锚点和独立空间隔离')
        action=self.node(root,'ACTION_'+suffix,kind='action')
        run=self.call('POST','/api/runs',{'node_id':action['id'],'device':'集成验收人工回报'})
        start={'event_id':'start-'+suffix,'status':'running','sequence':1}
        first_event=self.call('POST','/api/runs/'+run['id']+'/events',start)
        replay=self.call('POST','/api/runs/'+run['id']+'/events',start)
        assert replay==first_event
        self.call('POST','/api/runs/'+run['id']+'/events',{'event_id':'stale-'+suffix,
            'status':'running','sequence':1},expected=400)
        self.call('POST','/api/runs/'+run['id']+'/events',{'event_id':'failure-'+suffix,
            'status':'failed','result':{'error':'验收模拟失败'}})
        retry=self.call('POST','/api/runs',{'node_id':action['id'],'retry_of':run['id']})
        assert retry['id']!=run['id'] and retry['retry_of']==run['id']
        assert self.context(root)['direct']==space['goal']
        self.passed('实验 Run 事件去重、乱序拒绝、重试独立及祖先不回写')
        branch=self.node(root,'FREEZE_'+suffix)
        self.approve(self.proposal('freeze',branch['id']))
        self.call('POST','/api/nodes',{'parent_id':branch['id'],'title':'冻结后不得生长'},expected=400)
        self.approve(self.proposal('unfreeze',branch['id']))
        self.approve(self.proposal('hide',branch['id']))
        self.node(branch['id'],'HIDDEN_GROWTH_'+suffix)
        self.approve(self.proposal('restore',branch['id']))
        assert not next(n for n in self.state(sid)['nodes'] if n['id']==branch['id'])['hidden']
        self.passed('冻结阻断生长、隐藏仍可研究且可恢复')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8080')
    parser.add_argument('--output',help='保存真实验收结果 JSON 的路径')
    args=parser.parse_args();verification=Verification(args.base_url)
    result={'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'base_url':args.base_url}
    try:
        verification.run();result['passed']=True
    except Exception as error:
        result['passed']=False;result['error']=str(error)
        print('FAIL '+str(error),file=sys.stderr)
    result.update({'checks':verification.checks,'created_spaces':verification.created_spaces,
        'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'note':'验收研究空间和证据保留，不删除或伪装真实实验。'})
    if args.output:Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':sys.exit(main())
