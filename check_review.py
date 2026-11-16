"""Network, large backup and caching regressions; all writes use temporary data."""
import server,tempfile,pathlib,sqlite3,json,secrets,threading,ipaddress,zipfile,hashlib
from urllib.request import Request,build_opener,HTTPCookieProcessor,ProxyHandler
from urllib.error import HTTPError
from http.cookiejar import CookieJar
class TestHandler(server.Handler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.client_address=(self.headers.get('X-Test-Peer','127.0.0.1'),0);super().do_GET()
 def do_POST(self):
  self.client_address=(self.headers.get('X-Test-Peer','127.0.0.1'),0);super().do_POST()
original_auth=server.AUTH_FILE;auth_bytes=original_auth.read_bytes()
with tempfile.TemporaryDirectory(prefix='landmade-review-') as temp:
 server.DATA=pathlib.Path(temp);server.UP=server.DATA/'uploads';server.UP.mkdir();server.DB=server.DATA/'catalog.sqlite3';server.AUTH_FILE=server.DATA/'auth.json'
 password=secrets.token_urlsafe(20);server.write_auth(server.secret_record(password))
 catalog={'categories':[{'id':'gifts','en':'GIFTS','zh':'商务礼赠'}],'products':[{'id':'test','en':'Test','zh':'测试','category':'gifts','images':['/assets/logo.png'],'published':True,'created':1}],'settings':{'slides':[],'newArrivals':['test'],'homeCollectionOrder':['test']}}
 with sqlite3.connect(server.DB) as db:db.execute('CREATE TABLE catalog(id INTEGER PRIMARY KEY,body TEXT NOT NULL)');db.execute('INSERT INTO catalog VALUES(1,?)',(json.dumps(catalog),))
 http=server.ThreadingHTTPServer(('127.0.0.1',0),TestHandler);http.lan_enabled=True;server.update_network_access(http,[('10.32.130.40',ipaddress.ip_network('10.32.130.0/24'))]);threading.Thread(target=http.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(http.server_port)
 admin=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()));public=build_opener(ProxyHandler({}))
 def request(path,data=None,headers=None,client=admin,method=None):
  hdr={'X-Landmade':'local','Content-Type':'application/json'};hdr.update(headers or {})
  if isinstance(data,(dict,list)):data=json.dumps(data).encode()
  req=Request(base+path,data=data,headers=hdr,method=method)
  try:
   with client.open(req,timeout=30) as r:return r.status,r.read(),r.headers
  except HTTPError as e:return e.code,e.read(),e.headers
 def body(result):return json.loads(result[1])
 try:
  shared_host='10.32.130.40:'+str(http.server_port)
  for peer in ('10.32.130.22','10.32.131.25','172.20.5.8','192.168.51.22'):
   headers={'X-Test-Peer':peer,'Host':shared_host}
   assert request('/',headers=headers,client=public)[0]==200
   assert request('/api/state',headers=headers,client=public)[0]==200
   assert request('/api/state?admin=1',headers=headers,client=public)[0]==401
   assert request('/api/state',catalog,headers=headers,client=public)[0]==401
  assert request('/',headers={'X-Test-Peer':'8.8.8.8','Host':shared_host},client=public)[0]==403
  assert request('/',headers={'X-Test-Peer':'10.32.131.25','Host':'untrusted.example:'+str(http.server_port)},client=public)[0]==403
  http.lan_enabled=False
  assert request('/',headers={'X-Test-Peer':'10.32.131.25','Host':shared_host},client=public)[0]==403
  assert not body(request('/api/network',client=public))['lan']
  http.lan_enabled=True
  assert body(request('/api/network',client=public))=={'lan':True,'urls':['http://'+shared_host]}
  assert request('/api/auth/login',{'password':password})[0]==200
  assert request('/api/network/clients',{'clients':[]})[0]==404
  server.update_network_access(http,[('10.32.132.40',ipaddress.ip_network('10.32.132.0/24'))]);assert '10.32.132.40' in http.allowed_hosts and '10.32.130.40' not in http.allowed_hosts;assert http.lan_urls==['http://10.32.132.40:'+str(http.server_port)]
  logo=request('/assets/logo.png',client=public);etag=logo[2]['ETag'];assert request('/assets/logo.png',headers={'If-None-Match':etag},client=public)[0]==304
  head=request('/assets/logo.png',method='HEAD',client=public);assert head[0]==200 and not head[1] and int(head[2]['Content-Length'])==len(logo[1])
  assert body(request('/api/revision'))['revision']==server.read_state()['_revision']
  bad=json.loads(json.dumps(catalog));bad['settings']['homeCollectionOrder']=['test','test'];assert request('/api/state',bad)[0]==400
  # A ZIP larger than the old 60MB limit is uploaded as a stream and restored on disk.
  backup=server.DATA/'large.zip';payload=b'\x89PNG\r\n\x1a\n'+b'0'*(16*1024*1024)
  with zipfile.ZipFile(backup,'w',zipfile.ZIP_STORED) as z:
   z.writestr('catalog.json',json.dumps(catalog))
   for i in range(4):z.writestr('uploads/test-'+str(i)+'.png',payload)
  assert backup.stat().st_size>60*1024*1024
  with backup.open('rb') as stream:restored=request('/api/restore/file',stream,headers={'Content-Type':'application/zip','Content-Length':str(backup.stat().st_size)})
  assert restored[0]==200,restored[:2]
  assert (server.UP/'test-3.png').stat().st_size==len(payload)
  assert server.read_state()['settings']['homeCollectionOrder']==['test']
  assert list(server.DATA.glob('before-restore-*.json'))
  assert request('/api/restore/file',b'bad',headers={'Content-Type':'application/zip'})[0]==400
  assert request('/api/restore/file',b'bad',client=public)[0]==401
  assert request('/api/restore/file',b'x',headers={'Content-Length':str(server.RESTORE_MAX+1)})[0]==400
  print('PASS: direct LAN access across subnets, local-only mode, authentication and Host guards, DHCP refresh, ETag/HEAD, revision polling, order validation, streamed >60MB restore, pre-restore recovery snapshot; real data untouched.')
 finally:http.shutdown();http.server_close();assert original_auth.read_bytes()==auth_bytes
