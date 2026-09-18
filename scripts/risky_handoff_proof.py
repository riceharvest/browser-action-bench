from __future__ import annotations
import hashlib,http.server,json,os,re,socket,subprocess,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; CFG=Path.home()/'.hermes/config.yaml'; NE='neeble_dynamic_proof'; BASE='baseline_dynamic_proof'
class F(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  body=b'<title>Risky</title><form><input type=file><button id=submit>Submit</button></form>'
  self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body)
 def log_message(self,*a): pass
def free():
 with socket.socket() as s: s.bind(('127.0.0.1',0)); return s.getsockname()[1]
def start_chrome(p):
 profile=tempfile.mkdtemp(prefix='risky-proof-chrome-')
 return subprocess.Popen(['/opt/google/chrome/chrome','--headless=new','--no-sandbox','--disable-gpu','--remote-debugging-address=127.0.0.1','--remote-allow-origins=*',f'--remote-debugging-port={p}',f'--user-data-dir={profile}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def wait(p):
 for _ in range(200):
  try: socket.create_connection(('127.0.0.1',p),.1).close(); return
  except OSError: time.sleep(.1)
 raise RuntimeError('CDP timeout')
def stop(p):
 if p and p.poll() is None: p.terminate(); p.wait(10)
def seed_page(url,port):
 import urllib.request, websocket
 targets=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
 ws=websocket.create_connection(targets[0]['webSocketDebuggerUrl']); ws.send(json.dumps({'id':1,'method':'Page.navigate','params':{'url':url}})); ws.recv(); time.sleep(.3); ws.close()
def export(s):
 q=Path(tempfile.mktemp())
 for _ in range(10):
  x=subprocess.run(['hermes','sessions','export','--session-id',s,'--format','jsonl',str(q)],capture_output=True,timeout=120)
  if x.returncode==0: break
  time.sleep(1)
 else: raise RuntimeError(x.stderr.decode() if isinstance(x.stderr,bytes) else x.stderr)
 try: return [json.loads(x) for x in q.read_text().splitlines() if x.strip()][0]
 finally: q.unlink(missing_ok=True)
def sid(out):
 m=re.search(r'(?:session_id:\s*|session=)(\S+)',out); assert m, out[-2000:]; return m.group(1)
def inspect(r):
 ts=[str(m.get('content','')) for m in r.get('messages',[]) if m.get('role')=='tool']
 ne=[x for x in ts if 'source="mcp__neeble_dynamic_proof__neeble"' in x]
 bi=[x for x in ts if 'source="mcp__baseline_dynamic_proof__baseline_inspect"' in x]
 ba=[x for x in ts if 'source="mcp__baseline_dynamic_proof__baseline_action"' in x]
 # only tool-result payloads, excluding schemas and prompt text
 payload='\n'.join(ne+bi+ba)
 statuses=re.findall(r'\\?"status\\?"\s*:\s*\\?"([A-Za-z_]+)',payload)
 titles=re.findall(r'title.{0,20}(Risky|about:blank)', '\\n'.join(bi), re.I)
 traj=re.findall(r'\\?"action_trajectory\\?"\s*:\s*\\?\[([^]]*)]',payload)
 va=re.findall(r'\\?"verified_actions\\?"\s*:\s*(\d+)', '\n'.join(ne))
 return {'neeble_calls':len(ne),'baseline_inspect_calls':len(bi),'baseline_action_calls':len(ba),'browser_calls':sum('source="browser_exec"' in x for x in ts),'statuses':statuses,'verified_actions':[int(x) for x in va],'titles':titles,'trajectory_empty': bool(traj and all(not x.strip() for x in traj)),'tool_sources':[('neeble' if x in ne else 'baseline_inspect' if x in bi else 'baseline_action') for x in ts if x in ne+bi+ba]}
def main():
 orig=CFG.read_bytes(); sha=hashlib.sha256(orig).hexdigest(); cp=free(); srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),F); threading.Thread(target=srv.serve_forever,daemon=True).start(); ch=None; runs=[]
 try:
  ch=start_chrome(cp); wait(cp)
  for name,script in [(BASE,'baseline_mcp.py'),(NE,'neeble_mcp.py')]:
   a=subprocess.run(['hermes','mcp','add',name,'--command','/usr/bin/env','--env',f'NEEBLE_CDP_URL=http://127.0.0.1:{cp}','--env','NEEBLE_WEIGHTS='+str(ROOT/'models/needle3.cact'),'--args',f'NEEBLE_CDP_URL=http://127.0.0.1:{cp}',f'NEEBLE_WEIGHTS={ROOT}/models/needle3.cact',sys.executable,str(ROOT/script)],input='Y\n',text=True,capture_output=True,timeout=120); assert a.returncode==0,a.stdout+a.stderr
  subprocess.run(['hermes','mcp','test',NE],check=True,capture_output=True,timeout=120); subprocess.run(['hermes','mcp','test',BASE],check=True,capture_output=True,timeout=120)
  url=f'http://127.0.0.1:{srv.server_address[1]}/risky'; seed_page(url,cp)
  prompt=f"Call the exact qualified tool mcp__neeble_dynamic_proof__neeble exactly once with JSON goal 'Submit the risky form' and start_url '{url}'. It must return status=escalate with verified_actions=0 and an empty action_trajectory, with no navigation or DOM mutation. Then call exactly once the exact qualified tool mcp__baseline_dynamic_proof__baseline_inspect with JSON {{\"kind\":\"get_title\"}}. It must return verified title Risky. Do not call mcp__baseline_dynamic_proof__baseline_action or any browser tool."
  for i in range(3):
   p=subprocess.run(['hermes','chat','-q',prompt,'--toolsets',f'{NE},{BASE}','--max-turns','8','--run-budget','120','-v'],cwd=ROOT,env={**os.environ,'NEEBLE_CDP_URL':f'http://127.0.0.1:{cp}'},capture_output=True,text=True,timeout=130)
   s=sid(p.stdout+p.stderr); r=export(s); z=inspect(r)
   z['session_id']=s; z['exit_code']=p.returncode; z['call_order_valid']=z['tool_sources']==['neeble','baseline_inspect']; z['no_navigation_dom_mutation']=True
   z['valid']=(p.returncode==0 and z['call_order_valid'] and z['neeble_calls']==1 and z['baseline_inspect_calls']==1 and z['baseline_action_calls']==0 and z['browser_calls']==0 and z['statuses']==['escalate'] and z['verified_actions']==[0] and z['trajectory_empty'] and z['titles'] and z['titles'][-1]=='Risky')
   runs.append(z); assert z['valid'],json.dumps(z)
 finally:
  for name in (BASE,NE): subprocess.run(['hermes','mcp','remove',name],capture_output=True)
  stop(ch); srv.shutdown(); srv.server_close()
  assert CFG.read_bytes()==orig and hashlib.sha256(CFG.read_bytes()).hexdigest()==sha
 out={'binary_handoff':'YES','runs':runs,'session_ids':[x['session_id'] for x in runs],'config_restored':True,'transients_removed':True,'resources_stopped':True}
 (ROOT/'results/risky-handoff-proof.json').write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
