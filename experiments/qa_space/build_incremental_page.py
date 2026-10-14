"""Render persisted positions and incremental resources; does not compute tree layout."""
import json,re
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]/'.runtime/experiments/robot-qa-v1'
def main():
 g=json.loads((BASE/'incremental-growth/graph.json').read_text());labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];names={r['qa_id']:r['original_id'] for r in labels}
 for r in g['nodes']+g['resources']+g['pending']+g['outside']:
  r['id']=names.get(r['qa_id'],r['id'])
 g['pending_records']=g['pending'];g['source_records']=[];s=(Path(__file__).parent/'tree-template.html').read_text();s=re.sub(r'(<script type="application/json" id="data">).*?(</script>)',lambda m:m[1]+json.dumps(g,ensure_ascii=False).replace('</','<\\/')+m[2],s,count=1,flags=re.S)
 s=s.replace('循序 · 智能制造单根研究树','循序 · 严格逐条增量生长树');evaluation_path=BASE/'incremental-growth/evaluation.json'
 if evaluation_path.exists():
  ev=json.loads(evaluation_path.read_text());stats=g['report']['stats'];warning=f'<p style="padding:10px;background:#fff1de;color:#754316">实验限制：86条原表父边匹配 {ev["matched_created_node_parent"]} 条；域外13条仅识别 {ev["scope_correct_outside"]} 条。增量机制已验证，语义判别未达到可替换基线的质量。模型请求 {stats["model_requests"]} 次，扩大检索 {stats["global_queries"]} 次。坐标固定，父关系只追加。当前为离线时间流，无真实会话ID；尚未接入平台。</p>';s=s.replace('</header>',warning+'</header>',1)
 s=s.replace('待复核 2',f"资源池 {len(g['resources'])+len(g['pending'])}")
 s=re.sub(r'<div class="meta">智能制造 · 唯一根节点.*?</div>',f'<div class="meta">逐条提交 {g["report"]["processed"]} 问答 · {len(g["nodes"])-1} 节点 · {len(g["resources"])} 同问题资源 · {len(g["pending"])} 待判定 · {len(g["outside"])} 域外 · 旧节点位置与边未改写</div>',s,count=1)
 a=s.index('  place(root,0);');b=s.index('  const paths=',a)
 s=s[:a]+'''  function collect(n){visible.push(n);pos.set(n.qa_id,{...n.position,depth:n.depth||0});if(expanded.has(n.qa_id))(children.get(n.qa_id)||[]).forEach(collect)}
  collect(root);
'''+s[b:]
 s=s.replace("function fitAll(){fitArea({x:0,y:0,width:totalWidth,height:totalHeight})}","function fitAll(){const xs=visible.map(n=>pos.get(n.qa_id).x),ys=visible.map(n=>pos.get(n.qa_id).y);fitArea({x:Math.min(...xs)-110,y:Math.min(...ys)-60,width:Math.max(...xs)-Math.min(...xs)+220,height:Math.max(...ys)-Math.min(...ys)+120})}")
 s=s.replace("Math.max(0,p.x-340)","p.x-340").replace("Math.max(0,p.y-340)","p.y-340")
 start=s.index("document.getElementById('pendingContent').innerHTML=");end=s.index("document.getElementById('pending').onclick",start)
 s=s[:start]+'''function card(r){return '<article style="border:1px solid #ccd6dc;border-radius:8px;padding:12px;margin:8px 0"><h3>'+esc(r.id+' · '+r.question)+'</h3><p>'+esc(r.status||'未归属')+' · '+esc(r.reason)+'</p><p>'+esc(r.core)+'</p><details><summary>完整问答</summary><p>'+esc(r.question)+'</p><div class="answer">'+esc(r.answer)+'</div></details></article>'}
const allResources=[...data.resources,...data.pending];
document.getElementById('pendingContent').innerHTML=allResources.map(card).join('')||'<p>暂无资源</p>';
const baseSelect=select;select=function(key,locate=false){baseSelect(key,locate);const records=allResources.filter(r=>r.storage_anchor===key);document.getElementById('detail').insertAdjacentHTML('beforeend',records.length?'<h3>节点资源池</h3>'+records.map(card).join(''):'')};
'''+s[end:]
 # Show archived out-of-scope evidence without adding graph nodes.
 s=s.replace('<button id="pending">', '<button id="outsideButton">域外档案</button><button id="pending">')
 s=s.replace('new ResizeObserver(()=>',"document.getElementById('outsideButton').onclick=()=>{document.getElementById('pendingContent').innerHTML=data.outside.map(card).join('')||'暂无域外问答';pendingDialog.showModal()};document.getElementById('pending').onclick=()=>{document.getElementById('pendingContent').innerHTML=allResources.map(card).join('')||'暂无资源';pendingDialog.showModal()};new ResizeObserver(()=>")
 Path('.runtime/exports/research-tree-incremental.html').write_text(s)
 print('Rendered persisted positions',len(g['nodes']))
if __name__=='__main__':main()
