"""Read-only Chromium visual/layout smoke checks in an isolated browser profile."""
from pathlib import Path
import http.server,threading,tempfile,subprocess,json
import server
STATIC=Path(__file__).parent/'static'
CHECK=r'''
(async()=>{const results=[];const check=(ok,name)=>{results.push({name,ok:!!ok});if(!ok)throw Error(name)};const wait=async(selector)=>{for(let n=0;n<100;n++){if(document.querySelector(selector))return document.querySelector(selector);await new Promise(r=>setTimeout(r,50))}throw Error('Missing '+selector)};const sleep=()=>new Promise(r=>setTimeout(r,350));try{
 const hero=await wait('#home-hero');check(Math.abs(hero.clientWidth/hero.clientHeight-16/9)<.02,'homepage banner 16:9');
 const card=await wait('.card-photo');check(Math.abs(card.clientWidth-card.clientHeight)<2,'recommendation square');check(getComputedStyle(card.querySelector('img,video')).objectFit==='cover','square cropping');
 window.scrollTo(0,600);check(Math.abs(document.querySelector('.site-header').getBoundingClientRect().top)<1,'navigation fixed during scroll');
 check(!document.documentElement.scrollWidth||document.documentElement.scrollWidth<=innerWidth+1,'no horizontal page overflow');
 const nav=document.querySelector('.nav a');check(getComputedStyle(nav.querySelector('.nav-zh')).opacity==='0','English label shown by default');
 const category=document.querySelector('.nav a[href*="category/"]');location.hash=category.hash;await wait('#category-grid');const heroLink=document.querySelector('.channel .hero-backdrop');if(heroLink)check(heroLink.tagName==='A'&&heroLink.hash.startsWith('#/product/'),'channel banner links to product');else check(!document.querySelector('.site-header').classList.contains('overlay'),'removed banner leaves room for navigation');const link=heroLink||document.querySelector('#category-grid .card');
 const square=document.querySelector('#category-grid .card-photo');check(Math.abs(square.clientWidth-square.clientHeight)<2,'channel cards square');location.hash=link.hash;await wait('.detail-photos');const cols=[...document.querySelectorAll('.detail-photo-column')];const tops=cols.filter(c=>c.firstElementChild).map(c=>c.firstElementChild.getBoundingClientRect().top);check(tops.length>0&&Math.max(...tops)-Math.min(...tops)<1,'detail first photos top-aligned');check(cols.every(col=>[...col.children].every((photo,i)=>!i||Math.abs(photo.getBoundingClientRect().top-col.children[i-1].getBoundingClientRect().bottom-(innerWidth<=600?8:12))<1)),'detail column gaps uniform');document.querySelector('[data-photo]').click();const viewer=await wait('#viewer[open]');check(viewer.clientHeight>innerHeight*.95,'viewer fills viewport');viewer.close();check(!viewer.open,'viewer closes');
}catch(e){results.push({name:e.message,ok:false})}const out=document.createElement('pre');out.id='compat-results';out.textContent=JSON.stringify({userAgent:navigator.userAgent,width:innerWidth,results});document.body.append(out)})();
'''
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/state':body=json.dumps(server.public_state()).encode();mime='application/json'
  elif path=='/compat-check.js':body=CHECK.encode();mime='text/javascript'
  else:
   root=server.UP if path.startswith('/uploads/') else STATIC
   p=(root/(path[len('/uploads/'):] if path.startswith('/uploads/') else ('index.html' if path=='/' else path.lstrip('/')))).resolve()
   if not p.is_relative_to(root.resolve()) or not p.is_file():self.send_error(404);return
   body=p.read_bytes();mime={'.html':'text/html','.js':'text/javascript','.css':'text/css'}.get(p.suffix,'application/octet-stream')
   if p.name=='index.html':body=body.replace(b'</body>',b'<script src="/compat-check.js" defer></script></body>')
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers()
  try:self.wfile.write(body)
  except (BrokenPipeError,ConnectionResetError):pass
with tempfile.TemporaryDirectory(prefix='landmade-browser-') as profile:
 http=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  for width,height in [(1366,900),(1920,1080),(390,844)]:
   run=subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless','--no-first-run','--disable-background-networking','--user-data-dir='+profile,'--window-size=%s,%s'%(width,height),'--dump-dom','--virtual-time-budget=12000','http://127.0.0.1:'+str(http.server_port)],capture_output=True,text=True,timeout=45)
   import re,html
   match=re.search(r'<pre id="compat-results">(.*?)</pre>',run.stdout,re.S)
   if not match:raise RuntimeError('Browser did not return results: '+run.stderr[-500:])
   result=json.loads(html.unescape(match.group(1)));print(json.dumps(result,ensure_ascii=False),flush=True)
   assert all(x['ok'] for x in result['results'])
 finally:http.shutdown()
