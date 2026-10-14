"""Fixed-budget multi-view recall experiments. Predictions precede label access."""
import json,sys,argparse,hashlib,csv,re,math
from pathlib import Path
from collections import Counter
import numpy as np
from prepare_dataset import load_inputs
from describe_dataset import validate_descriptors
from question_baseline import rankings,metrics
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from embeddings import local_embedding,METHOD

def order(scores,i):return sorted(range(i),key=lambda j:(-float(scores[i,j]),j))
def fusion(views):
 result=[]
 for i in range(len(views[0])):
  score={j:0.0 for j in range(i)}
  for view in views:
   for pos,j in enumerate(view[i],1):score[j]+=1/(60+pos)
  result.append(sorted(score,key=lambda j:(-score[j],j)))
 return result

def coverage(views,budget=10):
 result=[]
 for i in range(len(views[0])):
  selected=[]
  for k in range(i):
   for view in views:
    if view[i][k] not in selected:selected.append(view[i][k])
    if len(selected)>=min(i,budget):break
   if len(selected)>=min(i,budget):break
  result.append(selected+[j for j in fusion(views)[i] if j not in selected])
 return result

def terms(text):
 text=re.sub(r'https?://\S+','',text)
 return Counter(re.findall(r'[a-zA-Z][a-zA-Z0-9-]*',text.lower())+[s[i:i+2] for s in re.findall(r'[\u4e00-\u9fff]+',text) for i in range(len(s)-1)])
def bm25(texts,queries):
 docs=[terms(t) for t in texts];result=[]
 for i,q in enumerate(queries):
  if not i:result.append([]);continue
  hist=docs[:i];df=Counter(t for d in hist for t in d);avg=sum(sum(d.values()) for d in hist)/i;qt=terms(q);scores=[]
  for d in hist:
   length=sum(d.values());score=0
   for t in qt:
    tf=d.get(t,0)
    if tf:score+=math.log(1+(i-df[t]+.5)/(df[t]+.5))*tf*2.2/(tf+1.2*(.25+.75*length/max(avg,1)))
   scores.append(score)
  result.append(sorted(range(i),key=lambda j:(-scores[j],j)))
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args();base=Path(a.dataset);out=base/'multi-view-recall';out.mkdir(exist_ok=True)
 rows=load_inputs(base/'inputs/qa.jsonl');cores=[json.loads(l) for l in (base/'descriptors/core.jsonl').read_text().splitlines()];validate_descriptors(rows,cores)
 q=np.load(base/'question-baseline/question-vectors.npy');qa=np.load(base/'full-qa-baseline/question-vectors.npy');core=np.asarray(local_embedding.encode([r['core'] for r in cores]));assert core.shape==q.shape==qa.shape==(127,512);np.save(out/'core-vectors.npy',core)
 mats={'question':q@q.T,'full_qa':qa@qa.T,'core':core@core.T,'question_to_qa':q@qa.T,'core_to_qa':core@qa.T,'core_to_question':core@q.T}
 methods={k:[order(m,i) for i in range(len(rows))] for k,m in mats.items()}
 methods['rrf_qa_core']=fusion([methods['full_qa'],methods['core']]);methods['rrf_q_qa_core']=fusion([methods[k] for k in ['question','full_qa','core']]);methods['coverage_qa_core']=coverage([methods['full_qa'],methods['core']]);methods['coverage_q_qa_core']=coverage([methods[k] for k in ['question','full_qa','core']]);methods['rrf_asymmetric']=fusion([methods[k] for k in ['full_qa','question_to_qa','core_to_qa']])
 text=['问题：'+r['question']+'\n回答：'+r['answer'] for r in rows];methods['bm25']=bm25(text,[r['question'] for r in rows]);methods['rrf_semantic_lexical']=fusion([methods[k] for k in ['full_qa','core','bm25']]);methods['coverage_lexical_qa']=coverage([methods['bm25'],methods['full_qa']]);methods['coverage_lexical_core']=coverage([methods['bm25'],methods['core']]);methods['rrf_lexical_qa']=fusion([methods['bm25'],methods['full_qa']])
 predictions={name:[{'qa_id':rows[i]['qa_id'],'top10':[rows[j]['qa_id'] for j in ranked[:10]]} for i,ranked in enumerate(ranking)] for name,ranking in methods.items()}
 (out/'predictions.json').write_text(json.dumps(predictions,ensure_ascii=False,indent=2))
 # Evaluation-only labels read after the candidate lists have been frozen.
 labels=[json.loads(l) for l in (base/'evaluation/labels.jsonl').read_text().splitlines()];ids={r['qa_id']:i for i,r in enumerate(rows)};eligible=[i for i,l in enumerate(labels) if l['parent_qa_id']];report={'model':METHOD,'dimension':512,'budget':10,'fusion_constant':60,'config_selection':'Exploratory two-round comparison on the same dataset; lexical hybrids were added after initial BM25 results. No independent holdout, optimality unproven.','results':{},'files':{}};details=[]
 for name,ranking in methods.items():
  r=[ranking[i].index(ids[labels[i]['parent_qa_id']])+1 for i in eligible];report['results'][name]=metrics(r)
  for i,rank in zip(eligible,r):details.append({'method':name,'qa_id':rows[i]['qa_id'],'original_id':labels[i]['original_id'],'question':rows[i]['question'],'parent':labels[ids[labels[i]['parent_qa_id']]]['original_id'],'rank':rank,'top10':[labels[j]['original_id'] for j in ranking[i][:10]],'action':labels[i]['metadata']['对话动作']})
 (out/'details.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in details))
 with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['方法','原编号','问题','参考父问题','排名','前十候选','对话动作'])
  for r in details:w.writerow([r['method'],r['original_id'],r['question'],r['parent'],r['rank'],'；'.join(r['top10']),r['action']])
 for file in out.iterdir():
  if file.name not in ['metrics.json','report.md'] and file.is_file():report['files'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
 (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report['results'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
