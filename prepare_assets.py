from pathlib import Path
import shutil, subprocess, json, sqlite3, time
ROOT=Path(__file__).parent
A=ROOT/'static/assets'
shutil.copy2('/Users/yiy9xi/Desktop/2x/资源 1@2x.png',A/'logo.png')
source='/Users/yiy9xi/.codex/generated_images/01a1ca15-67be-7710-8204-e5af2536e520/exec-94315ea2-2e2e-4dab-9d93-194f2d47c23c.png'
def crop(name,y,x,h,w,src=source):
 subprocess.run(['sips','--cropToHeightWidth',str(h),str(w),'--cropOffset',str(y),str(x),src,'--out',str(A/name)],check=True,stdout=subprocess.DEVNULL)
# Extract standalone product photos from the approved demonstration artwork.
crop('fan.png',71,495,285,396)
items=[('kettle',489,34,272,285),('lamp',489,331,272,281),('shaver',489,625,272,282),('ceramic',940,34,232,285),('pen',940,331,232,281),('purifier',940,625,232,282),('thermos',1238,34,236,285),('clock',1238,331,236,281),('light',1238,625,236,282)]
for name,y,x,h,w in items:crop(name+'.png',y,x,h,w)
# Real angle/detail images for the sample fan, from the approved gallery artwork.
src='/Users/yiy9xi/.codex/generated_images/01a1ca15-67be-7710-8204-e5af2536e520/exec-2342aab7-459e-4a84-aa2a-1b1cba781545.png'
info=subprocess.check_output(['sips','-g','pixelWidth',src],text=True)
# Gallery source is 1024px wide.
for name,y,x,h,w in [('fan-side',607,32,290,310),('fan-rim',658,355,239,313),('fan-front',607,682,290,310),('fan-room',911,32,266,376),('fan-control',911,421,266,247),('fan-top',911,682,266,310)]:crop(name+'.png',y,x,h,w,src)
cats=[{'id':i,'en':e,'zh':z,'title':t,'subtitle':s,'hero':'','heroProduct':''} for i,e,z,t,s in [('gifts','GIFTS','商务礼赠','Business Gifts','Considered objects. Lasting impressions.'),('tasks','TASKS','任务相关','Mission Objects','Designed for a purpose.'),('home','HOME','家居系列','Objects for Home','Quiet details. Everyday living.'),('appliances','APPLIANCES','小家电','Small Appliances','Thoughtful technology. Simple living.'),('office','OFFICE','办公用品','The Workspace','A little clarity for your everyday.')]]
products=[]
for idx,(id,en,zh,cat) in enumerate([('fan','Air Ring','环形桌面风扇','appliances'),('kettle','Electric Kettle','电热水壶','appliances'),('lamp','Articulated Desk Lamp','多角度台灯','office'),('shaver','Electric Shaver','电动剃须刀','appliances'),('ceramic','Porcelain Carafe Set','瓷质冷水壶套装','home'),('pen','Pen Tray & Pen','金属笔盘与签字笔','office'),('purifier','Portable Air Purifier','便携空气净化器','appliances'),('thermos','Gift Thermos','礼赠保温杯','gifts'),('clock','Analog Desk Clock','桌面模拟时钟','home'),('light','Frosted Table Light','磨砂台灯','home')]):
 pic='/assets/'+id+'.png'
 imgs=[pic] if id!='fan' else [pic]+['/assets/fan-'+x+'.png' for x in ['side','rim','front','room','control','top']]
 products.append(dict(id=id,en=en,zh=zh,category=cat,description='Thoughtfully designed for everyday living.',descriptionZh='以简洁形态，融入日常生活。',cover=pic,hero=pic,images=imgs,published=True,created=round(time.time()*1000)-idx*86400000,demo=True))
state={'categories':cats,'products':products,'settings':{'headline':'Less, but\nbetter.','tagline':'让设计，回归生活。','slides':[{'image':'/assets/fan.png','product':'fan','title':'Less, but\nbetter.','subtitle':'让设计，回归生活。'},{'image':'/assets/kettle.png','product':'kettle','title':'Everyday,\nconsidered.','subtitle':'为日常，多想一步。'}]}}
for c in cats:
 p=next((p for p in products if p['category']==c['id']),products[0]);c['hero']=p['hero'];c['heroProduct']=p['id']
db=sqlite3.connect(ROOT/'data/catalog.sqlite3');db.execute('CREATE TABLE IF NOT EXISTS catalog(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)');db.execute('INSERT OR IGNORE INTO catalog VALUES(1,?)',(json.dumps(state,ensure_ascii=False),));db.commit();db.close()
print('Demo assets and catalog ready.')
