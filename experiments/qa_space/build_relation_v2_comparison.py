# Render private experiment results using the tracked, data-free upward tree template.
import json,re,csv,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--variant',default='relation-v2');variant=parser.parse_args().variant
b=Path('.runtime/experiments/robot-qa-v1');graph=json.loads((b/variant/'graph.json').read_text());old=json.loads((b/'conversation-graph/graph.json').read_text());rep=graph['report'];nodes=graph['nodes'];idx={n['qa_id']:n for n in nodes};oldidx={n['qa_id']:n for n in old['nodes']};levels={'smart-manufacturing':0}
for n in nodes:
 if n['parent']:levels[n['qa_id']]=levels[n['parent']]+1
 n['level']=levels[n['qa_id']]
graph['pending_records']=graph['pending'];graph['source_records']=[]
source=(Path(__file__).resolve().parent/'tree-template.html').read_text();source=re.sub(r'(<script type="application/json" id="data">).*?(</script>)',lambda m:m[1]+json.dumps(graph,ensure_ascii=False).replace('</','<\\/')+m[2],source,count=1,flags=re.S)
source=source.replace('循序 · 智能制造单根研究树','循序 · 关系判别 V2 研究树');source=re.sub(r'<div class="meta">智能制造 · 唯一根节点.*?</div>',f'<div class="meta">关系判别 V2 实验 · {rep["attached_qa"]} 个已关联问答 · {rep["pending_qa"]} 个待复核 · {rep["cross_links"]} 条交叉虚线 · 分数尚未校准</div>',source,count=1)
source=source.replace('AI 推断父子关系 · 点击节点查看依据','实线：逻辑承接优先，检索补充').replace('实验结构，尚未独立验证','虚线：第二、第三名的明确交叉关系')
source=source.replace('<button id="pending">待复核 2</button>',f'<button id="pending">待复核 {rep["pending_qa"]}</button><label><input type="checkbox" id="allCross" style="width:auto">全部可见虚线</label>')
source=source.replace("document.getElementById('sources').innerHTML='';",'''const types={sibling:'并列研究',method:'方法借鉴',inspiration:'综合启发',validation_dependency:'验证依赖'};
 const shown=(data.links||[]).filter(l=>pos.has(l.source)&&pos.has(l.target)&&(document.getElementById('allCross').checked||l.source===selected||l.target===selected));
 document.getElementById('sources').innerHTML=shown.map(l=>{const a=pos.get(l.source),b=pos.get(l.target),x=(a.x+b.x)/2,y=(a.y+b.y)/2-40;return '<path class="source-link" d="M'+a.x+','+a.y+' Q'+x+','+y+' '+b.x+','+b.y+'"/><text x="'+x+'" y="'+y+'" text-anchor="middle" fill="var(--text)" stroke="var(--panel)" stroke-width="4" paint-order="stroke" style="font-size:12px">'+types[l.type]+'</text>'}).join('');''')
source=source.replace("function select(key,locate=false){selected=key;", "function select(key,locate=false){selected=key;(data.links||[]).filter(l=>l.source===key||l.target===key).forEach(l=>{reveal(l.source);reveal(l.target)});")
source=source.replace("'<h3>连线依据</h3>","'<h3>连线依据</h3>")
needle="+'<h3>引用片段</h3>'" # Direct insertion into the concatenated panel.
source=source.replace("+'<h3>引用片段</h3><p>'", "+(n.score!=null?'<p class=\"meta\">父节点适配分 '+n.score+' · 与第二名差 '+n.score_margin+'（未校准）</p>':'')+'<h3>引用片段</h3><p>'")
source=source.replace("+'<h3>完整原始回答</h3>'", "+'<h3>完整原始回答</h3>'")
source=source.replace("+'<h3>完整原始回答</h3><div class=\"answer\">'", "+((data.links||[]).filter(l=>l.source===key).length?'<h3>交叉关联</h3>'+data.links.filter(l=>l.source===key).map(l=>'<p>'+({sibling:'并列研究',method:'方法借鉴',inspiration:'综合启发',validation_dependency:'验证依赖'})[l.type]+' → '+byId.get(l.target).id+'<br>第二/第三名位置：'+l.rank+' · 关联分 '+l.score+'<br>'+esc(l.reason)+'</p>').join(''):'')+'<h3>完整原始回答</h3><div class=\"answer\">'")
source=source.replace('校验未通过：引用片段未在关联两端逐字找到，暂不绘制连线。','未确认逻辑承接、引用依据，或父节点仍待复核。')
source=source.replace("['用户指定主题']","(n.score!=null?['当前或父候选的原文/核心描述']:['用户指定主题'])")
source=source.replace("new ResizeObserver(()=>", "document.getElementById('allCross').onchange=()=>draw();new ResizeObserver(()=>")
source=source.replace('实线：逻辑承接优先，检索补充','实线：研究目标包含检查').replace('虚线：第二、第三名的明确交叉关系','虚线：沿用原评分结果，未独立验证')
source=source.replace("+'<h3>引用片段</h3><p>'","+(n.relation_analysis?'<h3>研究目标对比</h3><p>当前：'+esc(n.relation_analysis.current_goal||'')+'<br>上位：'+esc(n.relation_analysis.parent_goal||'')+'</p><h3>为何是包含或并列</h3><p>'+esc(n.relation_analysis.containment_explanation||'')+'</p><h3>排除另一种关系的理由</h3><p>'+esc(n.relation_analysis.alternative_explanation||'')+'</p>':'')+'<h3>引用片段</h3><p>'")
Path('.runtime/exports/research-tree-relation-v2.html').write_text(source)
# Compare to the prior single-root AI graph; original spreadsheet annotations remain a third reference.
raw_labels=[json.loads(l) for l in (b/'evaluation/labels.jsonl').read_text().splitlines()];names={l['qa_id']:l['original_id'] for l in raw_labels};names['smart-manufacturing']='智能制造';pending={p['qa_id']:p for p in graph['pending']};eligible=[l for l in raw_labels if l['node_type']!='外领域问题'];changes=[]
for l in eligible:
 key=l['qa_id'];new=idx.get(key);prev=oldidx.get(key);changes.append({'id':l['original_id'],'question':l['metadata']['问题'] if '问题' in l['metadata'] else (new or prev or pending[key])['question'],'old':names.get(prev['parent']) if prev else '待复核','new':names.get(new['parent']) if new else '待复核','original':names.get(l['parent_qa_id']) if l['parent_qa_id'] else '无父标注','status':'父节点一致' if new and prev and new['parent']==prev['parent'] else '父节点变化' if new and prev else '本轮待复核' if not new else '新增关联'})
with (b/variant/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['节点','问题','旧单根AI父节点','评分树父节点','原表父标注','变化'])
 for r in changes:w.writerow([r['id'],r['question'],r['old'],r['new'],r['original'],r['status']])
# One connected root, chronological solid edges, two cross-links at most per source.
assert len([n for n in nodes if not n['parent']])==1
for n in nodes:
 if n['parent']:assert idx[n['parent']]['sequence']<n['sequence']
for l in graph['links']:assert l['source'] in idx and l['target'] in idx and l['rank'] in [2,3]
statuses={s:sum(r['status']==s for r in changes) for s in {r['status'] for r in changes}};(b/variant/'comparison-summary.json').write_text(json.dumps(statuses,ensure_ascii=False,indent=2))
rows=''.join('<tr><td>'+r['id']+'</td><td>'+r['old']+'</td><td>'+r['new']+'</td><td>'+r['status']+'</td></tr>' for r in changes if r['status']!='父节点一致')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>研究树构建对照</title><style>body{font:14px/1.6 system-ui;margin:0;background:#f5f7fb;color:#223246}header{padding:16px 20px;background:white}h1{font-size:21px;margin:0}a{color:#1669c6}main{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px}iframe{width:100%;height:780px;border:1px solid #cbd6e3;background:white}h2{font-size:17px;padding:0 10px}details{padding:16px 20px}table{width:100%;border-collapse:collapse}td,th{padding:8px;text-align:left;border-bottom:1px solid #d6deea}@media(max-width:900px){main{grid-template-columns:1fr}iframe{height:900px}}</style><header><h1>会话承接版与关系判别 V2 对照</h1><p>左：上一版会话承接优先树。右：增加研究目标包含检查，对比拟定父问题与共同上位，区分深化和并列。检索策略未改变；原表父子标注未用于预测。</p><p>本轮按原始时间流测试，真实会话边界未知。要求给出两端研究目标、包含解释和替代关系解释；引用真实不等于语义正确。数据仍按时间流测试，问答粒度保持不变，属于探索实验。</p><p><a href="research-tree-conversation.html" target="_blank">单独打开旧图</a> · <a href="research-tree-relation-v2.html" target="_blank">单独打开新图</a> · <a href="research-tree-reference.html" target="_blank">原表标注图</a></p>__SUMMARY__</header><main><section><h2>会话承接基线结构</h2><iframe src="research-tree-conversation.html" title="会话承接基线结构"></iframe></section><section><h2>关系判别 V2 结构</h2><iframe src="research-tree-relation-v2.html" title="关系判别 V2 结构"></iframe></section></main><details><summary>父节点变化与待复核列表</summary><table><thead><tr><th>节点</th><th>旧父节点</th><th>评分父节点</th><th>状态</th></tr></thead><tbody>__ROWS__</tbody></table></details></html>'''
html=html.replace('__SUMMARY__',f'<p>评分树：{rep["attached_qa"]} 个已关联问答，{rep["pending_qa"]} 个待复核，{rep["cross_links"]} 条虚线。'+ '；'.join(f'{k} {v}' for k,v in statuses.items())+'</p>').replace('__ROWS__',rows);Path('.runtime/exports/research-tree-relation-v2-comparison.html').write_text(html);print(rep);print(statuses)
