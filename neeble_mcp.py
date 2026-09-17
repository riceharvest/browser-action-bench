"""Minimal stdio MCP bridge exposing Neeble as the `neeble` tool."""
from __future__ import annotations
import json, os, sys
from neeble_tool import NeebleTool

SCHEMA={'name':'neeble','description':'Fast verified browser action policy layer','inputSchema':{'type':'object','properties':{'goal':{'type':'string'},'state':{'type':'object'},'tools':{'type':'array'}},'required':['goal','state','tools']}}
def reply(i,r): print(json.dumps({'jsonrpc':'2.0','id':i,'result':r}),flush=True)
def main():
 c=NeebleTool(weights=os.environ.get('NEEBLE_WEIGHTS','models/needle3.cact'), cdp_url=os.environ.get('NEEBLE_CDP_URL'))
 for line in sys.stdin:
  if not line.strip(): continue
  q=json.loads(line); i=q.get('id'); m=q.get('method')
  if m=='initialize': reply(i,{'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'neeble','version':'0.1.0'}})
  elif m=='notifications/initialized': continue
  elif m=='tools/list': reply(i,{'tools':[SCHEMA]})
  elif m=='tools/call':
   try:
    a=q.get('params',{}).get('arguments',{}); out=c(a.get('goal',''),a.get('state',{}),a.get('tools',[])); reply(i,{'content':[{'type':'text','text':json.dumps(out)}]})
   except Exception as e:
    reply(i,{'content':[{'type':'text','text':json.dumps({'error':str(e),'verified':False})}],'isError':True})
  else: reply(i,{'error':f'unsupported method: {m}'})
if __name__=='__main__': main()
