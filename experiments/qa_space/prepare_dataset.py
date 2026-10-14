"""Prepare isolated QA inputs and evaluation labels; never imports the live application."""
import argparse,hashlib,json,shutil
from pathlib import Path

def empty(value):return value is None or value in ('','—')
def refs(value):return [] if empty(value) else list(dict.fromkeys(str(value).split('；')))
def build(main,cross):
 required={'编号','问题','回答','提问顺序','父问题编号','层级','节点类型','来源问题编号','对话动作'}
 if not main or not required.issubset(main[0]):raise ValueError('Missing required columns')
 if len({r['编号'] for r in main})!=len(main):raise ValueError('Duplicate original IDs')
 if [r['提问顺序'] for r in main]!=list(range(1,len(main)+1)):raise ValueError('Workbook sequence is not contiguous row order')
 index={r['编号']:i for i,r in enumerate(main)};keys={name:f'qa_{i+1:04d}' for name,i in index.items()};inputs=[];labels=[]
 for i,r in enumerate(main):
  if not isinstance(r['问题'],str) or not r['问题'].strip() or not isinstance(r['回答'],str) or not r['回答'].strip():raise ValueError('Empty question or answer')
  parent=None if empty(r['父问题编号']) else r['父问题编号']
  if parent:
   if parent not in index or index[parent]>=i:raise ValueError('Parent missing, future or cyclic')
   if r['层级']!=main[index[parent]]['层级']+1:raise ValueError('Inconsistent depth')
  elif r['层级']!=0:raise ValueError('Unparented non-root')
  sources=refs(r.get('来源问题编号'));continuations=refs(r.get('承接或回访节点'))
  if any(s not in index for s in sources+continuations):raise ValueError('Unknown reference')
  if any(index[s]>=i for s in sources if s!=r['编号']):raise ValueError('Future source')
  inputs.append({'qa_id':keys[r['编号']],'sequence':i+1,'question':r['问题'],'answer':r['回答']})
  labels.append({'qa_id':keys[r['编号']],'original_id':r['编号'],'parent_qa_id':keys[parent] if parent else None,'level':r['层级'],'node_type':r['节点类型'],'source_qa_ids':[keys[s] for s in sources if s!=r['编号']],'continuation_qa_ids':[keys[s] for s in continuations],'metadata':{k:v for k,v in r.items() if k not in ('问题','回答')}})
 for r in cross:
  if r['编号'] not in index:raise ValueError('Cross-domain row absent from main')
  m=main[index[r['编号']]]
  if (r['问题'],r['回答'])!=(m['问题'],m['回答']):raise ValueError('Cross-domain duplicate has inconsistent QA')
  if r['综合子问题'] not in index or r['关联原问题'] not in index:raise ValueError('Missing synthesis reference')
  synth=labels[index[r['综合子问题']]]
  if synth['parent_qa_id']!=keys[r['关联原问题']] or keys[r['编号']] not in synth['source_qa_ids']:raise ValueError('Inconsistent cross-source labels')
 return inputs,labels

def load_inputs(path):
 """Model-facing loader: rejects label fields rather than silently accepting leakage."""
 rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
 if any(set(r)!= {'qa_id','sequence','question','answer'} for r in rows):raise ValueError('Only QA input fields are allowed')
 return rows

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 import openpyxl
 source=Path(args.source).resolve();out=Path(args.output).resolve()
 if out.exists():raise ValueError('Output already exists; choose a new dataset directory')
 workbook=openpyxl.load_workbook(source,read_only=True,data_only=True)
 tables={}
 for sheet in workbook:
  rows=list(sheet.values);tables[sheet.title]=[dict(zip(rows[0],r)) for r in rows[1:] if any(v is not None for v in r)]
 inputs,labels=build(tables['测试问题列表'],tables['跨领域问题']);workbook.close()
 out.mkdir(parents=True);(out/'inputs').mkdir();(out/'evaluation').mkdir();(out/'source').mkdir()
 shutil.copy2(source,out/'source/source.xlsx')
 for filename,rows in [('inputs/qa.jsonl',inputs),('evaluation/labels.jsonl',labels)]:
  (out/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 (out/'evaluation/cross_domain.json').write_text(json.dumps(tables['跨领域问题'],ensure_ascii=False,indent=2))
 assert load_inputs(out/'inputs/qa.jsonl')==inputs
 manifest={'schema_version':1,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_path':str(source),'qa_count':len(inputs),'parent_edges':sum(r['parent_qa_id'] is not None for r in labels),'top_level_count':sum(r['parent_qa_id'] is None for r in labels),'cross_domain_count':len(tables['跨领域问题']),'synthesis_count':sum(r['node_type']=='综合延伸' for r in labels),'input_fields':['qa_id','sequence','question','answer'],'evaluation_fields_excluded_from_inputs':['original_id','parent_qa_id','level','node_type','source_qa_ids','continuation_qa_ids','metadata'],'validation':{'unique_ids':True,'complete_qa':True,'original_order_preserved':True,'parent_exists_and_precedes_child':True,'depth_consistent':True,'sources_exist_and_precede_synthesis':True,'cross_sheet_duplicates_consistent':True,'cross_synthesis_labels_consistent':True,'input_label_isolation':True},'files':{}}
 for p in sorted(out.rglob('*')):
  if p.is_file():manifest['files'][str(p.relative_to(out))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 (out/'README.md').write_text(f'''# 问答实验数据底座\n\n问答：{len(inputs)} 条。父子关系：{manifest['parent_edges']} 条。\n\n`inputs/qa.jsonl` 是算法唯一输入，含无层级含义的 ID、原始顺序及完整问答。\n`evaluation/labels.jsonl` 保留原编号、父子关系、来源和全部结构标注，仅用于评价。\n`evaluation/cross_domain.json` 是跨领域配对标注，不增加问答数量。\n`source/source.xlsx` 是原始文件快照；`manifest.json` 记录校验和。\n\n上层无父问题统一保存 null，不人为挂到 Q1。来源与主父关系分开保存。外领域记录中的自引用来源不生成自环，但原字段在 metadata 中保留。承接字段保留其原始语义，不能直接当作父节点。\n\n没有执行摘要生成、向量计算、数据集拆分或研究树构建；没有写入项目数据库。全部问答及其标注均为私人实验数据，目录位于 Git 忽略区域。\n''')
 print(json.dumps({k:manifest[k] for k in ['qa_count','parent_edges','top_level_count','cross_domain_count','synthesis_count','validation']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
