"""Minimal stdio MCP bridge exposing Neeble as the `neeble` tool."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from neeble_tool import DEFAULT_TOOLS, NeebleTool

SCHEMA={'name':'neeble','description':'Own one bounded verified browser trajectory; completion is claimed only when an explicit completion condition matches observed browser state','inputSchema':{'type':'object','properties':{'goal':{'type':'string'},'start_url':{'type':'string'},'max_steps':{'type':'integer','minimum':1,'maximum':50},'state':{'type':'object'},'tools':{'type':'array'},'completion':{'type':'object','description':'Optional explicit postcondition: url, title, or text_contains. Arbitrary goals remain partial.'}},'required':['goal']}}
def reply(i,r): print(json.dumps({'jsonrpc':'2.0','id':i,'result':r}),flush=True)
def main():
 weights = os.environ.get('NEEBLE_WEIGHTS')
 if not weights:
  weights = str(Path(__file__).resolve().parent / 'models' / 'needle3.cact')
 c=NeebleTool(weights=weights, cdp_url=os.environ.get('NEEBLE_CDP_URL'))
 try:
  for line in sys.stdin:
   if not line.strip(): continue
   q=json.loads(line); i=q.get('id'); m=q.get('method')
   if m=='initialize': reply(i,{'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'neeble','version':'0.1.0'}})
   elif m=='notifications/initialized': continue
   elif m=='tools/list': reply(i,{'tools':[SCHEMA]})
   elif m=='tools/call':
    try:
     a=q.get('params',{}).get('arguments',{}); goal=a.get('goal','')
     out=c.run_goal(goal, a.get('start_url'), int(a.get('max_steps',12)),
                    a.get('tools') or DEFAULT_TOOLS, a.get('state') or None,
                    a.get('completion') or None)
     reply(i,{'content':[{'type':'text','text':json.dumps(out, separators=(',', ':'))}]})
    except Exception as e:
     reply(i,{'content':[{'type':'text','text':json.dumps({'error':str(e),'verified':False})}],'isError':True})
   else: reply(i,{'error':f'unsupported method: {m}'})
 finally:
  c.close()
if __name__=='__main__': main()
