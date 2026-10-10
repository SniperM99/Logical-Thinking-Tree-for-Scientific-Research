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
    vectors, method, semantic = coordinates([t.text for t in specs])
    thoughts = []
    for index,(spec,vector) in enumerate(zip(specs,vectors)):
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
                         'coordinate_method':method,'semantic_embedding':semantic,'proposal':proposal})
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
    result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'max_tokens':2200,'response_format':{'type':'json_object'},'messages':[
        {'role':'system','content':'判断研究意图是否相同。仅返回 JSON decisions数组，各项id、decision（same_intent|related|distinct）、短reason。same_intent须研究目标/具体问题相同且适用条件兼容，不要求标题字面相同。共享JEPA等对象不代表同问题：机制、应用、哲学是不同问题，应related；相反实验条件不能same_intent；存在不确定性用related。只建议，不执行合并。'},
        {'role':'user','content':json.dumps({'pairs':[dict(p.model_dump(),id=str(i)) for i,p in enumerate(request.pairs)],'context':request.context.model_dump()},ensure_ascii=False)}]})
    try:
        decisions=json.loads(result['choices'][0]['message']['content'])['decisions']
        if not isinstance(decisions,list) or len(decisions)!=len(request.pairs):raise ValueError()
        if {d['id'] for d in decisions}!={str(i) for i in range(len(request.pairs))}:raise ValueError()
        if any(d['decision'] not in ('same_intent','related','distinct') or not isinstance(d['reason'],str) or len(d['reason'])>1000 for d in decisions):raise ValueError()
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'意图判断返回结构无效') from None
    for d in decisions:d['id']=request.pairs[int(d['id'])].id
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
        '仅通过 deliver_research_turn 函数返回完整结果，函数参数是 JSON 对象：answer 是给用户的完整自然语言回答（可含 Markdown）；thoughts 是本轮回答对应的1至3个科研思想，第一项主要思想，其余辅助思想。'
        '每项包含 text、topic、excerpt、core_concepts。text 为具体思想的完整语义表述；topic 为简短稳定的具体研究问题；core_concepts 为1至5个短核心概念。'
        '同问题同条件可复用已知 topic，但不能仅因共享关键词复用。只提取本轮问答内容，不重复历史。excerpt 必须逐字来自当前问题或本次 answer。'
        '不得把假设写成已证结论，不提出结构移动。不要在 answer 中解释 thoughts 或 JSON 格式。用户的字数、只回复数字等要求仅约束 answer 字段，不能省略 JSON 封装和 thoughts。'
        '格式示例：{"answer":"表征预测值得研究。","thoughts":[{"text":"研究表征预测机制","topic":"表征预测机制","excerpt":"表征预测","core_concepts":["表征预测"]}]}。示例仅说明格式，内容必须基于当前问题。\n'
        +json.dumps({'context':request.context.model_dump(),'known_intents':request.intent_catalog},ensure_ascii=False))
    messages=[{'role':'system','content':system}]
    for turn in request.history:messages.extend([{'role':'user','content':turn.question},{'role':'assistant','content':turn.answer}])
    messages.append({'role':'user','content':json.dumps({'question':request.question,'output_contract':'以 JSON 返回 answer 和 thoughts；问题中的输出限制仅作用于 answer 字段。'},ensure_ascii=False)})
    schema={'type':'object','additionalProperties':False,'required':['answer','thoughts'],'properties':{'answer':{'type':'string','description':'给用户的回答，用户的简短/数字要求只约束该字段'},'thoughts':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','additionalProperties':False,'required':['text','topic','excerpt','core_concepts'],'properties':{'text':{'type':'string'},'topic':{'type':'string'},'excerpt':{'type':'string','description':'逐字来自当前问题或answer'},'core_concepts':{'type':'array','minItems':1,'maxItems':5,'items':{'type':'string'}}}}}}}
    result=provider_request('chat/completions',{'model':model,'temperature':0.2,'max_tokens':3600,'messages':messages,'tools':[{'type':'function','function':{'name':'deliver_research_turn','description':'一次返回科研回答与本轮思想；仅传递数据，不执行外部操作','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'deliver_research_turn'}}})
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
        for t in rows:
            concepts=t['core_concepts']
            if not isinstance(concepts,list) or not 1<=len(concepts)<=20 or any(not isinstance(c,str) or not c.strip() or len(c)>100 for c in concepts):raise ValueError()
            spec=ThoughtInput(text=t['text'],topic=t['topic'],excerpt=t.get('excerpt',''),core_concepts=concepts[:5],independent=False)
            if spec.excerpt and spec.excerpt not in request.question and spec.excerpt not in answer:raise ValueError()
            specs.append(spec)
    except (KeyError,TypeError,IndexError,ValueError):raise HTTPException(502,'回答与思想的合并结果不合法或被截断；未追加模型请求，研究数据未提交。') from None
    analysis=analyze(AnalyzeRequest(qa_id=request.qa_id,question=request.question,answer=answer,context=request.context,thoughts=specs))
    return {'answer':answer,'analysis':analysis,'generation':{'model':model,'mode':'combined-answer-and-thoughts','answer_extraction_requests':1,'usage':result.get('usage',{})},'writes_performed':False}
