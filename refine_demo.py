from pathlib import Path
import subprocess,sqlite3,json,time
R=Path(__file__).parent;A=R/'static/assets'
def crop(name,y,x,h,w,source):
 subprocess.run(['sips','--cropToHeightWidth',str(h),str(w),'--cropOffset',str(y),str(x),source,'--out',str(A/(name+'.png'))],check=True,stdout=subprocess.DEVNULL)
src='/Users/yiy9xi/.codex/generated_images/01a1ca15-67be-7710-8204-e5af2536e520/exec-2342aab7-459e-4a84-aa2a-1b1cba781545.png'
crop('fan',220,460,350,460,src)
src='/Users/yiy9xi/.codex/generated_images/01a1ca15-67be-7710-8204-e5af2536e520/exec-79f05b44-0823-43d3-b189-6cc6ed64f1a4.png'
items=[('gift-pen','Machined Aluminum Pen','精密铝笔',475,271,242,234),('gift-tea','Ceramic Tea Set','陶瓷茶具套装',475,518,242,237),('gift-notebook','Notebook & Pen Set','皮革笔记本套装',897,17,333,242),('gift-case','Business Card Case','金属名片盒',897,271,196,234),('gift-cups','Premium Cup Set','雅致茶杯套装',897,518,217,237),('gift-travel','Travel Tea Kit','便携茶具套装',1302,17,207,242),('gift-bag','Thermos & Travel Bag','保温杯随行套装',1157,271,303,234),('gift-charge','Wireless Charging Pad','无线充电底座礼盒',1187,518,191,237),('gift-power','Power Bank Gift','充电宝礼盒',1572,17,199,242),('gift-lamp','Sculptural Table Lamp','艺术台灯礼盒',1442,518,329,237)]
with sqlite3.connect(R/'data/catalog.sqlite3') as db:
 state=json.loads(db.execute('select body from catalog where id=1').fetchone()[0])
 for n,en,zh,y,x,h,w in items:
  crop(n,y,x,h,w,src)
  if any(p['id']==n for p in state['products']):continue
  pic='/assets/'+n+'.png'
  state['products'].append(dict(id=n,en=en,zh=zh,category='gifts',description='Considered objects. Lasting impressions.',descriptionZh='精心设计，为每一份心意。',cover=pic,hero=pic,images=[pic],published=True,created=round(time.time()*1000)-30*86400000-len(state['products'])*86400000,demo=True))
 # Gift hero is a photo, never a whole screenshot.
 crop('gifts-hero',90,387,234,367,src)
 next(c for c in state['categories'] if c['id']=='gifts')['hero']='/assets/gifts-hero.png'
 db.execute('update catalog set body=? where id=1',(json.dumps(state,ensure_ascii=False),))
print('Demo catalog enriched; clean product photography ready.')
