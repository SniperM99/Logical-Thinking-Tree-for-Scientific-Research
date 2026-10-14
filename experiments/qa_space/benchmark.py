"""Offline QA mapping experiment. No database writes; source IDs are evaluation-only."""
import argparse,json,sys,re,time,hashlib,csv
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai-engine'))
from embeddings import local_embedding,METHOD

def normalize(x):
 x=np.asarray(x,dtype=float);return x/np.maximum(np.linalg.norm(x,axis=-1,keepdims=True),1e-12)
def rank_previous(vectors):
 sim=vectors@vectors.T
 return [list(np.argsort(-sim[i,:i])) for i in range(len(vectors))],sim

def complete_link(vectors,threshold):
 """Conservative grouping: every member must meet the threshold, no bridging chains."""
 sim=vectors@vectors.T;groups=[]
 for i in range(len(vectors)):
  eligible=[g for g in groups if min(sim[i,j] for j in g)>=threshold]
  if eligible:max(eligible,key=lambda g:float(np.mean([sim[i,j] for j in g]))).append(i)
  else:groups.append([i])
 return groups

def evaluate(rows,vectors,cross):
 ids={r['id']:i for i,r in enumerate(rows)};rank,sim=rank_previous(vectors)
 labeled=[(i,ids[r['id'].rsplit('.',1)[0]]) for i,r in enumerate(rows) if '.' in r['id']]
 detail=[]
 for i,parent in labeled:
  ranking=rank[i];p=ranking.index(parent)+1;detail.append({'id':rows[i]['id'],'reference_parent':rows[parent]['id'],'nearest':rows[ranking[0]]['id'],'parent_rank':p,'similarity':float(sim[i,parent])})
 metrics={'parent_cases':len(detail),'top1':sum(d['parent_rank']==1 for d in detail)/len(detail),'recall5':sum(d['parent_rank']<=5 for d in detail)/len(detail),'recall10':sum(d['parent_rank']<=10 for d in detail)/len(detail),'mrr':sum(1/d['parent_rank'] for d in detail)/len(detail),'previous_turn_accuracy':sum(parent==i-1 for i,parent in labeled)/len(labeled)}
 source_detail=[]
 for c in cross:
  i=ids[c['synthesis']];a=ids[c['id']];b=ids[c['original']];source_detail.append({'id':c['synthesis'],'primary_rank':rank[i].index(b)+1,'cross_source_rank':rank[i].index(a)+1})
 metrics['cross_both_recall10']=sum(max(d['primary_rank'],d['cross_source_rank'])<=10 for d in source_detail)/len(source_detail)
 return metrics,detail,source_detail

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True);p.add_argument('--summaries');args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
 raw=json.loads(Path(args.data).read_text());rows=[{'id':r[0],'question':r[1],'answer':r[2]} for r in raw[0]['rows'][1:]]
 cross=[{'id':r[0],'original':r[4],'synthesis':r[5]} for r in raw[1]['rows'][1:]]
 representations={};t=time.perf_counter()
 q=np.asarray(local_embedding.encode([r['question'] for r in rows]));a=np.asarray(local_embedding.encode([r['answer'] for r in rows]));representations['question']=q;representations['qa_concat']=np.asarray(local_embedding.encode(['问题：'+r['question']+'\n回答：'+r['answer'] for r in rows]));representations['balanced_qa']=normalize(q+a)
 if args.summaries:
  summaries=json.loads(Path(args.summaries).read_text());assert len(summaries)==len(rows)
  representations['core80']=np.asarray(local_embedding.encode([s['core'] for s in summaries]))
 results={};details={};sources={}
 for name,v in representations.items():results[name],details[name],sources[name]=evaluate(rows,v,cross)
 comparison=[]
 for name,v in representations.items():
  for threshold in [.65,.7,.75,.8,.85,.9]:
   groups=complete_link(v,threshold);pairs=[(i,j) for g in groups for z,i in enumerate(g) for j in g[z+1:]];same=sum(rows[i]['id'].split('.')[0]==rows[j]['id'].split('.')[0] for i,j in pairs)
   comparison.append({'representation':name,'threshold':threshold,'nodes':len(groups),'merged_pairs':len(pairs),'reference_family_pair_purity':same/len(pairs) if pairs else None,'groups':[[rows[i]['id'] for i in g] for g in groups]})
 token_lengths=[len(local_embedding.tokenizer.encode(r['question']+'\n'+r['answer']).ids) for r in rows]
 report={'count':len(rows),'unique':len({r['id'] for r in rows}),'cross_domain':len(cross),'reference_parent_edges':86,'embedding':METHOD,'dimension':512,'elapsed_seconds':time.perf_counter()-t,'max_token_length_with_truncation':max(token_lengths),'metrics':results,'one_qa_one_node':{'nodes':len(rows),'granularity':'fixed','parentage_still_unresolved':True},'aggregate_sweep':comparison,'parent_cases':details,'cross_cases':sources,'limitations':['ID hierarchy is weak reference, not a human-approved node grouping or semantic gold standard.','No model sees IDs or cross-source labels; labels used only to evaluate.','Aggregation purity measures shared identifier family, not scientific correctness.','All retrieval candidates precede the query in workbook order.','No thresholds tuned or selected on a held-out dataset; no best-algorithm claim.']}
 (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));np.savez_compressed(out/'vectors.npz',**representations)
 print(json.dumps({'count':len(rows),'metrics':results,'elapsed_seconds':report['elapsed_seconds']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
