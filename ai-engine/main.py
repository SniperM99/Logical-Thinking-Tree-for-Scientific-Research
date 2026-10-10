"""Stateless AI analysis. Java owns final writes, evidence admission and approvals."""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from typing import Literal
from embeddings import local_embedding, METHOD
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title='循序 AI 引擎', version='0.1.0')

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ContextEntry(StrictModel):
    node_id: str
    title: str
    summary: str = ''

class ScopedContext(StrictModel):
    space_id: str
    node_id: str
    direct_summary: str = ''
    nutrition_context: str = Field(default='',max_length=200000)
    ancestors: list[ContextEntry] = Field(default_factory=list)
    approved_sources: list[ContextEntry] = Field(default_factory=list)

class ExistingNode(StrictModel):
    node_id: str
    space_id: str
    title: str
    summary: str = ''

class ThoughtInput(StrictModel):
    text: str = Field(min_length=1,max_length=12000)
    topic: str = Field(min_length=1,max_length=200)
    excerpt: str = Field(default='',max_length=12000)
    independent: bool = False
    core_concepts: list[str] = Field(default_factory=list,max_length=5)

class ChatTurn(StrictModel):
    qa_id: str
    question: str = Field(min_length=1,max_length=30000)
    answer: str = Field(min_length=1,max_length=60000)

class AnalyzeRequest(StrictModel):
    qa_id: str
    question: str = Field(min_length=1,max_length=30000)
    answer: str = Field(min_length=1,max_length=60000)
    context: ScopedContext
    thoughts: list[ThoughtInput] = Field(default_factory=list,max_length=8)
    existing_nodes: list[ExistingNode] = Field(default_factory=list,max_length=1000)
    intent_catalog: list[str] = Field(default_factory=list,max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list,max_length=200)

class CandidatesRequest(StrictModel):
    context: ScopedContext
    count: int = Field(default=3,ge=2,le=3)
    retained_titles: list[str] = Field(default_factory=list,max_length=50)

class ChatRequest(StrictModel):
    history: list[ChatTurn] = Field(default_factory=list,max_length=200)
    question: str = Field(min_length=1,max_length=30000)
    context: ScopedContext


def lexical_vector(text: str) -> list[float]:
    compact = re.sub(r'\s+','',text.lower())
    vector = [0.0]*256
    for token in (compact[i:i+2] for i in range(max(0,len(compact)-1))):
        vector[int(hashlib.sha256(token.encode()).hexdigest()[:8],16)%256] += 1
    norm = math.sqrt(sum(v*v for v in vector)) or 1
    return [round(v/norm,7) for v in vector]


def provider_request(path: str, body: dict, *, embedding: bool = False) -> dict:
    prefix = 'XUNXU_EMBEDDING' if embedding else 'XUNXU'
    base = os.environ.get(prefix+'_API_BASE')
    key = os.environ.get(prefix+'_API_KEY')
    if not base or not key:
        raise HTTPException(503,'模型服务未配置；可以提交人工问答并使用明确标记的实验性分析。')
    if not (base.startswith('https://') or base.startswith(('http://127.0.0.1:','http://localhost:'))):
        raise HTTPException(503,'模型地址必须使用 HTTPS 或本机 HTTP。')
    body=dict(body)
    if path=='chat/completions' and base.rstrip('/').endswith('api.deepseek.com'):
        body.setdefault('thinking',{'type':'disabled'})
    req = urllib.request.Request(base.rstrip('/')+'/'+path,
        data=json.dumps(body,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail={401:'DeepSeek 密钥无效或已失效。',402:'DeepSeek 账户余额不足。',429:'模型服务请求限流，请稍后重试。'}.get(error.code,'模型服务拒绝请求（HTTP '+str(error.code)+'）。')
        raise HTTPException(502,detail) from None
    except (urllib.error.URLError,TimeoutError,ValueError):
        raise HTTPException(502,'模型请求失败，请检查服务连接与返回格式。') from None


def coordinates(texts: list[str]) -> tuple[list[list[float]],str,bool]:
    model = os.environ.get('XUNXU_EMBEDDING_MODEL')
    if not model:
        try:return local_embedding.encode(texts),METHOD,True
        except Exception:raise HTTPException(503,'本地语义嵌入尚未就绪，请安装模型并检查 /health。') from None
    result = provider_request('embeddings',{'model':model,'input':texts},embedding=True)
    try:
        data = sorted(result['data'],key=lambda row:row['index'])
        vectors = [row['embedding'] for row in data]
        if len(vectors)!=len(texts) or len({len(v) for v in vectors})!=1 or not vectors[0]:
            raise ValueError()
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for vec in vectors for v in vec):
            raise ValueError()
        return vectors,'provider:'+model,True
    except (KeyError,TypeError,ValueError,IndexError):
        raise HTTPException(502,'嵌入模型返回的坐标数量、维度或数值不合法。') from None


def validate_scope(request: AnalyzeRequest):
    if any(n.space_id != request.context.space_id for n in request.existing_nodes):
        raise HTTPException(422,'已有节点只能来自当前研究空间。')
    if len({n.node_id for n in request.existing_nodes}) != len(request.existing_nodes):
        raise HTTPException(422,'已有节点 ID 重复。')
    for thought in request.thoughts:
        if thought.excerpt and thought.excerpt not in request.question and thought.excerpt not in request.answer:
            raise HTTPException(422,'思想引用片段必须来自原始问答。')


def analyze(request: AnalyzeRequest) -> dict:
    validate_scope(request)
    specs = request.thoughts
    if not specs and os.environ.get('XUNXU_MODEL'):
        result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'response_format':{'type':'json_object'},'max_tokens':1200,'messages':[
            {'role':'system','content':'仅提取当前问答的1至3个科研思想。会话历史仅帮助理解指代，不重复提取历史问答。仅输出 JSON 对象 thoughts 数组，每项 text、topic、excerpt、core_concepts（1至5个短核心概念，例如研究对象、关键机制、方法，不能仅复述全文）。第一项为主要思想。topic 是简短且稳定的具体研究问题；若与已知研究意图同一问题同一适用条件，复用其 topic，不能仅因词语相似复用。excerpt 必须逐字来自当前问答。不得将假设写成已证明结论，不提出结构移动。'},
            {'role':'user','content':json.dumps({'question':request.question,'answer':request.answer,'context':request.context.model_dump(),'known_intents':request.intent_catalog,'conversation_history':[turn.model_dump() for turn in request.history]},ensure_ascii=False)}]})
        try:
            raw=json.loads(result['choices'][0]['message']['content'])['thoughts']
            if not isinstance(raw,list) or not 1<=len(raw)<=3:raise ValueError()
            specs=[ThoughtInput(text=t['text'],topic=t['topic'],excerpt=t.get('excerpt',''),independent=False,core_concepts=t.get('core_concepts',[])[:5]) for t in raw]
            for spec in specs:
                if spec.excerpt and spec.excerpt not in request.question and spec.excerpt not in request.answer:raise ValueError()
        except (KeyError,TypeError,IndexError,ValueError):
            raise HTTPException(502,'自动思想提取结果不合法，研究数据未提交。') from None
    if not specs:
        specs=[ThoughtInput(text=request.question,topic=request.question[:80])]
    vectors, method, semantic = coordinates([specs[0].text])
    thoughts = []
    for index,spec in enumerate(specs):
        vector=vectors[0] if index==0 else []
        trigger = hashlib.sha256((request.context.space_id+'\0'+request.qa_id+'\0'+str(index)).encode()).hexdigest()
        matches = [n for n in request.existing_nodes if n.title.strip()==spec.topic.strip()]
        # Exact labels are candidate matches, never enough to declare intent/conditions equal.
        proposal = {'type':'independent_thought' if spec.independent else 'cluster_candidate',
                    'parent_candidate_id':request.context.node_id,'topic':spec.topic,
                    'requires_intent_validation':True,'minimum_distinct_qas':1 if spec.independent else 2,
                    'matched_node_candidates':[n.node_id for n in matches],
                    'create_automatically':False,
                    'reason':'需由业务服务检查既有承载、独立问答数、研究意图、冻结与结构上下文。'}
        thoughts.append({'trigger_id':trigger,'qa_id':request.qa_id,'role':'main' if index==0 else 'auxiliary',
                         'text':spec.text,'topic':spec.topic,'excerpt':spec.excerpt,'core_concepts':spec.core_concepts or [spec.topic],
                         'original_coordinate':vector,'working_coordinate':vector[:],
                         'coordinate_method':method if index==0 else 'not-quantified','semantic_embedding':semantic if index==0 else False,'proposal':proposal})
    return {'qa_id':request.qa_id,'space_id':request.context.space_id,'node_id':request.context.node_id,
            'thoughts':thoughts,'analysis_version':'0.1.0','writes_performed':False,
            'validation_status':'unvalidated','warnings':['高维坐标、显示坐标与结构归属必须分开。',
                '此接口只提出建议，不能批准结构修改或宣称研究结论成立。']}


def candidates(request: CandidatesRequest) -> dict:
    # Offline suggestions are explicitly templates, not predicted scientific discoveries.
    title = request.context.direct_summary[:60] or '当前研究问题'
    candidates = [
        {'title':'检验关键假设','description':f'围绕“{title}”定义可证伪条件与需要的证据。'},
        {'title':'对照替代解释','description':f'围绕“{title}”设计能够区分不同解释的对照。'},
        {'title':'验证适用边界','description':f'围绕“{title}”确认结论在何种条件下不再成立。'},
    ][:request.count]
    return {'space_id':request.context.space_id,'node_id':request.context.node_id,
            'type':'hypothesis_validation','candidates':candidates,'retained_titles':request.retained_titles,
            'method':'offline-research-templates','validation_status':'unvalidated','writes_performed':False}


@app.get('/health')
def health():
    return {'ok':True,'service':'ai-engine','stateless':True,'model_configured':bool(os.environ.get('XUNXU_MODEL') and os.environ.get('XUNXU_API_BASE') and os.environ.get('XUNXU_API_KEY')),'final_write_authority':'java-backend',
            'model':os.environ.get('XUNXU_MODEL'),'thought_extraction':'model' if os.environ.get('XUNXU_MODEL') else 'offline','embedding_mode':'provider' if os.environ.get('XUNXU_EMBEDDING_MODEL') else 'local-semantic-onnx','embedding':local_embedding.health() if not os.environ.get('XUNXU_EMBEDDING_MODEL') else {'ready':bool(os.environ.get('XUNXU_EMBEDDING_API_BASE') and os.environ.get('XUNXU_EMBEDDING_API_KEY')),'method':'provider:'+os.environ['XUNXU_EMBEDDING_MODEL'],'semantic_embedding':True}}

@app.post('/analyze')
def analyze_endpoint(request: AnalyzeRequest):
    return analyze(request)

@app.post('/candidates')
def candidates_endpoint(request: CandidatesRequest):
    return candidates(request)

@app.post('/chat')
def chat_endpoint(request: ChatRequest):
    model = os.environ.get('XUNXU_MODEL')
    if not model:
        raise HTTPException(503,'尚未配置 XUNXU_MODEL。')
    messages=[{'role':'system','content':'你是循序科研助手。使用以下准入的祖先路径、当前节点背景及本会话历史进行连续交流。会话历史用于理解指代，不代表父节点已接受的结论；区分事实、假设和未执行实验，不引入其他会话或子孙总结。\n'+request.context.model_dump_json()}]
    for turn in request.history:
        messages.extend([{'role':'user','content':turn.question},{'role':'assistant','content':turn.answer}])
    messages.append({'role':'user','content':request.question})
    result = provider_request('chat/completions',{'model':model,'max_tokens':2400,'messages':messages})
    try:
        answer = result['choices'][0]['message']['content']
        if not isinstance(answer,str) or not answer.strip(): raise ValueError()
        return {'answer':answer,'model':model,'writes_performed':False}
    except (KeyError,TypeError,IndexError,ValueError):
        raise HTTPException(502,'模型返回格式不兼容。') from None

class CoordinatesRequest(StrictModel):
    texts: list[str] = Field(min_length=1,max_length=128)

@app.post('/coordinates')
def coordinates_endpoint(request: CoordinatesRequest):
    if any(not t.strip() or len(t)>12000 for t in request.texts):raise HTTPException(422,'文本不能为空且最多12000字符')
    vectors,method,semantic=coordinates(request.texts)
    return {'vectors':vectors,'method':method,'dimension':len(vectors[0]),'semantic_embedding':semantic,'normalization':'L2' if method==METHOD else 'provider-defined','writes_performed':False}

class IntentDescription(StrictModel):
    role: str = Field(default='',max_length=20)
    text: str = Field(default='',max_length=12000)
    topic: str = Field(default='',max_length=200)
    core_concepts: list[str] = Field(default_factory=list,max_length=5)
    question: str = Field(default='',max_length=30000)
class IntentPair(StrictModel):
    id: str
    left: IntentDescription
    right: IntentDescription
class IntentMatches(StrictModel):
    pairs: list[IntentPair] = Field(min_length=1,max_length=30)
    context: ScopedContext
class IntentMatch(StrictModel):
    left: IntentDescription
    right: IntentDescription
    context: ScopedContext

@app.post('/intent-matches')
def intent_matches(request: IntentMatches):
    if len({p.id for p in request.pairs})!=len(request.pairs):raise HTTPException(422,'pair id重复')
    if not os.environ.get('XUNXU_MODEL'):
        return {'decisions':[{'id':p.id,'decision':'not_evaluated','reason':'模型未配置，不能判定语义归并'} for p in request.pairs],'writes_performed':False}
    schema={'type':'object','additionalProperties':False,'required':['decisions'],'properties':{'decisions':{'type':'array','minItems':1,'maxItems':30,'items':{'type':'object','additionalProperties':False,'required':['id','decision','reason','direction_title','direction_reason'],'properties':{'id':{'type':'string'},'decision':{'type':'string','enum':['same_intent','related','distinct']},'reason':{'type':'string'},'direction_title':{'type':'string'},'direction_reason':{'type':'string'}}}}}}
    result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'max_tokens':6000,'tools':[{'type':'function','function':{'name':'deliver_intent_matches','description':'返回思想意图与研究方向判断，不执行结构操作','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_intent_matches'}},'messages':[
        {'role':'system','content':'判断研究意图是否相同。仅通过 deliver_intent_matches 返回 JSON decisions数组，每项必须包含 id、decision（same_intent|related|distinct）、reason、direction_title、direction_reason 五个字段，reason和direction_reason各不超过150字，不能遗漏后两个方向字段。即使无共同方向也必须返回空direction_title并说明direction_reason。same_intent须研究目标/具体问题相同且适用条件兼容，不要求标题字面相同。共享JEPA等对象不代表同问题：机制、应用、哲学是不同问题，应related；相反实验条件不能same_intent；存在不确定性用related。另外独立判断研究方向：返回 direction_title（不满足则空字符串）及 direction_reason。仅当双方role均为main，原始question明确以同一研究对象为主要讨论对象，且至少一问是方向、理论谱系、整体解读或应用探索等概览，才能形成有意义的共同研究方向；不同具体问题不妨碍同方向。例如世界模型方向概览与哲学世界模型可返回世界模型；JEPA整体解读与JEPA应用可返回JEPA。禁止仅因回答中提及同词、共享宽泛AI等领域、不同实验条件或相反目标而给出方向。方向标题简短且具体，不能以两个不同对象拼接。same_intent与方向判定互相独立，只建议，不执行合并。'},
        {'role':'user','content':json.dumps({'pairs':[dict(p.model_dump(),id=str(i)) for i,p in enumerate(request.pairs)],'context':request.context.model_dump()},ensure_ascii=False)}]})
    try:
        choice=result['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError()
        message=choice['message'];calls=message.get('tool_calls',[])
        if calls:
            if len(calls)!=1 or calls[0]['function']['name']!='deliver_intent_matches':raise ValueError()
            payload=calls[0]['function']['arguments']
        else:payload=message['content']
        decisions=json.loads(payload)['decisions']
        if not isinstance(decisions,list) or len(decisions)!=len(request.pairs):raise ValueError()
        for d in decisions:d['id']=str(d['id'])
        if {d['id'] for d in decisions}!={str(i) for i in range(len(request.pairs))}:raise ValueError()
        if any(d['decision'] not in ('same_intent','related','distinct') or not isinstance(d['reason'],str) or len(d['reason'])>1000 for d in decisions):raise ValueError()
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'意图判断返回结构无效') from None
    for d in decisions:
        pair=request.pairs[int(d['id'])]
        if pair.left.role==pair.right.role=='main' and ('direction_title' not in d or not d.get('direction_reason')):raise HTTPException(502,'研究方向判断字段缺失，不能静默跳过')
        title=d.get('direction_title','')
        reason=d.get('direction_reason','')
        if not isinstance(title,str) or len(title)>80 or not isinstance(reason,str) or len(reason)>1000:raise HTTPException(502,'研究方向判断返回结构无效')
        d['direction_title']=title.strip() if pair.left.role==pair.right.role=='main' else ''
        d['direction_reason']=reason
        d['id']=pair.id
    return {'decisions':decisions,'writes_performed':False,'validation_status':'proposal_only'}

@app.post('/intent-match')
def intent_match(request: IntentMatch):
    return intent_matches(IntentMatches(pairs=[IntentPair(id='pair',left=request.left,right=request.right)],context=request.context))['decisions'][0]

class ProjectRequest(StrictModel):
    vectors: list[list[float]] = Field(min_length=1,max_length=2000)

@app.post('/project')
def project(request: ProjectRequest):
    try:
        x=np.asarray(request.vectors,dtype=np.float64)
        if x.ndim!=2 or not 1<=x.shape[1]<=4096 or not np.isfinite(x).all():raise ValueError()
    except (TypeError,ValueError):raise HTTPException(422,'坐标须同维度且为有限数值') from None
    centered=x-x.mean(axis=0)
    if len(x)==1:return {'points':[{'x':0.0,'y':0.0}],'explained_variance':[0.0,0.0],'method':'PCA-SVD','dimension':x.shape[1]}
    _,singular,basis=np.linalg.svd(centered,full_matrices=False)
    k=min(2,len(singular));axes=basis[:k].copy()
    # Deterministic sign avoids random orientation flips for identical input.
    for axis in axes:
        if axis[np.argmax(np.abs(axis))]<0:axis*=-1
    pts=centered@axes.T
    if k<2:pts=np.pad(pts,((0,0),(0,2-k)))
    total=float(np.sum(singular**2));variance=(singular[:k]**2/total).tolist() if total else [0.0]*k
    variance+=[0.0]*(2-k)
    return {'points':[{'x':float(p[0]),'y':float(p[1])} for p in pts],'explained_variance':variance,'method':'PCA-SVD','dimension':x.shape[1],'warning':'显示投影不替代高维语义距离或结构归属'}

class ConceptSource(StrictModel):
    id: str
    text: str = Field(min_length=1,max_length=12000)
    topic: str = Field(min_length=1,max_length=200)
class ConceptsRequest(StrictModel):
    thoughts: list[ConceptSource] = Field(min_length=1,max_length=30)
@app.post('/concepts')
def extract_concepts(request: ConceptsRequest):
    if not os.environ.get('XUNXU_MODEL'):raise HTTPException(503,'提取历史核心概念需要配置模型')
    result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'max_tokens':2200,'response_format':{'type':'json_object'},'messages':[
        {'role':'system','content':'只提取所给科研思想中明确存在的核心概念，不能增加猜测或改变思想。JSON concepts数组，每项id与core_concepts（1至5个简短概念，保留原文专有名称）。不要将整句当一个概念。'},
        {'role':'user','content':json.dumps({'thoughts':[dict(t.model_dump(),id=str(i)) for i,t in enumerate(request.thoughts)]},ensure_ascii=False)}]})
    try:
        rows=json.loads(result['choices'][0]['message']['content'])['concepts']
        if len(rows)!=len(request.thoughts) or {r['id'] for r in rows}!={str(i) for i in range(len(request.thoughts))}:raise ValueError()
        for r in rows:
            cs=r['core_concepts']
            if not isinstance(cs,list) or not 1<=len(cs)<=20 or any(not isinstance(c,str) or not c.strip() or len(c)>100 for c in cs):raise ValueError()
            r['core_concepts']=cs[:5]
            r['id']=request.thoughts[int(r['id'])].id
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'核心概念提取结果无效') from None
    return {'concepts':rows,'writes_performed':False}

class ResearchTurnRequest(ChatRequest):
    qa_id: str
    intent_catalog: list[str] = Field(default_factory=list,max_length=1000)

@app.post('/research-turn')
def research_turn(request: ResearchTurnRequest):
    """One provider request returns user answer and machine-readable thoughts together."""
    model=os.environ.get('XUNXU_MODEL')
    if not model:raise HTTPException(503,'尚未配置 XUNXU_MODEL。')
    system=('你是循序科研助手，使用准入的祖先路径、当前节点背景及本会话历史连续交流。历史仅理解指代，不代表父节点已接受的结论；区分事实、假设和未执行实验，不引入其他会话或子孙总结。'
        '仅通过 deliver_research_turn 函数返回完整结果，函数参数是 JSON 对象：answer 是给用户的完整自然语言回答（可含 Markdown）；thoughts 是本轮回答对应的1至3个科研思想，第一项主要思想必须保留用户当前问题的整体研究意图：方向概览应概括方向探索，整体解读应概括对象机制，不要用回答中的一个争议或子问题取代；其余辅助思想。'
        '每项包含 text、topic、excerpt、core_concepts。text 为具体思想的完整语义表述；topic 为简短稳定的具体研究问题；core_concepts 为1至5个短核心概念。'
        '同问题同条件可复用已知 topic，但不能仅因共享关键词复用。只提取本轮问答内容，不重复历史。excerpt 必须逐字复制当前问题或本轮 answer 中的一段连续原文，不能改写或摘取历史回答；不确定时填空字符串。'
        '不得把假设写成已证结论，不提出结构移动。不要在 answer 中解释 thoughts 或 JSON 格式。用户的字数、只回复数字等要求仅约束 answer 字段，不能省略 JSON 封装和 thoughts。'
        '格式示例：{"answer":"表征预测值得研究。","thoughts":[{"text":"研究表征预测机制","topic":"表征预测机制","excerpt":"表征预测","core_concepts":["表征预测"]}]}。示例仅说明格式，内容必须基于当前问题。\n'
        +json.dumps({'context':request.context.model_dump(),'known_intents':request.intent_catalog},ensure_ascii=False))
    messages=[{'role':'system','content':system}]
    for turn in request.history:messages.extend([{'role':'user','content':turn.question},{'role':'assistant','content':turn.answer}])
    messages.append({'role':'user','content':json.dumps({'question':request.question,'output_contract':'以 JSON 返回 answer 和 thoughts；问题中的输出限制仅作用于 answer 字段。'},ensure_ascii=False)})
    schema={'type':'object','additionalProperties':False,'required':['answer','thoughts'],'properties':{'answer':{'type':'string','description':'给用户的回答，用户的简短/数字要求只约束该字段'},'thoughts':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','additionalProperties':False,'required':['text','topic','excerpt','core_concepts'],'properties':{'text':{'type':'string'},'topic':{'type':'string'},'excerpt':{'type':'string','description':'逐字来自当前问题或answer'},'core_concepts':{'type':'array','minItems':1,'maxItems':5,'items':{'type':'string'}}}}}}}
    result=provider_request('chat/completions',{'model':model,'temperature':0.2,'max_tokens':8192,'messages':messages,'tools':[{'type':'function','function':{'name':'deliver_research_turn','description':'一次返回科研回答与本轮思想；仅传递数据，不执行外部操作','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_research_turn'}}})
    try:
        choice=result['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError()
        calls=choice['message'].get('tool_calls')
        if calls is not None:
            if len(calls)!=1 or calls[0]['function']['name']!='deliver_research_turn':raise ValueError()
            payload=calls[0]['function']['arguments']
        else:payload=choice['message']['content']
        raw=json.loads(payload);answer=raw['answer'];rows=raw['thoughts']
        if not isinstance(answer,str) or not answer.strip() or len(answer)>60000:raise ValueError()
        if not isinstance(rows,list) or not 1<=len(rows)<=3:raise ValueError()
        specs=[]
        validation_warnings=[]
        for index,t in enumerate(rows):
            concepts=t['core_concepts']
            if not isinstance(concepts,list) or not 1<=len(concepts)<=20 or any(not isinstance(c,str) or not c.strip() or len(c)>100 for c in concepts):raise ValueError()
            spec=ThoughtInput(text=t['text'],topic=t['topic'],excerpt=t.get('excerpt',''),core_concepts=concepts[:5],independent=False)
            if spec.excerpt and spec.excerpt not in request.question and spec.excerpt not in answer:
                spec.excerpt=''
                validation_warnings.append({'thought_index':index,'code':'unverified_excerpt_removed'})
            specs.append(spec)
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'回答与思想的合并结果不合法或被截断；未追加模型请求，研究数据未提交。') from None
    analysis=analyze(AnalyzeRequest(qa_id=request.qa_id,question=request.question,answer=answer,context=request.context,thoughts=specs))
    return {'answer':answer,'analysis':analysis,'generation':{'model':model,'mode':'combined-answer-and-thoughts','answer_extraction_requests':1,'usage':result.get('usage',{}),'validation_warnings':validation_warnings},'writes_performed':False}

class GrowthPlacementsRequest(StrictModel):
    requests: list[dict] = Field(min_length=1,max_length=10)

@app.post('/growth-placements')
def growth_placements(request: GrowthPlacementsRequest):
    """Read only ordered evidence and measured candidates; Java owns graph writes."""
    if len({row.get('id') for row in request.requests})!=len(request.requests):raise HTTPException(422,'生长判断id重复')
    if not os.environ.get('XUNXU_MODEL'):
        return {'decisions':[{'id':row['id'],'decision':'uncertain','parent_id':None,'reason':'模型未配置，保留现有结构'} for row in request.requests],'writes_performed':False}
    proposals=[]
    for i,row in enumerate(request.requests):
        candidates=row.get('candidates',[])
        if not 1<=len(candidates)<=5:raise HTTPException(422,'父节点候选数量无效')
        proposals.append({'id':str(i),'child':{k:v for k,v in row.get('child',{}).items() if k!='node_id'},'candidates':[dict(c,node_id=str(j)) for j,c in enumerate(candidates)],'sequence':row.get('sequence',[])})
    schema={'type':'object','additionalProperties':False,'required':['decisions'],'properties':{'decisions':{'type':'array','minItems':1,'maxItems':10,'items':{'type':'object','additionalProperties':False,'required':['id','decision','parent_id','reason','branch_start_turn','parent_evidence_turns'],'properties':{'id':{'type':'string'},'decision':{'type':'string','enum':['deepen','continue','switch','uncertain']},'parent_id':{'type':['string','null']},'reason':{'type':'string'},'branch_start_turn':{'type':['integer','null']},'parent_evidence_turns':{'type':'array','items':{'type':'integer'}}}}}}}
    result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':6000,'tools':[{'type':'function','function':{'name':'deliver_growth_placements','description':'返回只读科研路径判断，不执行结构操作','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_growth_placements'}},'messages':[
        {'role':'system','content':'你是科研路径归属判断器，仅调用 deliver_growth_placements 返回 JSON decisions 数组，每项必须含 id、decision（deepen|continue|switch|uncertain）、parent_id、reason、branch_start_turn（深入分支正式展开的轮次，否则null）、parent_evidence_turns（真正支持祖先关系的前序轮次列表，否则空数组）。根据同一会话按顺序的真实问题、回答片段和候选高维余弦值判断研究演化。deepen 表示当前节点是前序候选研究方向/问题的进一步展开，parent_id必须是该项请求候选中显示的局部node_id（例如字符串0），不得引用其他请求的节点、真实节点ID或会话ID。每一项只判断自己的child，不得把另一项的child代入。continue表示同一具体问题延续，不据此再挂一层；switch表示转向独立研究方向；uncertain表示证据不足。后三种parent_id必须为null。会话锚点只是历史起点，不是所有节点的父节点。顺序只是研究因果候选，不能把每个后续问题机械挂在上一节点；余弦也不是父子关系证明。必须结合前文是否明确建立研究范围、后文是否在该范围内探索子机制或方法。例：先探索世界模型及其哲学，再深度讨论JEPA与其应用，若回答和语义证据支持，则JEPA是世界模型的深入分支；不能仅因JEPA可被用于世界模型而无条件建立该层级。节点最早支持证据不等于正式分支起点：早期回答中的辅助提及可以支持后来形成的分支，却不能把分支起点提前。例如第1轮世界模型回答顺带提到JEPA，第3轮才明确要求深入解读JEPA，则branch_start_turn=3，parent_evidence_turns应是此前建立世界模型范围的第1、2轮。候选evidence可以包含早期辅助证据，判断祖先只能使用早于branch_start_turn的真实轮次，不能把未来问答、其他会话或子孙总结当成祖先依据。明确切换主题则switch；不确定宁可保留结构。reason必须引用问答轮次和语义依据，控制在200字内。parent_evidence_turns必须逐项检查是否确实存在于所选候选的evidence中且早于branch_start_turn；不满足时返回uncertain，禁止猜测轮次。只建议，不执行移动。'},
        {'role':'user','content':json.dumps({'requests':proposals},ensure_ascii=False)}]})
    try:
        choices=result['choices']
        if choices[0].get('finish_reason')=='length':raise ValueError()
        message=choices[0]['message'];calls=message.get('tool_calls',[])
        if calls:
            if len(calls)!=1 or calls[0]['function']['name']!='deliver_growth_placements':raise ValueError()
            payload=calls[0]['function']['arguments']
        else:payload=message['content']
        rows=json.loads(payload)['decisions']
        if not isinstance(rows,list) or len(rows)!=len(proposals) or {str(r['id']) for r in rows}!={str(i) for i in range(len(proposals))}:raise ValueError()
        output=[]
        for row in rows:
            original=request.requests[int(row['id'])];kind=row['decision'];reason=row['reason'];parent=row.get('parent_id')
            if kind not in ('deepen','continue','switch','uncertain') or not isinstance(reason,str) or not reason.strip() or len(reason)>2000:raise ValueError()
            invalid=None
            if kind=='deepen':
                if str(parent) not in {str(i) for i in range(len(original['candidates']))}:
                    invalid='父节点不在本项准入候选中'
                else:
                    candidate=original['candidates'][int(parent)]
                    focus=row.get('branch_start_turn');basis=row.get('parent_evidence_turns')
                    if not isinstance(focus,int) or isinstance(focus,bool) or focus not in {t['turn_index'] for t in original['sequence']}:
                        invalid='分支起点不是有效的原会话轮次'
                    else:
                        allowed={t['turn_index'] for t in candidate['evidence'] if t['turn_index']<focus}
                        if not isinstance(basis,list) or not basis or any(not isinstance(t,int) or isinstance(t,bool) or t not in allowed for t in basis):
                            invalid='祖先依据不属于候选的前序证据'
                    if not invalid:parent=candidate['node_id']
            elif parent is not None:invalid='非深入判断不允许指定父节点'
            if invalid:
                kind='uncertain';parent=None
                reason='归属建议未通过证据校验，保留现有结构：'+invalid+'。模型原判断：'+reason
            output.append({'id':original['id'],'decision':kind,'parent_id':parent,'reason':reason,'branch_start_turn':row.get('branch_start_turn') if kind=='deepen' else None,'parent_evidence_turns':row.get('parent_evidence_turns',[]) if kind=='deepen' else []})
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'研究生长归属返回结构无效') from None
    return {'decisions':output,'writes_performed':False,'validation_status':'proposal_only'}
