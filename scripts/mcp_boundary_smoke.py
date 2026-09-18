"""Real one-call stdio MCP smoke against an ephemeral HTTP fixture and Chromium."""
from __future__ import annotations
import http.server, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_lifecycle import stop_mcp_then_chrome
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<!doctype html><title>step 1</title><script>
function advance(id,title,label){var old=document.getElementById(id); old.remove(); document.title=title; var b=document.createElement('button'); b.id=label.toLowerCase(); b.textContent=label; b.onclick=function(){advance(b.id, label==='Continue'?'step 3':'done', label==='Continue'?'Finish':'Done')}; document.body.appendChild(b)}
</script><button id="login" onclick="advance('login','step 2','Continue')">Login</button>'''
        self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]

def rpc(proc, ident, method, params=None):
    proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params or {}})+'\n'); proc.stdin.flush()
    return json.loads(proc.stdout.readline())

def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cdp = free_port()
    chrome = subprocess.Popen([sys.executable, '-c', 'import playwright.sync_api as s; p=s.sync_playwright().start(); b=p.chromium.launch(headless=True, args=["--remote-debugging-port='+str(cdp)+'"]); b.new_page(); import time; time.sleep(300)'])
    mcp = None
    try:
        deadline=time.time()+15
        while time.time()<deadline:
            try:
                with socket.create_connection(('127.0.0.1', cdp), .2): break
            except OSError: time.sleep(.1)
        env=os.environ.copy(); env['NEEBLE_CDP_URL']=f'http://127.0.0.1:{cdp}'; env['NEEBLE_RESPONSE_TIMEOUT_S']='30'
        mcp=subprocess.Popen([sys.executable, str(ROOT/'neeble_mcp.py')], cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        rpc(mcp,1,'initialize')
        mcp.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n'); mcp.stdin.flush()
        response=rpc(mcp,3,'tools/call',{'arguments':{'goal':'Click Login, then Continue, then Finish','start_url':f'http://127.0.0.1:{server.server_address[1]}/','max_steps':4}})
        payload=json.loads(response['result']['content'][0]['text'])
        assert len(payload['steps']) >= 4, payload
        assert payload['verified_actions'] >= 4, payload
        assert [item['name'] for item in payload['action_trajectory'][:4]] == ['goto', 'click_element', 'click_element', 'click_element'], payload
        assert payload['state']['title'] == 'done', payload
        assert payload['verified'] is True and payload['goal_completed'] is False, payload
        assert payload['termination'] == 'step_budget_exhausted', payload
        print(json.dumps({'status':'PASS','trajectory':payload['action_trajectory'],'result':{k:payload[k] for k in ('status','verified','verified_actions','goal_completed','termination','reason')}}))
    finally:
        _, _, stderr = stop_mcp_then_chrome(mcp, chrome)
        if stderr: print(stderr, file=sys.stderr, end='')
        server.shutdown(); server.server_close()
if __name__ == '__main__': main()
