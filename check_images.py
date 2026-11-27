"""Display-image regression checks. All images, catalog and credentials are temporary."""
import tempfile,json,sqlite3,threading,hashlib,io,secrets,time
from pathlib import Path
import server,image_optimizer
from PIL import Image,ImageOps,ImageChops
from urllib.request import build_opener,ProxyHandler,Request
from urllib.error import HTTPError
with tempfile.TemporaryDirectory(prefix='landmade-images-test-') as temp:
 data=Path(temp);up=data/'uploads';up.mkdir();server.DATA=data;server.UP=up;server.DB=data/'catalog.sqlite3'
 original=Image.new('RGBA',(1500,1000),(100,150,200,128));original.save(up/'transparent.png')
 before=hashlib.sha256((up/'transparent.png').read_bytes()).hexdigest();key,entry=image_optimizer.optimize_image(up/'transparent.png',data)
 assert before==hashlib.sha256((up/'transparent.png').read_bytes()).hexdigest()
 for kind,variant in entry['variants'].items():
  file=data/'optimized'/variant['url'].split('/')[-1];encoded=Image.open(file);assert encoded.format=='WEBP';assert max(encoded.size)<=image_optimizer.PRESETS[kind][0]
  assert file.stat().st_size<=300000
  assert ImageChops.difference(encoded.getchannel('A'),original.resize(encoded.size,Image.Resampling.LANCZOS).getchannel('A')).getbbox() is None
 stamp=(data/'optimized/manifest.json').stat().st_mtime_ns;image_optimizer.optimize_image(up/'transparent.png',data);assert (data/'optimized/manifest.json').stat().st_mtime_ns==stamp
 noisy=Image.effect_noise((2400,1600),100).convert('RGB');noisy.save(up/'noisy.png');_,hard=image_optimizer.optimize_image(up/'noisy.png',data)
 assert all(v['bytes']<=300000 for v in hard['variants'].values())
 assert hard['variants']['display']['width']<2240
 portrait=Image.new('RGB',(200,100),'red');exif=Image.Exif();exif[274]=6;portrait.save(up/'rotate.jpg',exif=exif)
 _,rotated=image_optimizer.optimize_image(up/'rotate.jpg',data);assert rotated['variants']['display']['width']==100 and rotated['variants']['display']['height']==200
 frames=[Image.new('RGB',(16,16),c) for c in ('red','blue')];frames[0].save(up/'animated.gif',save_all=True,append_images=frames[1:],duration=50,loop=0);assert image_optimizer.optimize_image(up/'animated.gif',data)[1] is None
 catalog={'categories':[{'id':'home','en':'HOME','zh':'家居'}],'products':[{'id':'p','en':'Product','zh':'产品','category':'home','published':True,'created':1,'images':['/uploads/transparent.png'],'cardImage':'/uploads/transparent.png','imageStatuses':{'/uploads/transparent.png':'listed'},'channelBanner':''}],'settings':{'slides':[]}}
 with sqlite3.connect(server.DB) as db:db.execute('CREATE TABLE catalog(id INTEGER PRIMARY KEY,body TEXT NOT NULL)');db.execute('INSERT INTO catalog VALUES(1,?)',(json.dumps(catalog),))
 client=server.client_state(True);assert key in client['mediaVariants'] and '/uploads/rotate.jpg' not in client['mediaVariants']
 revision=client['_revision'];server.save_state(client,require_revision=True);saved=server.read_state();assert 'mediaVariants' not in saved and '_mediaRevision' not in saved
 assert saved['products']==catalog['products']
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(http.server_port);opener=build_opener(ProxyHandler({}))
 try:
  with opener.open(base+entry['variants']['card']['url']) as r:assert r.status==200 and r.headers['Content-Type']=='image/webp' and len(r.read())==entry['variants']['card']['bytes']
  try:opener.open(base+'/optimized/manifest.json');raise AssertionError('manifest exposed')
  except HTTPError as e:assert e.code==404
  with opener.open(base+'/api/revision') as r:assert json.load(r)['mediaRevision']==image_optimizer.load_manifest(data)[1]
  fresh=Image.new('RGB',(800,600),'green');fresh.save(up/'new.png');image_optimizer.queue_images([up/'new.png'],data)
  for _ in range(100):
   if '/uploads/new.png' in image_optimizer.load_manifest(data)[0]:break
   time.sleep(.02)
  assert '/uploads/new.png' in image_optimizer.load_manifest(data)[0]
  print('PASS: non-destructive variants, alpha, EXIF rotation, dimension/size bounds, idempotence, animation preserved, no catalog pollution, WebP serving, manifest protection, media revision and future-upload background compression.')
 finally:http.shutdown();http.server_close()
