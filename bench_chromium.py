from __future__ import annotations
import json, statistics, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import needle

HTML='''<html><body><button id="login" onclick="document.body.dataset.clicked='yes'">Log in</button><input id="search"><div style="height:2000px">results</div></body></html>'''

def run(cases=40, weights='models/needle3.cact'):
  with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True); page=browser.new_page()
    actions=[]
    def click_element(element_id: str):
      "Click a visible browser element by stable id and verify it exists."
      page.locator('#'+element_id).click(); return {'verified': page.locator('#'+element_id).count()==1}
    def type_text(element_id: str, text: str):
      "Type text into a visible input by stable id and verify its value."
      page.locator('#'+element_id).fill(text); return {'verified': page.locator('#'+element_id).input_value()==text}
    def scroll(direction: str):
      "Scroll the browser page up or down."; page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); return {'verified': page.evaluate('window.scrollY')>0}
    tools=[needle.tool(click_element),needle.tool(type_text),needle.tool(scroll)]
    prompts=['Click the login button with element id login','Type Enschede into the search field with element id search','Scroll down the page']
    rows=[]
    for i in range(cases):
      page.set_content(HTML); start=time.perf_counter(); r=needle.Needle(tools=tools,weights=weights).run(prompts[i%3],max_new_tokens=64); ms=(time.perf_counter()-start)*1000
      verified=bool(r.get('results')) and all(x.get('verified') for x in r['results'] if isinstance(x,dict))
      rows.append({'ms':ms,'success':bool(r.get('success')),'verified':verified,'prefill_tps':r.get('prefill_tps'),'decode_tps':r.get('decode_tps'),'prompt':prompts[i%3]})
    browser.close()
  s={'backend':'needle3-playwright-chromium','cases':cases,'verified_actions':sum(x['verified'] for x in rows),'success_rate':sum(x['verified'] for x in rows)/cases,'latency_ms_mean':statistics.mean(x['ms'] for x in rows),'latency_ms_p50':statistics.median(x['ms'] for x in rows),'actions_per_minute':cases/(sum(x['ms'] for x in rows)/60000),'prefill_tps_median':statistics.median(x['prefill_tps'] for x in rows),'decode_tps_median':statistics.median(x['decode_tps'] for x in rows),'note':'Real headless Chromium fixture with verified DOM actions.'}
  Path('results').mkdir(exist_ok=True); Path('results/needle3-playwright.json').write_text(json.dumps({'summary':s,'runs':rows},indent=2)+'\n'); print(json.dumps(s,indent=2))
if __name__=='__main__': run()
