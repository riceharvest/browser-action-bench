"""Five real one-call MCP scenarios over fresh HTTP/CDP fixtures.

Run: python scripts/mcp_scenario_suite.py
Each case starts and tears down its own fixture, Chromium, and MCP stdio server.
"""
from __future__ import annotations
import http.server, json, os, socket, subprocess, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_lifecycle import stop_mcp_then_chrome

PAGES={
 '/form': '<!doctype html><title>Form</title><input id="unique_name" type="text"><button id="safe_submit" onclick="document.body.dataset.submitted=document.getElementById(\'unique_name\').value;document.title=\'Submitted\'">Save draft</button>',
 '/one': '<!doctype html><title>One</title><a id="to_two" href="/two">Two</a><button id="reload_marker" onclick="document.body.dataset.reloaded=\'yes\'">Reload marker</button>',
 '/two': '<!doctype html><title>Two</title><p id="two_state">page-two</p><a id="to_one" href="/one">One</a>',
 '/tabs': '<!doctype html><title>Tabs</title><a id="other" href="/other" target="_blank">Other</a>',
 '/other': '<!doctype html><title>Other</title><button id="other_button" onclick="document.body.dataset.clicked=\'yes\';document.title=\'OtherClicked\'">Other target</button>',
 '/ambiguous': '<!doctype html><title>Ambiguous</title><button id="a">Same</button><button id="b">Same</button>',
 '/risky': '<!doctype html><title>Risky</title><form id="upload"><input id="file" type="file"><button id="submit" type="submit">Submit</button></form>',
}
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  body=PAGES.get(self.path,PAGES['/form']).encode(); self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
 def log_message(self,*a): pass

def port():
 with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]
def rpc(p,i,args):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'arguments':args}})+'\n'); p.stdin.flush(); return json.loads(p.stdout.readline())
def case(path,goal,completion=None,tools=None):
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler); threading.Thread(target=server.serve_forever,daemon=True).start(); cp=port()
 chrome=subprocess.Popen([sys.executable,'-c',f'import playwright.sync_api as s,time; p=s.sync_playwright().start(); b=p.chromium.launch(headless=True,args=["--remote-debugging-port={cp}"]); b.new_page(); time.sleep(120)'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
 mcp=None
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',cp),.1): break
   except OSError: time.sleep(.1)
  env=os.environ.copy(); env['NEEBLE_CDP_URL']=f'http://127.0.0.1:{cp}'; env['NEEBLE_RESPONSE_TIMEOUT_S']='20'
  mcp=subprocess.Popen([sys.executable,str(ROOT/'neeble_mcp.py')],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  for i,method in [(1,'initialize'),(2,'tools/list')]:
   mcp.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':{}})+'\n'); mcp.stdin.flush(); json.loads(mcp.stdout.readline())
  args={'goal':goal,'start_url':f'http://127.0.0.1:{server.server_address[1]}{path}','max_steps':8}
  if completion:
   args['completion']=dict(completion); args['completion']['url']=args['completion'].get('url','').replace('http://PLACEHOLDER',f'http://127.0.0.1:{server.server_address[1]}')
  if tools: args['tools']=tools
  response=rpc(mcp,3,args); payload=json.loads(response['result']['content'][0]['text']); return payload
 finally:
  _, _, stderr = stop_mcp_then_chrome(mcp, chrome)
  if stderr: print(stderr, file=sys.stderr, end='')
  server.shutdown(); server.server_close()
def main():
 specs=[
  ('form','/form','Type unique_name to "Alice" then click safe_submit Save draft',{'title':'Submitted'}),
  ('navigation','/one','Click to_two, then go back to /one and reload; preserve the page title',{'url':'http://PLACEHOLDER/one','title':'One'}),
  ('tabs','/tabs','Open the Other link in another page/tab and click the unique other_button target',{'title':'OtherClicked'}),
  ('ambiguous','/ambiguous','Click the button labeled Same',None),
  ('risky','/risky','Upload a file and submit the form',None),]
 results=[]
 for name,path,goal,completion in specs:
  try:
   p=case(path,goal,completion); tr=p.get('action_trajectory',[]); names=[x.get('name') for x in tr]; st=p.get('state',{}); url=st.get('url','');
   nav_ok=names[:5]==['goto','click_element','back','reload'] and names.count('reload')==1 and url.endswith('/one') and st.get('title')=='One' and p.get('status')=='complete'
   tab_ok=names[:3]==['goto','click_element','click_element'] and len(names)==3 and st.get('pages',0)>=2 and url.endswith('/other') and st.get('title')=='OtherClicked' and p.get('status')=='complete'
   results.append({'name':name,'status':p.get('status'),'termination':p.get('termination'),'trajectory':tr,'verified':p.get('verified'),'postcondition':st,'pass': (name == 'ambiguous' and p.get('status') in {'partial','escalate'} and not any(x.get('verified') and x.get('name') == 'click_element' for x in tr)) or (name == 'risky' and p.get('status') == 'escalate' and not tr) or (name == 'navigation' and nav_ok) or (name == 'tabs' and tab_ok) or (name == 'form' and names[:3] == ['goto','type_text','click_element'])})
  except Exception as e: results.append({'name':name,'status':'error','error':str(e),'pass':False})
 print(json.dumps(results,indent=2)); return 0 if all(x['pass'] for x in results) else 1
if __name__=='__main__': raise SystemExit(main())
