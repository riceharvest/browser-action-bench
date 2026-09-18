from __future__ import annotations
import json, os, statistics, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

TOOLS=[{'type':'function','function':{'name':'click_element','description':'Click a visible browser element by stable id.','parameters':{'type':'object','properties':{'element_id':{'type':'string'}},'required':['element_id']}}},{'type':'function','function':{'name':'type_text','description':'Type text into a visible input by stable id.','parameters':{'type':'object','properties':{'element_id':{'type':'string'},'text':{'type':'string'}},'required':['element_id','text']}}},{'type':'function','function':{'name':'scroll','description':'Scroll the page down.','parameters':{'type':'object','properties':{'direction':{'type':'string'}},'required':['direction']}}}]
CASES=[('Click the login button with element id login', 'click_element'),('Type Enschede into the search field with element id search','type_text'),('Scroll down the page','scroll')]
HTML="<button id='login' onclick=\"document.body.dataset.clicked='yes'\">Log in</button><input id='search'><div style='height:2000px'>results</div>"
def call(prompt):
 b={'model':'deepseek/deepseek-v4.1-flash','messages':[{'role':'user','content':prompt}],'tools':TOOLS,'tool_choice':'required','max_tokens':256,'temperature':0}
 req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(b).encode(),headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY'],'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read())
def main():
 rows=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True); page=browser.new_page()
  for i in range(30):
   page.set_content(HTML); prompt,expected=CASES[i%3]; t=time.perf_counter(); err=None; ok=False
   try:
    out=call(prompt); msg=out['choices'][0]['message']; tc=msg.get('tool_calls',[]); args=json.loads(tc[0]['function']['arguments']) if tc else {}; name=tc[0]['function']['name'] if tc else ''
    if name=='click_element': page.locator('#'+args['element_id']).click(); ok=page.locator('#'+args['element_id']).count()==1
    elif name=='type_text': page.locator('#'+args['element_id']).fill(args['text']); ok=page.locator('#'+args['element_id']).input_value()==args['text']
    elif name=='scroll': page.evaluate('window.scrollTo(0,document.body.scrollHeight)'); ok=page.evaluate('window.scrollY')>0
   except Exception as e: err=str(e)
   rows.append({'prompt':prompt,'expected':expected,'ok':ok,'elapsed_ms':(time.perf_counter()-t)*1000,'error':err})
  browser.close()
 s={'backend':'direct-openrouter/deepseek/deepseek-v4.1-flash+playwright','cases':len(rows),'verified_actions':sum(x['ok'] for x in rows),'success_rate':sum(x['ok'] for x in rows)/len(rows),'latency_ms_mean':statistics.mean(x['elapsed_ms'] for x in rows),'latency_ms_p50':statistics.median(x['elapsed_ms'] for x in rows),'actions_per_minute':len(rows)/(sum(x['elapsed_ms'] for x in rows)/60000),'excluded_from_timing':['Hermes startup','Hermes conversation loop','MCP dispatch','browser startup','browser state acquisition'],'note':'Direct provider microbenchmark only; not a normal Hermes/browser baseline.'}
 Path('results').mkdir(exist_ok=True);Path('results/deepseek-playwright.json').write_text(json.dumps({'summary':s,'runs':rows},indent=2)+'\n');print(json.dumps(s,indent=2))
if __name__=='__main__':main()
