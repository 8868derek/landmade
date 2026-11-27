"""Integration checks run against an isolated temporary database and upload folder."""
from http.cookiejar import CookieJar
import secrets, hashlib
import server, tempfile, pathlib, shutil, threading, urllib.request, urllib.error, json, base64, zipfile, io, http.cookiejar
with tempfile.TemporaryDirectory(prefix='landmade-check-') as tmp:
 server.DATA=pathlib.Path(tmp);server.DB=server.DATA/'catalog.sqlite3';server.UP=server.DATA/'uploads';server.UP.mkdir();shutil.copy2(pathlib.Path(__file__).parent/'data/catalog.sqlite3',server.DB)
 # Exercise backup with test uploads, not the user's increasingly large media library.
 def fixture_media(value):
  if isinstance(value,str):return '/assets/logo.png' if value.startswith('/uploads/') else value
  if isinstance(value,list):return [fixture_media(v) for v in value]
  if isinstance(value,dict):return {fixture_media(k):fixture_media(v) for k,v in value.items()}
  return value
 server.save_state(fixture_media(server.read_state()))
 test_password=secrets.token_urlsafe(20);salt=secrets.token_hex(32);server.AUTH_FILE=server.DATA/'auth.json';server.AUTH_FILE.write_text(json.dumps({'salt':salt,'digest':hashlib.pbkdf2_hmac('sha256',test_password.encode(),bytes.fromhex(salt),200000).hex()}))
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(http.server_port)
 jar=CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 def request(path,data=None,headers=None):
  hdr={'Content-Type':'application/json','X-Landmade':'local'};hdr.update(headers or {})
  req=urllib.request.Request(url+path,None if data is None else json.dumps(data).encode(),hdr)
  try:
   with opener.open(req) as r:
    status,raw=r.status,r.read()
    if path=='/api/state' and data is not None and status==200:data['_revision']=json.loads(raw)['revision']
    return status,raw
  except urllib.error.HTTPError as e:return e.code,e.read()
 try:
  assert request('/')[0]==200
  assert request('/api/state')[0]==200
  assert request('/api/state?admin=1')[0]==401
  assert request('/api/backup')[0]==401
  for path in ('/api/state','/api/upload','/api/restore'):assert request(path,{})[0]==401
  assert request('/api/auth/login',{'password':'incorrect'})[0]==401
  assert request('/api/auth/login',{'password':test_password})[0]==200
  assert json.loads(request('/api/auth/session')[1])['authenticated'] is True
  cookie=next(iter(jar));assert cookie.has_nonstandard_attr('HttpOnly') and cookie.get_nonstandard_attr('SameSite')=='Strict'
  status,raw=request('/api/state?admin=1');assert status==200;state=json.loads(raw);baseline=json.loads(raw)
  png=(pathlib.Path(__file__).parent/'static/assets/logo.png').read_bytes()
  status,raw=request('/api/upload',{'files':[{'data':base64.b64encode(png).decode()}]});assert status==200,raw
  pic=json.loads(raw)['images'][0];assert request(pic)[1]==png
  mp4=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'+b'\x00\x00\x00\x08mdat'
  status,raw=request('/api/upload',{'files':[{'data':base64.b64encode(mp4).decode()}]});assert status==200,raw
  video=json.loads(raw)['images'][0];assert video.endswith('.mp4') and request(video)[1]==mp4
  assert request(video,headers={'Range':'bytes=4-11'})==(206,mp4[4:12])
  assert request(video,headers={'Range':'bytes=-8'})==(206,mp4[-8:])
  assert request(video,headers={'Range':'bytes=999-1000'})[0]==416
  p=dict(id='integration-test',en='Test Product',zh='测试产品',category=state['categories'][0]['id'],description='',descriptionZh='',cover=pic,hero=pic,images=[pic,video],published=True,created=1)
  p['imageStatuses']={pic:'making'};p['banner']=pic;p['cardImage']=pic;p['mediaNames']={pic:'Front photo',video:'Product video'};p['descriptionZh']='Product description';p['categories']=[p['category'],state['categories'][1]['id']]
  stale=json.loads(json.dumps(state))
  state['products'].append(p);assert request('/api/state',state)[0]==200
  assert request('/api/state',stale)[0]==409
  assert any(p['id']=='integration-test' for p in json.loads(request('/api/state?admin=1')[1])['products'])
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['imageStatuses'][pic]=='making'
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['banner']==pic
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['mediaNames'][pic]=='Front photo'
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['cardImage']==pic
  wrong_card=json.loads(json.dumps(state));wrong_card['products'][-1]['cardImage']='/assets/not-in-gallery.png';assert request('/api/state',wrong_card)[0]==400
  # Manual arrivals persist independently from banners and product publication.
  original_slides=json.loads(json.dumps(state['settings']['slides']))
  state['settings']['newArrivals']=['integration-test'];assert request('/api/state',state)[0]==200
  assert json.loads(request('/api/state?admin=1')[1])['settings']['newArrivals']==['integration-test']
  assert json.loads(request('/api/state')[1])['settings']['newArrivals'][0]=='integration-test'
  state['settings']['newArrivals']=[];assert request('/api/state',state)[0]==200
  after=json.loads(request('/api/state?admin=1')[1])
  assert after['settings']['newArrivals']==[] and after['products'][-1]['published']
  assert after['settings']['slides']==original_slides
  # Home collection order persists without changing arrivals, banners or products.
  before_arrivals=json.loads(json.dumps(state['settings'].get('newArrivals')))
  state=json.loads(request('/api/state?admin=1')[1])
  before_products=json.loads(json.dumps(state['products']))
  state['settings']['homeCollectionOrder']=[p['id'] for p in reversed(state['products'])]
  assert request('/api/state',state)[0]==200
  ordered=json.loads(request('/api/state?admin=1')[1])
  assert ordered['settings']['homeCollectionOrder']==state['settings']['homeCollectionOrder']
  storefront=json.loads(request('/api/state')[1])
  visible={p['id'] for p in storefront['products']}
  assert storefront['settings']['homeCollectionOrder']==[pid for pid in state['settings']['homeCollectionOrder'] if pid in visible]
  assert ordered['products']==before_products and ordered['settings']['newArrivals']==before_arrivals
  assert ordered['settings']['slides']==original_slides
  # Removing a channel hero must stay removed after canonical synchronization.
  guest_slides=json.loads(request('/api/state')[1])['settings']['slides']
  removed_channel=state['categories'][0]
  removed_channel.update(hero='',heroProduct='',heroMode='custom')
  assert request('/api/state',state)[0]==200
  removed=json.loads(request('/api/state')[1])
  hero=next(c for c in removed['categories'] if c['id']==removed_channel['id'])
  assert hero['hero']=='' and hero['heroProduct']=='' and hero['heroMode']=='custom'
  assert any(p['id']=='integration-test' for p in removed['products'])
  assert removed['settings']['slides']==guest_slides
  assert json.loads(request('/api/state?admin=1')[1])['settings']['slides']==original_slides
  first,second=state['categories'][:2]
  first['hidden']=True;assert request('/api/state',state)[0]==200
  public=json.loads(request('/api/state')[1]);assert first['id'] not in [c['id'] for c in public['categories']]
  shown=next(p for p in public['products'] if p['id']=='integration-test');assert shown['category']==second['id']
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['category']==first['id']
  second['hidden']=True;assert request('/api/state',state)[0]==200
  assert not any(p['id']=='integration-test' for p in json.loads(request('/api/state')[1])['products'])
  assert any(p['id']=='integration-test' for p in json.loads(request('/api/state?admin=1')[1])['products'])
  first['hidden']=False;second['hidden']=False;assert request('/api/state',state)[0]==200
  invalid=json.loads(json.dumps(state));invalid['products'][-1]['imageStatuses'][pic]='invalid';assert request('/api/state',invalid)[0]==400
  state['categories'][0]['zh']='改名测试';assert request('/api/state',state)[0]==200
  assert json.loads(request('/api/state?admin=1')[1])['products'][-1]['category']==baseline['categories'][0]['id']
  status,backup=request('/api/backup');assert status==200
  z=zipfile.ZipFile(io.BytesIO(backup));assert 'catalog.json' in z.namelist();assert pic.lstrip('/') in z.namelist();assert video.lstrip('/') in z.namelist()
  state['products'].pop();assert request('/api/state',state)[0]==200
  restored=request('/api/restore',{'data':base64.b64encode(backup).decode()});assert restored[0]==200,restored
  state['_revision']=json.loads(request('/api/state?admin=1')[1])['_revision']
  assert any(p['id']=='integration-test' for p in json.loads(request('/api/state?admin=1')[1])['products'])
  assert request('/api/upload',{'files':[{'data':base64.b64encode(b'not image').decode()}]})[0]==400
  assert request('/api/state',{'products':[]})[0]==400
  assert request('/api/state',state,{'Origin':'http://example.com'})[0]==403
  assert request('/api/state',state,{'X-Landmade':'wrong'})[0]==403
  assert request('/server.py')[0]==404
  assert request('/uploads/../catalog.sqlite3')[0]==404
  assert request('/api/state',headers={'Host':'untrusted.example:'+str(http.server_port)})[0]==403
  http.allowed_hosts={'127.0.0.1','localhost','192.168.50.10'}
  http.lan_enabled=True
  lan_host='192.168.50.10:'+str(http.server_port)
  assert server.allowed_peer('192.168.50.22',http.lan_enabled)
  assert server.allowed_peer('192.168.51.22',http.lan_enabled)
  assert not server.allowed_peer('8.8.8.8',http.lan_enabled)
  assert request('/api/state?admin=1',headers={'Host':lan_host})[0]==200
  assert request('/api/upload',{'files':[{'data':base64.b64encode(png).decode()}]}, {'Host':lan_host,'Origin':'http://'+lan_host})[0]==200
  assert request('/api/upload',{}, {'Host':lan_host,'Origin':'http://untrusted.example'})[0]==403
  bad=io.BytesIO()
  with zipfile.ZipFile(bad,'w') as z:z.writestr('catalog.json',json.dumps(baseline));z.writestr('../escape.png',png)
  assert request('/api/restore',{'data':base64.b64encode(bad.getvalue()).decode()})[0]==400
  assert request('/api/auth/logout',{})[0]==200
  assert json.loads(request('/api/auth/session')[1])['authenticated'] is False
  assert request('/api/state?admin=1')[0]==401
  assert request('/api/state',state)[0]==401
  assert request('/')[0]==200
  print('PASS: password login/logout, private read/write protection, HttpOnly cookie,  isolated upload, static image, product create/delete, persistence, category rename, ZIP backup/restore, invalid upload, invalid state, origin guard, traversal guard.')
 finally:http.shutdown();http.server_close()
