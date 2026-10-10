#!/usr/bin/env python3
"""Check real user measurements without changing original evidence."""
import json,math,urllib.request
from pathlib import Path
BASE='http://127.0.0.1:8080'
def get(path):
 with urllib.request.urlopen(BASE+path,timeout=70) as r:return json.load(r)
before=json.loads(Path('.runtime/thought-space-before.json').read_text());sid=before['space_id'];after=get('/api/state?space_id='+sid);space=get('/api/thought-space?space_id='+sid)
assert {q['id']:q for q in before['qas']}=={q['id']:q for q in after['qas']}
assert {t['id']:t for t in before['thoughts']}=={t['id']:t for t in after['thoughts']}
assert before['conversations']==after['conversations']
assert before['nodes'][0]['summary']==next(n for n in after['nodes'] if n['id']==before['nodes'][0]['id'])['summary']
assert space['model']['semantic'] and space['model']['dimension']==512
assert len(space['points'])==len(before['thoughts'])==12
concept_count=0
for point in space['points']:
 assert all(math.isfinite(point[k]) for k in ['x','y'])
 for c in point['concept_coordinates']:
  assert len(c['vector'])==512 and abs(sum(v*v for v in c['vector'])-1)<1e-5
  concept_count+=1
for pair in space['pairs']:
 assert abs(pair['distance']-(1-pair['similarity']))<1e-10
 assert -1<=pair['similarity']<=1
same=[p for p in space['pairs'] if p['decision']=='same_intent'];related=[p for p in space['pairs'] if p['decision']=='related'];assert same and related
new=[n for n in after['nodes'] if n['id'] not in {b['id'] for b in before['nodes']}]
assert len(new)==1 and new[0]['creation_type']=='semantic_cluster'
report={'passed':True,'qa_evidence_unchanged':True,'birth_coordinates_unchanged':True,'conversation_anchor_unchanged':True,'parent_summary_unchanged':True,'model':space['model'],'thought_coordinates':12,'core_concept_coordinates':concept_count,'same_intent_pairs':len(same),'related_pairs':len(related),'created_nodes':[{'id':n['id'],'title':n['title']} for n in new],'same_intent_similarity':[round(p['similarity'],6) for p in same]}
Path('docs/semantic-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
