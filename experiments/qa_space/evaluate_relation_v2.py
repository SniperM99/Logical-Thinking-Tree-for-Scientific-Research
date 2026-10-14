"""Post-prediction comparison; original parent annotations are never model inputs."""
import json,csv,argparse
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]/'.runtime/experiments/robot-qa-v1'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--variant',default='relation-v2');variant=parser.parse_args().variant
 labels=[json.loads(l) for l in (BASE/'evaluation/labels.jsonl').read_text().splitlines()];label={l['qa_id']:l for l in labels};old=json.loads((BASE/'conversation-graph/graph.json').read_text());new=json.loads((BASE/variant/'graph.json').read_text());oi={n['qa_id']:n for n in old['nodes']};ni={n['qa_id']:n for n in new['nodes']};records=[]
 for l in labels:
  gold=l['parent_qa_id'];key=l['qa_id']
  if not gold:continue
  op=oi.get(key,{}).get('parent');np=ni.get(key,{}).get('parent');chain=op!=gold and op in label and label[op]['parent_qa_id']==gold
  records.append({'qa_id':key,'original_id':l['original_id'],'gold_parent':gold,'old_parent':op,'new_parent':np,'old_correct':op==gold,'new_correct':np==gold,'baseline_sibling_as_child':chain,'fixed_sibling_as_child':chain and np==gold,'lost_correct':op==gold and np!=gold})
 result={'annotated_edges':len(records),'old_correct':sum(r['old_correct'] for r in records),'new_correct':sum(r['new_correct'] for r in records),'gains':sum(not r['old_correct'] and r['new_correct'] for r in records),'losses':sum(r['lost_correct'] for r in records),'baseline_sibling_as_child':sum(r['baseline_sibling_as_child'] for r in records),'fixed_sibling_as_child':sum(r['fixed_sibling_as_child'] for r in records),'new_sibling_as_child':sum(r['new_parent']!=r['gold_parent'] and r['new_parent'] in label and label[r['new_parent']]['parent_qa_id']==r['gold_parent'] for r in records),'attached_qa':new['report']['attached_qa'],'pending_qa':new['report']['pending_qa'],'limits':'Exploratory comparison on previously inspected dataset, not held-out validation. 28 unannotated upper questions excluded from parent accuracy.'}
 for n in new['nodes']:
  if n['parent']:assert ni[n['parent']]['sequence']<n['sequence']
 out=BASE/variant;(out/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'evaluation-cases.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 with (out/'evaluation-cases.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 for name in ['Q1.1','Q3.1','Q3.2']:
  n=next((n for n in new['nodes'] if n['id']==name),None);print(name,'=>',ni[n['parent']]['id'] if n else 'pending',n['relation'] if n else '')
if __name__=='__main__':main()
