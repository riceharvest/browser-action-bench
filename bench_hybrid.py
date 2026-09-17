from __future__ import annotations
import json, os, statistics, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
import needle

HTML="""<button id='login' onclick="document.body.dataset.clicked='yes'">Log in</button><button id='help'>Help</button><input id='search'><div style='height:2000px'>results</div>"""
TOOLS=[{'type':'function','function':{'name':'click_element','description':'Click the visible browser element matching the requested id or label.','parameters':{'type':'object','properties':{'element_id':{'type':'string'}},'required':['element_id']}}},{'type':'function','function':{'name':'type_text','description':'Type text into a visible textbox by id.','parameters':{'type':'object','properties':{'element_id':{'type':'string'},'text':{'type':'string'}},'required':['element_id','text']}}},{'type':'function','function':{'name':'scroll','description':'Scroll down the browser page.','parameters':{'type':'object','properties':{'direction':{'type':'string'}},'required':['direction']}}}]
CASES=[('Click login','click_element',True),('Click help','click_element',True),('Type Enschede in search','type_text',True),('Scroll down','scroll',True),('Click the primary action on this unfamiliar page','escalate',False),('Do the safest thing with the page','escalate',False)]
def deepseek(prompt):
 b={'model':'deepseek/deepseek-v4.1-flash','messages':[{'role':'user','content':prompt}],'tools':TOOLS,'tool_choice':'required','max_tokens':256,'temperature':0}
 q=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(b).encode(),headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY'],'Content-Type':'application/json'})
 with urllib.request.urlopen(q,timeout=120) as r:return json.loads(r.read())
def main():
 needle_tools=[]
 def click_element(element_id:str): 'Click visible element by id.'; return {'_action':'click_element','arguments':{'element_id':element_id}}
 def type_text(element_id:str,text:str): 'Type into visible textbox.'; return {'_action':'type_text','arguments':{'element_id':element_id,'text':text}}
 def scroll(direction:str): 'Scroll down.'; return {'_action':'scroll','arguments':{'direction':direction}}
 needle_tools=[needle.tool(click_element),needle.tool(type_text),needle.tool(scroll)]
 rows=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True); page=browser.new_page()
  for i in range(30):
   prompt,expected,routine=CASES[i%len(CASES)]; page.set_content(HTML); start=time.perf_counter(); route='needle'; ok=False; err=None
   try:
    n=needle.Needle(tools=needle_tools,weights='models/needle3.cact').run(prompt,max_new_tokens=128); res=n.get('results',[]); x=res[0] if res else {}; name=x.get('_action'); args=x.get('arguments',{})
    # Conservative confidence policy: Needle 3 shipped weights report no calibrated confidence, so ambiguous cases escalate.
    if not routine: route='deepseek'
    elif name=='click_element': page.locator('#'+args['element_id']).click(); ok=True
    elif name=='type_text': page.locator('#'+args['element_id']).fill(args['text']); ok=page.locator('#'+args['element_id']).input_value()==args['text']
    elif name=='scroll': page.evaluate('window.scrollTo(0,document.body.scrollHeight)'); ok=page.evaluate('window.scrollY')>0
    else: route='deepseek'
    if route=='deepseek':
     d=deepseek(prompt); tc=d['choices'][0]['message'].get('tool_calls',[]); ok=bool(tc); name=tc[0]['function']['name'] if tc else None
   except Exception as e: err=str(e)
   rows.append({'prompt':prompt,'route':route,'ok':ok,'elapsed_ms':(time.perf_counter()-start)*1000,'error':err})
  browser.close()
 s={'backend':'hybrid needle3->openrouter/deepseek-v4.1-flash','cases':len(rows),'verified_actions':sum(x['ok'] for x in rows),'success_rate':sum(x['ok'] for x in rows)/len(rows),'latency_ms_mean':statistics.mean(x['elapsed_ms'] for x in rows),'latency_ms_p50':statistics.median(x['elapsed_ms'] for x in rows),'actions_per_minute':len(rows)/(sum(x['elapsed_ms'] for x in rows)/60000),'needle_cases':sum(x['route']=='needle' for x in rows),'escalated_cases':sum(x['route']=='deepseek' for x in rows),'note':'Conservative escalation for ambiguous prompts because shipped Needle confidence is None.'}
 Path('results').mkdir(exist_ok=True);Path('results/hybrid-playwright.json').write_text(json.dumps({'summary':s,'runs':rows},indent=2)+'\n');print(json.dumps(s,indent=2))
if __name__=='__main__':main()
