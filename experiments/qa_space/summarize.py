"""Produce cached ~80-character descriptors from supplied QA, without structure labels."""
import json,os,sys,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'ai-engine'))
from main import provider_request

def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True);args=p.parse_args()
 for line in (ROOT/'ai-engine/.env').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   k,v=line.split('=',1)
   if k.startswith('XUNXU_'):os.environ.setdefault(k,v)
 rows=json.loads(Path(args.data).read_text())[0]['rows'][1:];out=Path(args.out);cache=out.parent/'summary-cache';cache.mkdir(parents=True,exist_ok=True)
 def run(start):
  path=cache/f'{start:03}.json'
  if path.exists():return start,json.loads(path.read_text())
  batch=[{'item':i,'question':r[1],'answer':r[2]} for i,r in enumerate(rows[start:start+12],start)]
  schema={'type':'object','additionalProperties':False,'required':['items'],'properties':{'items':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['item','core'],'properties':{'item':{'type':'integer'},'core':{'type':'string'}}}}}}
  result=provider_request('chat/completions',{'model':os.environ['XUNXU_MODEL'],'temperature':0.1,'max_tokens':4096,'tools':[{'type':'function','function':{'name':'describe_qa','description':'为每个完整问答生成核心内容描述','parameters':schema}}],'tool_choice':{'type':'function','function':{'name':'describe_qa'}},'messages':[{'role':'system','content':'每条问答生成一个约80字的中文核心内容描述，目标70至90字符（含标点）。保留研究对象、具体问题、回答的关键判断或方法及重要条件。每条独立概括，忠于给定问答，不增加结论，不把研究建议写成已验证结果，不做节点或父子判断，不复述无关背景。不要写编号、列表、网址。不同问题不能套用相同的泛化摘要。调用describe_qa输出全部items。'},{'role':'user','content':json.dumps(batch,ensure_ascii=False)}]})
  choice=result['choices'][0];assert choice.get('finish_reason')!='length';message=choice['message'];calls=message.get('tool_calls',[]);payload=calls[0]['function']['arguments'] if calls else message['content'];items=json.loads(payload)['items'];assert {s['item'] for s in items}=={s['item'] for s in batch};assert len(items)==len(batch);assert all(isinstance(s['core'],str) and 20<=len(s['core'])<=200 for s in items)
  path.write_text(json.dumps(items,ensure_ascii=False,indent=2));return start,items
 allrows={}
 with ThreadPoolExecutor(max_workers=2) as pool:
  for f in as_completed([pool.submit(run,i) for i in range(0,len(rows),12)]):
   start,items=f.result();allrows.update({s['item']:s for s in items});print('Completed descriptors',len(allrows),'/',len(rows),flush=True)
 ordered=[{'id':rows[i][0],'core':allrows[i]['core'],'characters':len(allrows[i]['core'])} for i in range(len(rows))];out.write_text(json.dumps(ordered,ensure_ascii=False,indent=2));print('Descriptor length range',min(s['characters'] for s in ordered),max(s['characters'] for s in ordered),flush=True)
if __name__=='__main__':main()
