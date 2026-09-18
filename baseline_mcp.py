"""Repo-local one-action MCP baseline; not Hermes built-in browser_exec."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from neeble import BrowserExecutor
from babench.runtime import canonicalize_action, verify_action, RISKY_ACTIONS

SAFE = {"goto","back","forward","reload","click_element","type_text","double_click","right_click","hover","press","scroll_into_view","focus","blur","clear","check","uncheck","select_option","scroll","snapshot","wait","get_title","get_url","get_text"}
SCHEMAS = [
 {"name":"baseline_action","description":"Baseline only: validate and execute exactly one safe browser action, then return verified state.","inputSchema":{"type":"object","required":["action"],"properties":{"action":{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"arguments":{"type":"object","properties":{"url":{"type":"string"},"element_id":{"type":"string"},"text":{"type":"string"}}}}}}}},
 {"name":"baseline_inspect","description":"Baseline safe inspection only: get_title or snapshot; never mutates the DOM.","inputSchema":{"type":"object","properties":{"kind":{"type":"string","enum":["get_title","snapshot"]}}}},
]
class Server:
 def __init__(self):
  # Connect lazily: Hermes performs MCP discovery before the fixture's CDP
  # endpoint is necessarily available.  Tool discovery must not disable the
  # server merely because the browser is not ready yet.
  self.ex=None; self.calls=0; self.verified=0; self.fallbacks=0; self.timings=[]
 def _ensure(self):
  if self.ex is None: self.ex=BrowserExecutor(os.environ["NEEBLE_CDP_URL"])
  return self.ex
 def _validation_state(self, snapshot):
  """Use executor's compact inner state, retaining display metadata."""
  inner=snapshot.get("state") if isinstance(snapshot,dict) else None
  while isinstance(inner,dict) and "elements" not in inner and isinstance(inner.get("state"),dict):
   inner=inner["state"]
  state=dict(inner) if isinstance(inner,dict) else dict(snapshot or {})
  for key in ("url","title","pages","text"):
   if key in snapshot and key not in state: state[key]=snapshot[key]
  return state
 def inspect(self, kind="snapshot"):
  ex=self._ensure(); t=time.perf_counter(); s=ex.snapshot(); self.timings.append({"kind":"state_acquisition","ms":(time.perf_counter()-t)*1000})
  if kind=="get_title": return {"verified":True,"title":s.get("title"),"url":s.get("url"),"state":s}
  return {"verified":True,**s}
 def action(self, action):
  ex=self._ensure(); self.calls+=1; t=time.perf_counter(); before=ex.snapshot(); acq=(time.perf_counter()-t)*1000
  if not isinstance(action,dict) or action.get("name") not in SAFE or action.get("name") in RISKY_ACTIONS:
   return {"verified":False,"error":"only one safe action is permitted","fallback":False,"state":before,"timing_ms":{"state_acquisition":acq,"validation":0,"executor":0}}
  validation_state=self._validation_state(before)
  action=canonicalize_action(action,validation_state); t=time.perf_counter(); v=verify_action(action,validation_state); val=(time.perf_counter()-t)*1000
  if not v.ok: return {"verified":False,"error":v.reason,"fallback":False,"state":before,"timing_ms":{"state_acquisition":acq,"validation":val,"executor":0}}
  t=time.perf_counter(); out=ex.execute(action); ex=(time.perf_counter()-t)*1000
  out.update({"action":action,"fallback":False,"verification_reason":v.reason,"timing_ms":{"state_acquisition":acq,"validation":val,"executor":ex}})
  self.timings.append(out["timing_ms"])
  if out.get("verified"): self.verified+=1
  return out
 def close(self):
  if self.ex is not None: self.ex.close()
def reply(i,r): print(json.dumps({"jsonrpc":"2.0","id":i,"result":r},separators=(",",":")),flush=True)
def main():
 s=Server()
 try:
  for line in sys.stdin:
   if not line.strip(): continue
   q=json.loads(line); i=q.get("id"); m=q.get("method")
   if m=="initialize": reply(i,{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"baseline-one-action","version":"0.1.0"}})
   elif m=="notifications/initialized": pass
   elif m=="tools/list": reply(i,{"tools":SCHEMAS})
   elif m=="tools/call":
    a=q.get("params",{}).get("arguments",{}); name=q.get("params",{}).get("name")
    try: out=s.action(a.get("action",{})) if name=="baseline_action" else s.inspect(a.get("kind","snapshot")); reply(i,{"content":[{"type":"text","text":json.dumps(out,separators=(",",":"))}]})
    except Exception as e: reply(i,{"isError":True,"content":[{"type":"text","text":json.dumps({"verified":False,"error":str(e)})}]})
   else: reply(i,{"error":f"unsupported method: {m}"})
 finally:
  s.close()
if __name__=="__main__": main()
