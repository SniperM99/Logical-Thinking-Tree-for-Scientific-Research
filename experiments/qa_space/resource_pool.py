"""Pending QA resources are placed at AI-suggested nodes, without graph edges."""
import json,re
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]/'.runtime/experiments/robot-qa-v1'
def build_pool(rows,pending,nodes,cores,names):
 idx={r['qa_id']:i for i,r in enumerate(rows)};attached={n['qa_id'] for n in nodes};pools={};stream=[];records=[]
 for p in pending:
  key=p['qa_id'];i=idx[key];r=rows[i];previous=rows[i-1]['qa_id'] if i else None;suggestion=p.get('proposal',{}).get('parent_id');anchor=suggestion if suggestion in attached else None
  record={**p,**r,'id':names[key],'core':cores[key],'previous_qa_id':previous,'suggested_node_id':suggestion,'storage_anchor':anchor,'storage_scope':'node_pending_resources' if anchor else 'unplaced_resources','status':'待判定，非父子关系','conversation_boundary_known':False}
  records.append(record)
  if anchor:pools.setdefault(anchor,[]).append(key)
  else:stream.append(key)
 assert len(records)==len(pending) and len({r['qa_id'] for r in records})==len(records)
 return {'records':records,'node_pools':pools,'stream_pool':stream}
def main():
 rows=[json.loads(l) for l in (BASE/'inputs/qa.jsonl').read_text().splitlines()];labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];cores={r['qa_id']:r['core'] for r in map(json.loads,(BASE/'descriptors/core.jsonl').read_text().splitlines())};names={l['qa_id']:l['original_id'] for l in labels};g=json.loads((BASE/'relation-v2/graph.json').read_text());pool=build_pool(rows,g['pending'],g['nodes'],cores,names)
 (BASE/'relation-v2/resource-pool.json').write_text(json.dumps(pool,ensure_ascii=False,indent=2))
 page=Path('.runtime/exports/research-tree-relation-v2.html');s=page.read_text();s=re.sub(r'// RESOURCE_POOL_START.*?// RESOURCE_POOL_END', '', s, flags=re.S);payload=json.dumps(pool,ensure_ascii=False).replace('</','<\\/')
 js='''
const resourcePool=__POOL__;
const resourceById=new Map(resourcePool.records.map(r=>[r.qa_id,r]));
function resourceCard(r){const suggestion=r.suggested_node_id;return '<article style="border:1px solid #ccd6dc;border-radius:8px;padding:12px;margin:10px 0"><h3>'+esc(r.id+' · '+r.question)+'</h3><span class="tag">待判定资源 · 非父子关系</span><p>'+esc(r.core)+'</p><p class="meta">'+esc(r.reason)+'<br>AI建议归属：'+esc(byId.get(suggestion)?.id||resourceById.get(suggestion)?.id||suggestion||'未确定')+'</p><details><summary>查看完整原始问答</summary><p>'+esc(r.question)+'</p><div class="answer">'+esc(r.answer)+'</div></details></article>'}
function pendingSection(key){const keys=resourcePool.node_pools[key]||[];return keys.length?'<h3>待判定资源池 · '+keys.length+'</h3><p class="meta">按 AI 建议归属放置；尚未确认为父子关系。</p>'+keys.map(k=>resourceCard(resourceById.get(k))).join(''):''}
const originalSelect=select;
select=function(key,locate=false){originalSelect(key,locate);document.getElementById('detail').insertAdjacentHTML('beforeend',pendingSection(key))};
document.getElementById('pending').textContent='待判定资源池 '+resourcePool.records.length;
document.getElementById('pendingContent').innerHTML='<p>所有未入树问答均保留。节点暂存 '+resourcePool.records.filter(r=>r.storage_anchor).length+' 条；未放置公共池 '+resourcePool.stream_pool.length+' 条。建议目标尚未入树或没有建议目标时保留在公共池，不建立父子边。</p>'+resourcePool.records.map(resourceCard).join('');
'''.replace('__POOL__',payload)
 marker='new ResizeObserver(()=>';assert marker in s;s=s.replace(marker,'// RESOURCE_POOL_START\n'+js+'\n// RESOURCE_POOL_END\n'+marker,1)
 page.write_text(s);print('Pending resources',len(pool['records']),'node anchored',sum(len(v) for v in pool['node_pools'].values()),'stream',len(pool['stream_pool']))
if __name__=='__main__':main()
