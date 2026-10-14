import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]/'.runtime/experiments/robot-qa-v1'
def main():
 g=json.loads((BASE/'incremental-growth/graph.json').read_text());labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];idx={n['qa_id']:n for n in g['nodes']};gold=[l for l in labels if l['parent_qa_id']];outside={l['qa_id'] for l in labels if l['node_type']=='外领域问题'};predoutside={r['qa_id'] for r in g['outside']};matches=sum(l['qa_id'] in idx and idx[l['qa_id']]['parent']==l['parent_qa_id'] for l in gold)
 assert g['processed']==[l['qa_id'] for l in labels]
 for n in g['nodes']:
  if n['parent']:assert idx[n['parent']]['sequence']<n['sequence']
 assert all(e['revision']==i+1 and e['existing_nodes_moved']==0 and e['existing_edges_changed']==0 for i,e in enumerate(g['events']))
 result={'annotated_parent_edges':len(gold),'matched_created_node_parent':matches,'created_annotated_nodes':sum(l['qa_id'] in idx for l in gold),'scope_true_outside':len(outside),'scope_predicted_outside':len(predoutside),'scope_correct_outside':len(outside&predoutside),'scope_outside_missed':len(outside-predoutside),'scope_in_domain_rejected':len(predoutside-outside),'stable_layout_check':True,'chronology_check':True,'limits':'Previously inspected development dataset, not held-out validation. Same-problem QA are resources rather than nodes; metrics not directly equivalent to earlier one-QA-one-node graph.'}
 (BASE/'incremental-growth/evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
