"""Measure historical retrieval against a frozen AI tree, not semantic correctness."""
import argparse,json,hashlib,csv
from pathlib import Path
import numpy as np
from prepare_dataset import load_inputs
from describe_dataset import validate_descriptors
from question_baseline import rankings,metrics
from improve_retrieval import bm25,coverage

def evaluate(rows,ranking,parents):
 ids={r['qa_id']:i for i,r in enumerate(rows)};details=[]
 for i,r in enumerate(rows):
  p=parents[r['qa_id']]
  if p not in ids:continue
  if ids[p]>=i:raise ValueError('Future or self reference parent')
  if sorted(ranking[i])!=list(range(i)):raise ValueError('Incomplete or invalid historical ranking')
  details.append({'qa_id':r['qa_id'],'parent_qa_id':p,'parent_rank':ranking[i].index(ids[p])+1,'top10':[rows[j]['qa_id'] for j in ranking[i][:10]],'candidate_count':i})
 return metrics([r['parent_rank'] for r in details]),details

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args();base=Path(a.dataset);out=base/'ai-tree-recall';out.mkdir(exist_ok=True)
 raw=(base/'single-root-ai/tree.json').read_bytes();tree=json.loads(raw);(out/'tree-snapshot.json').write_bytes(raw)
 rows=load_inputs(base/'inputs/qa.jsonl');cores=[json.loads(l) for l in (base/'descriptors/core.jsonl').read_text().splitlines()];validate_descriptors(rows,cores);full_ids={r['qa_id']:i for i,r in enumerate(rows)}
 graph=tree['nodes'];root=[n for n in graph if n['parent'] is None];assert len(root)==1;root_id=root[0]['qa_id'];graph_qa={n['qa_id'] for n in graph if n['parent']};selected=[r for r in rows if r['qa_id'] in graph_qa];take=[full_ids[r['qa_id']] for r in selected];assert len(selected)==112
 from embeddings import local_embedding,METHOD
 input_manifest=json.loads((base/'manifest.json').read_text());assert hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest()==input_manifest['files']['inputs/qa.jsonl']['sha256']
 encoded_texts={'question':[r['question'] for r in selected],'full_qa':['问题：'+r['question']+'\n回答：'+r['answer'] for r in selected],'core':[cores[full_ids[r['qa_id']]]['core'] for r in selected]}
 arrays={name:np.asarray(local_embedding.encode(texts)) for name,texts in encoded_texts.items()}
 (out/'encoding-inputs.json').write_text(json.dumps({name:[{'qa_id':r['qa_id'],'text':text} for r,text in zip(selected,texts)] for name,texts in encoded_texts.items()},ensure_ascii=False,indent=2))
 rankings_by_method={};similarities={}
 for name,v in arrays.items():
  assert v.shape==(112,512) and np.isfinite(v).all();rankings_by_method[name],similarities[name]=rankings(v);np.save(out/(name+'-vectors.npy'),v)
 rankings_by_method['bm25']=bm25(['问题：'+r['question']+'\n回答：'+r['answer'] for r in selected],[r['question'] for r in selected]);rankings_by_method['hybrid']=coverage([rankings_by_method['bm25'],rankings_by_method['full_qa']])
 predictions={name:[{'qa_id':r['qa_id'],'sequence':r['sequence'],'top10':[selected[j]['qa_id'] for j in rank[i][:10]]} for i,r in enumerate(selected)] for name,rank in rankings_by_method.items()}
 unions=[list(dict.fromkeys(rankings_by_method['bm25'][i][:10]+rankings_by_method['full_qa'][i][:10])) for i in range(len(selected))];predictions['expanded_union']=[{'qa_id':r['qa_id'],'sequence':r['sequence'],'candidates':[selected[j]['qa_id'] for j in unions[i]]} for i,r in enumerate(selected)]
 # Freeze candidates before using AI edges as targets. Original spreadsheet labels are never read.
 (out/'predictions.json').write_text(json.dumps(predictions,ensure_ascii=False,indent=2));parents={n['qa_id']:n['parent'] for n in graph if n['parent']};names={n['qa_id']:n['id'] for n in graph};results={};all_details=[]
 for method,ranking in rankings_by_method.items():
  results[method],details=evaluate(selected,ranking,parents)
  for d in details:all_details.append({**d,'method':method,'original_id':names[d['qa_id']],'parent_original_id':names[d['parent_qa_id']],'question':next(r['question'] for r in selected if r['qa_id']==d['qa_id']),'top10_original_ids':[names[k] for k in d['top10']]})
 eligible=[i for i,r in enumerate(selected) if parents[r['qa_id']]!=root_id];ids={r['qa_id']:i for i,r in enumerate(selected)};expanded={'cases':len(eligible),'hits':sum(ids[parents[selected[i]['qa_id']]] in unions[i] for i in eligible),'candidate_limit':20,'actual_max_candidates':max(map(len,unions))};expanded['recall']=expanded['hits']/expanded['cases']
 (out/'evaluations.jsonl').write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in all_details))
 for filename,subset in [('all-methods.csv',all_details),('hybrid-cases.csv',[d for d in all_details if d['method']=='hybrid']),('hybrid-failures.csv',[d for d in all_details if d['method']=='hybrid' and d['parent_rank']>10])]:
  with (out/filename).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f);w.writerow(['方法','节点','问题','AI树指定父节点','父节点排名','历史候选数','前十候选','前十命中'])
   for d in subset:w.writerow([d['method'],d['original_id'],d['question'],d['parent_original_id'],d['parent_rank'],d['candidate_count'],'；'.join(d['top10_original_ids']),d['parent_rank']<=10])
 report={'target':'frozen AI-inferred single-root tree','embedding_method':METHOD,'dimension':512,'freshly_encoded':True,'tree_sha256':hashlib.sha256(raw).hexdigest(),'input_sha256':hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest(),'tree_nodes':len(graph),'attached_qa_queries':len(selected),'ordinary_parent_cases':len(eligible),'root_parent_cases':[names[r['qa_id']] for r in selected if parents[r['qa_id']]==root_id],'root_policy':'Root is known and available by definition, not part of question retrieval metrics.','excluded_outside_domain_count':13,'pending_qa_count':len(tree['pending']),'candidate_inventory':'Only previously attached QA nodes in the frozen tree; external and pending QA excluded; root handled separately.','methods':results,'expanded_union':expanded,'limitations':['Measures reproduction/recall of AI-selected parents, not independent correctness of research logic.','Tree and descriptions were AI inferred or edited previously; target is not independent ground truth.','Retrieval recipes reused unchanged; no tuning to these AI edges.','No original spreadsheet parent labels or graph paths used in ranking; only node membership and chronology constrain the search space.','Metrics are not directly comparable to prior 86-case spreadsheet evaluation.'],'files':{}}
 for f in out.iterdir():
  if f.is_file() and f.name not in ['metrics.json','report.md']:report['files'][f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
 (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 titles={'question':'仅问题','full_qa':'完整问答','core':'80字核心描述','bm25':'BM25词语匹配','hybrid':'BM25与问答语义联合'}
 text='# 当前AI树父节点召回测量\n\n## 评价范围\n\n当前树共有113个节点：智能制造根节点与112个已关联问答。Q1直接挂根，其父节点已知，单独报告，不计入历史问答召回；其余111个问答参与评价。13个域外问答和2个待复核问答不进入候选或分母。每个查询仅搜索当时之前已关联的问答节点。\n\n## 真实测量结果\n\n|方法|最近邻命中|前五召回|前十召回|前十比例|\n|---|---:|---:|---:|---:|\n'
 for name,m in results.items():text+=f"|{titles[name]}|{m['top1_hits']}/111|{m['recall5_hits']}/111|{m['recall10_hits']}/111|{m['recall10']:.2%}|\n"
 text+=f"\n扩大并集（最多20个）召回{expanded['hits']}/111，比例{expanded['recall']:.2%}。与固定10个候选分开比较。\n\n## 如何理解\n\n这些指标衡量能否找回AI树指定的父节点，不是父子关系科学准确率。AI树还未经过独立标注复核。旧实验以Excel标注的86条父关系为分母，本实验以AI树的111条非根父关系为分母，不能据百分比直接断言算法变好或变差。检索阶段没有使用父子边或祖先路径来补入候选。\n\n完整原始候选、向量、固定目标快照及逐条失败记录均保留，便于复核。没有重新调用大模型或修改研究树。\n"
 (out/'report.md').write_text(text);print(json.dumps({'methods':results,'expanded_union':expanded,'root_parent_cases':report['root_parent_cases']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
