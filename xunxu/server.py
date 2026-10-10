#!/usr/bin/env python3
"""Local HTTP application; stdlib only. Bind loopback by default."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from domain import Store, DomainError

ROOT=Path(__file__).resolve().parent
STORE=None

def model_answer(conversation, question):
    key=os.environ.get('XUNXU_API_KEY')
    base=os.environ.get('XUNXU_API_BASE')
    model=os.environ.get('XUNXU_MODEL')
    if not all((key,base,model)):
        raise DomainError('模型尚未配置：请填写已有回答以人工记录，或在服务端设置 XUNXU_API_KEY、XUNXU_API_BASE、XUNXU_MODEL。')
    url=base.rstrip('/')+'/chat/completions'
    if not url.startswith(('https://','http://localhost:','http://127.0.0.1:')):
        raise DomainError('模型地址必须为 HTTPS 或本机 HTTP')
    context=conversation['context_snapshot']
    # Only current conversation history and original scoped snapshot are included.
    d=STORE.read()
    anchor=conversation['anchor_id']
    admitted={r['thought_id'] for r in d['refs'].values() if r['node_id']==anchor}
    history=[t for t in d['thoughts'].values() if t['id'] in admitted and d['qas'][t['qa_id']]['conversation_id']==conversation['id']]
    messages=[{'role':'system','content':'你是循序科研助手。研究上下文如下，区分事实与假设，不声称未进行的实验已经完成。不要将后代结论回写祖先。\n'+json.dumps(context,ensure_ascii=False)}]
    if history:
        scoped=[{'thought':t['text'],'excerpt':t['excerpt'],'qa_id':t['qa_id']} for t in sorted(history,key=lambda x:x['created_at'])[-24:]]
        messages.append({'role':'system','content':'当前节点准入的会话思想片段（原会话中的其他思想未纳入上下文）：\n'+json.dumps(scoped,ensure_ascii=False)})
    messages.append({'role':'user','content':question})
    req=urllib.request.Request(url,data=json.dumps({'model':model,'messages':messages},ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=90) as response:
            result=json.load(response)
        return result['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        raise DomainError('模型服务返回 HTTP '+str(e.code)+'，请检查配置与账户额度。') from None
    except (urllib.error.URLError,TimeoutError,KeyError,TypeError) as e:
        raise DomainError('模型调用失败或返回格式不兼容，请检查服务端配置。') from None

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def send(self,status,body,content_type='application/json; charset=utf-8',headers=None):
        if not isinstance(body,bytes):
            body=(json.dumps(body,ensure_ascii=False) if content_type.startswith('application/json') else str(body)).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def fail(self,e):
        if isinstance(e,(DomainError,KeyError,ValueError)):
            self.send(400,{'error':str(e) if not isinstance(e,KeyError) else '缺少必需字段：'+str(e)})
        else:
            self.log_error('internal error: %s',e)
            self.send(500,{'error':'服务处理失败，请查看本地服务日志。'})
    def do_GET(self):
        try:
            parsed=urllib.parse.urlparse(self.path)
            path=parsed.path;query=urllib.parse.parse_qs(parsed.query)
            if path=='/api/state':return self.send(200,STORE.state(query.get('space_id',[None])[0]))
            if path=='/api/context':return self.send(200,STORE.context(query.get('node_id',[''])[0]))
            if path=='/api/health':return self.send(200,{'ok':True,'version':'0.1.0','framework':'1.1'})
            if path.startswith('/api/transplants/') and path.endswith('/context'):
                t=STORE.get(STORE.read(),'transplants',path.split('/')[3])
                filename=urllib.parse.quote('research-context.md')
                return self.send(200,t['context_md'],'text/markdown; charset=utf-8',{'Content-Disposition':"attachment; filename*=UTF-8''"+filename})
            if path.startswith('/api/conversations/'):
                d=STORE.read();c=STORE.get(d,'conversations',path.split('/')[3])
                return self.send(200,{'conversation':c,'qas':[q for q in d['qas'].values() if q['conversation_id']==c['id']]})
            if path=='/api/export':
                # Whole local database content export is an explicit backup endpoint.
                return self.send(200,STORE.read(),headers={'Content-Disposition':'attachment; filename="xunxu-backup.json"'})
            if path.startswith('/api/'):return self.send(404,{'error':'API 不存在'})
            file=(ROOT/'static'/('index.html' if path=='/' else (path[len('/static/'):] if path.startswith('/static/') else path.lstrip('/')))).resolve()
            if ROOT/'static' not in file.parents or not file.is_file():return self.send(404,'Not found','text/plain')
            mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}.get(file.suffix,'application/octet-stream')
            self.send(200,file.read_bytes(),mime)
        except Exception as e:self.fail(e)
    def do_POST(self):
        try:
            # Prevent other websites from modifying local research through a browser.
            origin=self.headers.get('Origin')
            if origin:
                o=urllib.parse.urlparse(origin)
                if o.netloc!=self.headers.get('Host') or o.scheme!='http':
                    return self.send(403,{'error':'拒绝跨来源修改请求'})
            if 'application/json' not in self.headers.get('Content-Type',''):
                return self.send(415,{'error':'请使用 application/json'})
            length=int(self.headers.get('Content-Length','0'))
            if length>2_000_000:raise DomainError('请求过大')
            data=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data,dict):raise DomainError('请求必须为 JSON 对象')
            path=urllib.parse.urlparse(self.path).path
            if path=='/api/spaces':result=STORE.create_space(data.get('title'),data.get('goal'))
            elif path=='/api/nodes':result=STORE.create_node(data)
            elif path=='/api/conversations':result=STORE.create_conversation(data)
            elif path=='/api/qa':
                if not data.get('answer'):
                    d=STORE.read();c=STORE.get(d,'conversations',data['conversation_id'])
                    STORE.ensure_open(d,STORE.node(d,c['anchor_id']))
                    data['answer']=model_answer(c,data['question']);data['mode']='model'
                result=STORE.add_qa(data)
            elif path=='/api/proposals':result=STORE.propose(data)
            elif path.startswith('/api/proposals/'):
                _,_,_,id,action=path.split('/')
                if action=='approve':result=STORE.approve(id)
                elif action=='reject':result=STORE.reject(id)
                else:raise DomainError('未知审核动作')
            elif path=='/api/runs':result=STORE.create_run(data)
            elif path.startswith('/api/runs/') and path.endswith('/events'):result=STORE.report_event(path.split('/')[3],data)
            elif path=='/api/resources':result=STORE.add_resource(data)
            elif path.startswith('/api/audit/') and path.endswith('/undo'):result=STORE.undo(path.split('/')[3])
            else:return self.send(404,{'error':'API 不存在'})
            self.send(200,result)
        except Exception as e:self.fail(e)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='循序 V1.1 本地科研系统')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--db',default=str(ROOT/'data'/'xunxu.sqlite3'))
    parser.add_argument('--no-seed',action='store_true')
    args=parser.parse_args()
    STORE=Store(args.db)
    if not args.no_seed:STORE.seed()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'循序已启动：http://127.0.0.1:{args.port}  数据库：{args.db}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
