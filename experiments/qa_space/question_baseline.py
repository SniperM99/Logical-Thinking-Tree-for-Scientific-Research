"""Question-only streaming retrieval. Embedding never sees answers or evaluation labels."""
import argparse,json,sys,hashlib,csv,time,platform
from pathlib import Path
import numpy as np
from prepare_dataset import load_inputs
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from embeddings import local_embedding,METHOD

def rankings(vectors):
 v=np.asarray(vectors,dtype=float)
 if v.ndim!=2 or not np.isfinite(v).all():raise ValueError('Invalid vectors')
 scores=v@v.T
 # Stable tie-break: earlier row first. No future candidates and no self.
 return [sorted(range(i),key=lambda j:(-float(scores[i,j]),j)) for i in range(len(v))],scores

def metrics(ranks):
 return {'cases':len(ranks),'top1_hits':sum(r==1 for r in ranks),'recall5_hits':sum(r<=5 for r in ranks),'recall10_hits':sum(r<=10 for r in ranks),'top1':sum(r==1 for r in ranks)/len(ranks) if ranks else None,'recall5':sum(r<=5 for r in ranks)/len(ranks) if ranks else None,'recall10':sum(r<=10 for r in ranks)/len(ranks) if ranks else None,'mrr':sum(1/r for r in ranks)/len(ranks) if ranks else None}

def encode_text(row,representation):
 return row['question'] if representation=='question' else '问题：'+row['question']+'\n回答：'+row['answer']

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--representation',choices=['question','full_qa'],default='question');args=p.parse_args();base=Path(args.dataset);out=base/('question-baseline' if args.representation=='question' else 'full-qa-baseline');out.mkdir(exist_ok=True)
 rows=load_inputs(base/'inputs/qa.jsonl');manifest=json.loads((base/'manifest.json').read_text());assert hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest()==manifest['files']['inputs/qa.jsonl']['sha256']
 started=time.perf_counter();texts=[encode_text(r,args.representation) for r in rows];vectors=np.asarray(local_embedding.encode(texts));
 from tokenizers import Tokenizer
 measuring=Tokenizer.from_str(local_embedding.tokenizer.to_str());measuring.no_truncation();measuring.no_padding()
 lengths=[len(measuring.encode(text).ids) for text in texts]
 encoding=[{'qa_id':r['qa_id'],'sequence':r['sequence'],'text':text,'untruncated_token_count':length,'token_limit':512,'truncated':length>512,'text_sha256':hashlib.sha256(text.encode()).hexdigest()} for r,text,length in zip(rows,texts,lengths)]
 (out/'encoding-inputs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in encoding))
 assert vectors.shape==(len(rows),512);assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5);rank,scores=rankings(vectors);elapsed=time.perf_counter()-started
 np.save(out/'question-vectors.npy',vectors)
 # Freeze retrieval outputs before reading labels.
 predictions=[{'qa_id':r['qa_id'],'sequence':r['sequence'],'candidate_count':len(rank[i]),'top10':[{'qa_id':rows[j]['qa_id'],'similarity':float(scores[i,j])} for j in rank[i][:10]]} for i,r in enumerate(rows)]
 (out/'retrieval.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in predictions))
 labels=[json.loads(x) for x in (base/'evaluation/labels.jsonl').read_text().splitlines()];assert [r['qa_id'] for r in labels]==[r['qa_id'] for r in rows];ids={r['qa_id']:i for i,r in enumerate(rows)};details=[]
 for i,l in enumerate(labels):
  parent=l['parent_qa_id'];parent_rank=None
  if parent is not None:
   assert ids[parent]<i;parent_rank=rank[i].index(ids[parent])+1
  details.append({'qa_id':rows[i]['qa_id'],'original_id':l['original_id'],'sequence':i+1,'question':rows[i]['question'],'reference_parent':parent,'reference_parent_original_id':labels[ids[parent]]['original_id'] if parent else None,'parent_rank':parent_rank,'candidate_count':i,'nearest_original_id':labels[rank[i][0]]['original_id'] if i else None,'top10_original_ids':[labels[j]['original_id'] for j in rank[i][:10]],'node_type':l['node_type'],'dialogue_action':l['metadata']['对话动作'],'status':'no_parent_reference' if parent is None else 'top1_hit' if parent_rank==1 else 'top10_hit' if parent_rank<=10 else 'top10_miss'})
 (out/'evaluation.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in details))
 for name,subset in [('all-cases.csv',details),('top10-failures.csv',[d for d in details if d['status']=='top10_miss'])]:
  with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f);w.writerow(['原编号','顺序','问题','参考父问题','父问题排名','历史候选数','最近邻','前十候选','结果','对话动作'])
   for d in subset:w.writerow([d['original_id'],d['sequence'],d['question'],d['reference_parent_original_id'],d['parent_rank'],d['candidate_count'],d['nearest_original_id'],'；'.join(d['top10_original_ids']),d['status'],d['dialogue_action']])
 eligible=[d for d in details if d['parent_rank'] is not None];report={'representation':args.representation,'text_format':'question only' if args.representation=='question' else '问题：{question}\n回答：{answer}','token_limit':512,'truncated_count':sum(n>512 for n in lengths),'max_untruncated_tokens':max(lengths),'input_sha256':hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest(),'model':METHOD,'dimension':512,'distance':'L2-normalized cosine similarity','query_count':len(rows),'evaluated_parent_cases':len(eligible),'no_parent_reference_count':len(rows)-len(eligible),'embedding_and_retrieval_seconds':elapsed,'metrics':metrics([d['parent_rank'] for d in eligible]),'previous_turn_parent_hits':sum(ids[d['reference_parent']]==d['sequence']-2 for d in eligible),'by_node_type':{},'by_dialogue_action':{},'versions':{'python':platform.python_version(),'numpy':np.__version__},'limitations':['This measures parent-candidate recall, not parent-selection accuracy or tree correctness.','No-parent records are searchable candidates but excluded from parent metrics.','Data is one annotated constructed dataset; no holdout tuning, optimality or generalization claim.','No descriptor, ID hierarchy, source or dialogue labels enter embeddings; question-only excludes answers and full_qa includes answers.','No new DeepSeek calls, no database changes, no tree generation.'],'files':{}}
 for field,target in [('node_type','by_node_type'),('dialogue_action','by_dialogue_action')]:
  for value in sorted({d[field] for d in eligible}):report[target][value]=metrics([d['parent_rank'] for d in eligible if d[field]==value])
 for file in sorted(out.iterdir()):
  if file.is_file() and file.name not in ['metrics.json','report.md']:report['files'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
 (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 m=report['metrics'];text=f'''# {('仅问题文本' if args.representation=='question' else '完整问答拼接')}召回基线\n\n真实运行：127 条问答，512 维本地 BGE 中文嵌入，表示方式为 {args.representation}。每条只搜索其前面的历史问答，按高维余弦相似度排序。预测文件先保存，随后加载独立标签评价。\n\n模型最多编码512个token；本轮 {sum(n>512 for n in lengths)} 条超过限制，最长 {max(lengths)} 个token。超限文本按现有模型截断，没有补算尾部。\n\n## 总体结果\n\n明确父问题的 86 条参与评价；41 条无父问题记录不计入命中率。\n\n|指标|命中数|比例|\n|---|---:|---:|\n|最近邻命中参考父问题|{m['top1_hits']}/86|{m['top1']:.2%}|\n|前五候选召回父问题|{m['recall5_hits']}/86|{m['recall5']:.2%}|\n|前十候选召回父问题|{m['recall10_hits']}/86|{m['recall10']:.2%}|\n\n平均倒数排名 MRR：{m['mrr']:.6f}。直接取上一轮会命中 {report['previous_turn_parent_hits']}/86。\n\n## 分组结果\n\n|问答类型|样本数|前十命中|前十召回率|\n|---|---:|---:|---:|\n'''
 for kind,v in report['by_node_type'].items():text+=f"|{kind}|{v['cases']}|{v['recall10_hits']}|{v['recall10']:.2%}|\n"
 text+='\n## 局限与核对\n\n这是候选召回结果，不能解释为分支构建准确率。没有训练或调参，不能据此声称最优；单一构造数据集不代表真实使用泛化能力。完整历史候选仍包含外领域问题，无父标注记录没有被算法自动判成根节点。\n\n`all-cases.csv` 包含全部 127 条；`top10-failures.csv` 包含全部前十漏召回；`retrieval.jsonl` 是评价前的原始预测；`question-vectors.npy` 保留真实向量；`metrics.json` 记录指标与校验和。\n\n## 前十漏召回记录\n\n|问题|参考父问题|父问题排名|最近邻|\n|---|---|---:|---|\n'
 for d in details:
  if d['status']=='top10_miss':text+=f"|{d['original_id']}|{d['reference_parent_original_id']}|{d['parent_rank']}|{d['nearest_original_id']}|\n"
 (out/'report.md').write_text(text);print(json.dumps({k:report[k] for k in ['query_count','evaluated_parent_cases','metrics','embedding_and_retrieval_seconds','by_node_type']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
