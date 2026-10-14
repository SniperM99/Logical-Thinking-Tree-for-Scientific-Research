"""Stage two: source-grounded descriptors from isolated QA input, never evaluation labels."""
import argparse,json,os,sys,hashlib,csv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from prepare_dataset import load_inputs
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request
POLICY='core-v1:70-100-unicode-characters:source-only'
def call(batch,review=False):
 schema={'type':'object','additionalProperties':False,'required':['items'],'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['qa_id','core','issues'],'properties':{'qa_id':{'type':'string'},'core':{'type':'string'},'issues':{'type':'array','items':{'type':'string'}}}}}}}
 task=('审核并修正描述，逐项核对原文：不能遗漏影响结论的条件、不能把建议写成实证结论、不能补充新事实。发现的问题写issues，修正后core仍需完整。' if review else '为每条完整问答生成核心内容描述，issues为空数组。')
 prompt=task+'每条core目标80个中文字符，允许70至100字符，按Python len计数含标点。保留对象、具体问题、关键判断或方法、必要条件与限制。是一段自然中文，不要网址、编号、标签或列表。具体问题间的区别不能被通用总结覆盖。不得新增原文没有的事实或解释。不得判断父子或节点关系。调用describe_qa，必须输出每个qa_id。'
 result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'describe_qa','description':'概括并检查问答核心内容','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'describe_qa'}},'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(batch,ensure_ascii=False)}]})
 c=result['choices'][0]
 if c.get('finish_reason')=='length':raise ValueError('Truncated descriptor response')
 m=c['message'];payload=m['tool_calls'][0]['function']['arguments'] if m.get('tool_calls') else m['content'];items=json.loads(payload)['items']
 if len(items)!=len(batch) or {x['qa_id'] for x in items}!={x['qa_id'] for x in batch}:raise ValueError('Descriptor IDs mismatch')
 if any(not isinstance(x['core'],str) or not x['core'].strip() or not isinstance(x['issues'],list) for x in items):raise ValueError('Invalid descriptor')
 return items

def validate_descriptors(rows,records):
 if len(rows)!=len(records) or [r['qa_id'] for r in rows]!=[r['qa_id'] for r in records]:raise ValueError('Descriptor identity/order mismatch')
 if len({r['core'] for r in records})!=len(records):raise ValueError('Duplicate descriptors')
 for source,item in zip(rows,records):
  if not 70<=len(item['core'])<=100 or item['character_count']!=len(item['core']):raise ValueError('Descriptor length invalid')
  expected=hashlib.sha256((source['question']+'\n'+source['answer']).encode()).hexdigest()
  if item['source_sha256']!=expected:raise ValueError('Source content changed')
 return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);args=p.parse_args();base=Path(args.dataset);rows=load_inputs(base/'inputs/qa.jsonl');out=base/'descriptors';out.mkdir(exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
 if (out/'core.jsonl').exists():
  saved=[json.loads(line) for line in (out/'core.jsonl').read_text().splitlines() if line.strip()]
  validate_descriptors(rows,saved);print('Existing reviewed descriptors verified; preserved without additional model calls.');return
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 def run(start):
  batch=rows[start:start+8];stamp=hashlib.sha256((POLICY+json.dumps(batch,ensure_ascii=False)).encode()).hexdigest();path=cache/(stamp+'.json')
  if path.exists():return json.loads(path.read_text())
  draft=call(batch);review=call([{**r,'draft':next(x['core'] for x in draft if x['qa_id']==r['qa_id'])} for r in batch],True)
  history={x['qa_id']:list(x['issues']) for x in review}
  for attempt in range(2):
   bad=[{**r,'draft':next(x['core'] for x in review if x['qa_id']==r['qa_id']),'observed_length':len(next(x['core'] for x in review if x['qa_id']==r['qa_id']))} for r in batch if not 70<=len(next(x['core'] for x in review if x['qa_id']==r['qa_id']))<=100]
   if not bad:break
   fixed=call(bad,True);lookup={x['qa_id']:x for x in fixed};review=[lookup.get(x['qa_id'],x) for x in review]
  records=[]
  for r in batch:
   item=next(x for x in review if x['qa_id']==r['qa_id']);records.append({'qa_id':r['qa_id'],'sequence':r['sequence'],'core':item['core'],'character_count':len(item['core']),'source_sha256':hashlib.sha256((r['question']+'\n'+r['answer']).encode()).hexdigest(),'review_issues_corrected':history[r['qa_id']],'length_pass':70<=len(item['core'])<=100})
  path.write_text(json.dumps(records,ensure_ascii=False,indent=2));return records
 results=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  for f in as_completed([pool.submit(run,i) for i in range(0,len(rows),8)]):results.extend(f.result());print('Reviewed',len(results),'/',len(rows),flush=True)
 results.sort(key=lambda x:x['sequence']);validate_descriptors(rows,results)
 (out/'core.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results))
 with (out/'core-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.writer(f);writer.writerow(['问答ID','顺序','问题','核心描述','字符数','长度合格','审核发现并修正的问题'])
  for r,source in zip(results,rows):writer.writerow([r['qa_id'],r['sequence'],source['question'],r['core'],r['character_count'],r['length_pass'],'；'.join(r['review_issues_corrected'])])
 report={'policy':POLICY,'model':os.environ['XUNXU_MODEL'],'count':len(results),'length_min':min(r['character_count'] for r in results),'length_max':max(r['character_count'] for r in results),'length_mean':sum(r['character_count'] for r in results)/len(results),'length_failures':[r['qa_id'] for r in results if not r['length_pass']],'duplicate_descriptions':len(results)-len({r['core'] for r in results}),'review_corrections':sum(bool(r['review_issues_corrected']) for r in results),'source_input_sha256':hashlib.sha256((base/'inputs/qa.jsonl').read_bytes()).hexdigest(),'validation':'Schema, identity, sequence, source hashes and length checked mechanically; fidelity reviewed by the same model in a separate pass, not an independent accuracy proof.','labels_read':False,'vectors_generated':False,'database_written':False}
 (out/'quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
