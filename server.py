#!/usr/bin/env python3
"""LANDMADE catalog. Local by default, optionally shared on the local network."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sqlite3, json, base64, uuid, mimetypes, zipfile, io, argparse, webbrowser, threading, time
from urllib.parse import urlparse, unquote, parse_qs
from urllib.request import urlopen
from http.cookies import SimpleCookie
import secrets, hashlib, hmac, re, ipaddress, subprocess, os, tempfile, shutil
from image_optimizer import client_variants,load_manifest,queue_images
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; UP=DATA/'uploads'; DB=DATA/'catalog.sqlite3'
MAX=90*1024*1024
RESTORE_MAX=1024*1024*1024
RESTORE_EXPANDED_MAX=2*1024*1024*1024
PRIVATE_NETWORKS=tuple(ipaddress.ip_network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
AUTH_FILE=DATA/'auth.json'
SESSIONS={}
SESSION_SECONDS=8*60*60
AUTH_LOCK=threading.Lock()
PASSWORD_GRANTS={}
PASSWORD_GRANT_SECONDS=5*60

def secret_record(value):
 salt=secrets.token_hex(32)
 return {'salt':salt,'digest':hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(salt),200000).hex()}

def secret_matches(value,record):
 if not isinstance(value,str) or len(value)>256 or not record:return False
 digest=hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(record['salt']),200000).hex()
 return hmac.compare_digest(digest,record['digest'])

def write_auth(config):
 temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=AUTH_FILE.parent,prefix='.auth-',delete=False) as f:
   temporary=Path(f.name);os.chmod(temporary,0o600);json.dump(config,f);f.flush();os.fsync(f.fileno())
  os.replace(temporary,AUTH_FILE)
 finally:
  if temporary and temporary.exists():temporary.unlink()

def local_networks():
 """Discover active physical IPv4 interfaces without contacting another host."""
 result=[]
 output=subprocess.check_output(['/sbin/ifconfig'],text=True)
 for block in re.split(r'\n(?=\S)',output):
  if not re.match(r'en\d+:',block) or 'status: active' not in block:continue
  for address,mask in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)',block):
   ip=ipaddress.ip_address(address)
   if not any(ip in network for network in PRIVATE_NETWORKS):continue
   netmask=str(ipaddress.IPv4Address(int(mask,16)))
   result.append((address,ipaddress.ip_network(address+'/'+netmask,strict=False)))
 return result

def allowed_peer(address,lan_enabled=False):
 try:
  ip=ipaddress.ip_address(address)
 except ValueError:return False
 return ip.is_loopback or (lan_enabled and any(ip in network for network in PRIVATE_NETWORKS))

def update_network_access(http,networks):
 http.allowed_hosts={'127.0.0.1','localhost'}|{address for address,_ in networks}
 http.lan_urls=['http://'+address+':'+str(http.server_port) for address,_ in networks]

def write_share_addresses(urls):
 (ROOT/'同事访问地址.txt').write_text('同事浏览（请完整复制 http:// 开头的网址）：\n'+'\n'.join(urls)+'\n\n后台编辑（需管理密码）：\n'+'\n'.join(url+'/#/admin/home' for url in urls)+'\n\n仅本机使用的 127.0.0.1 / localhost 不能发给同事。保持主机开机、联网和网站启动窗口运行。同事的设备能通过内网连到这台电脑，就可以直接浏览。\n',encoding='utf-8')

def refresh_network_loop(http,stop):
 previous=list(getattr(http,'lan_urls',[]))
 while not stop.wait(10):
  try:
   networks=local_networks();update_network_access(http,networks)
   if http.lan_urls!=previous:write_share_addresses(http.lan_urls);previous=list(http.lan_urls);print('局域网地址已更新：'+', '.join(previous),flush=True)
  except (OSError,ValueError) as e:print('网络地址检查失败：'+str(e),flush=True)

def network_info(http):
 return {'lan':getattr(http,'lan_enabled',False),'urls':list(getattr(http,'lan_urls',[]))}

def password_ok(password):
 return secret_matches(password,json.loads(AUTH_FILE.read_text()))
def public_state():
 s=read_state();s['categories']=[c for c in s['categories'] if not c.get('hidden',False)]
 categories={c['id'] for c in s['categories']}
 products=[]
 for p in s['products']:
  available=[c for c in p.get('categories',[p['category']]) if c in categories]
  if p.get('published') and available:
   p['categories']=available
   if p['category'] not in available:p['category']=available[0]
   products.append(p)
 s['products']=products
 visible={p['id'] for p in s['products']}
 s['settings']['slides']=[slide for slide in s['settings'].get('slides',[]) if slide.get('product') in visible]
 return s


def client_state(admin=False):
 state=read_state() if admin else public_state()
 state['mediaVariants'],state['_mediaRevision']=client_variants(state,DATA)
 return state

def read_state():
 with sqlite3.connect(DB) as db:
  body=db.execute('SELECT body FROM catalog WHERE id=1').fetchone()[0]
  state=json.loads(body);state['_revision']=hashlib.sha256(body.encode()).hexdigest();return state
def validate(s):
 if not isinstance(s,dict) or not isinstance(s.get('products'),list) or not isinstance(s.get('categories'),list) or not isinstance(s.get('settings'),dict):raise ValueError('数据结构不完整')
 ids=[c.get('id') for c in s['categories']]
 if len(ids)!=len(set(ids)) or not ids:raise ValueError('分类编号重复或为空')
 pids=[p.get('id') for p in s['products']]
 if len(pids)!=len(set(pids)) or not all(isinstance(i,str) and i for i in ids+pids):raise ValueError('产品编号不正确')
 for key,limit in [('newArrivals',3),('homeCollectionOrder',10000)]:
  if key in s['settings']:
   values=s['settings'][key]
   if not isinstance(values,list) or len(values)>limit or any(not isinstance(v,str) or not v for v in values) or len(values)!=len(set(values)):raise ValueError('推荐或排序设置不正确')
 def image(path):
  if not isinstance(path,str) or not path.startswith(('/assets/','/uploads/')) or '..' in path or '?' in path:raise ValueError('图片路径不正确')
 for p in s['products']:
  if p.get('category') not in ids or not p.get('en','').strip() or not isinstance(p.get('images'),list):raise ValueError('请填写产品英文名称、分类和组图')
  if 'categories' in p and (not isinstance(p['categories'],list) or not p['categories'] or any(c not in ids for c in p['categories']) or p['category'] not in p['categories']):raise ValueError('产品分类不正确')
  for f in p['images']:image(f)
  statuses=p.get('imageStatuses',{})
  if not isinstance(statuses,dict) or any(k not in p['images'] or v not in ('design','making','listed') for k,v in statuses.items()):raise ValueError('图片状态不正确，请选择完成设计、制作中或已上架')
  names=p.get('mediaNames',{})
  if not isinstance(names,dict) or any(k not in p['images'] or not isinstance(v,str) or len(v)>120 for k,v in names.items()):raise ValueError('图片名称不正确')
  for k in ('cover','hero','banner','channelBanner','cardImage'):
   if p.get(k):image(p[k])
  if p.get('cover') and p['cover'] not in p['images']:raise ValueError('封面必须属于产品组图')
  if p.get('hero') and p['hero'] not in p['images']:raise ValueError('顶部大图必须属于产品组图')
  if p.get('cardImage') and p['cardImage'] not in p['images']:raise ValueError('推荐展示图必须属于产品组图')
 for c in s['categories']:
  if not c.get('zh','').strip() or not c.get('en','').strip():raise ValueError('请填写导航中英文文案')
  if 'hidden' in c and not isinstance(c['hidden'],bool):raise ValueError('频道显示状态不正确')
  if 'productOrder' in c:
   order=c['productOrder']
   if not isinstance(order,list) or len(order)>10000 or any(not isinstance(v,str) or not v for v in order) or len(order)!=len(set(order)):raise ValueError('频道产品排序设置不正确')
  if c.get('hero'):image(c['hero'])
 for slide in s['settings'].get('slides',[]):
  image(slide.get('image',''))
  if slide.get('product') not in pids:raise ValueError('轮播跳转产品不存在')
 return s
def sync_product_images(s,previous):
 """Resolve product-backed images once, for all three administration screens."""
 products={p['id']:p for p in s['products']}
 old_products={p['id']:p for p in previous.get('products',[])}
 def source(p,channel=False):
  return (p.get('channelBanner') if channel else '') or p.get('banner') or p.get('hero') or p.get('cover') or ''
 for p in products.values():
  old=old_products.get(p['id'],{})
  # Freeze legacy shared channel images before a homepage-only edit.
  if 'channelBanner' not in p and old:p['channelBanner']=source(old,True)
  if p.get('bannerSource') in ('hero','cover'):p['banner']=p.get(p['bannerSource'],'') or source(p)
 old_slides=previous.get('settings',{}).get('slides',[])
 for slide in s['settings'].get('slides',[]):
  p=products.get(slide.get('product'))
  if not p or slide.get('imageMode')=='custom':continue
  old=old_products.get(p['id'],{})
  old_slide=next((a for a in old_slides if a.get('product')==p['id'] and a.get('image')==slide.get('image')),None)
  linked=slide.get('imageMode')=='product' or (p.get('banner') and slide.get('image')==p['banner']) or (old_slide and slide.get('image')==source(old))
  if linked and source(p):slide['image']=source(p);slide['imageMode']='product'
 old_channels={c['id']:c for c in previous.get('categories',[])}
 for c in s['categories']:
  p=products.get(c.get('heroProduct'))
  if not p:continue
  old_c=old_channels.get(c['id'],{});old_p=old_products.get(p['id'],{})
  linked=c.get('heroMode') in ('shared','product') or (old_c.get('heroProduct')==p['id'] and c.get('hero')==old_c.get('hero')==source(old_p,True))
  if linked:
   if c['id'] not in p.get('categories',[p.get('category')]):c.update(hero='',heroProduct='',heroMode='custom')
   elif source(p,True):c.update(hero=source(p,True),heroMode='shared')
 return s

def save_state(s,require_revision=False):
 validate(s)
 clean=dict(s);expected=clean.pop('_revision',None);clean.pop('mediaVariants',None);clean.pop('_mediaRevision',None)
 with sqlite3.connect(DB) as db:
  db.execute('BEGIN IMMEDIATE')
  current=db.execute('SELECT body FROM catalog WHERE id=1').fetchone()[0]
  if require_revision and expected!=hashlib.sha256(current.encode()).hexdigest():raise StaleCatalogError('产品资料已在其他页面更新。请先刷新本页，再重新编辑保存，避免覆盖新上传的产品。')
  if require_revision:sync_product_images(clean,json.loads(current));validate(clean)
  body=json.dumps(clean,ensure_ascii=False);db.execute('UPDATE catalog SET body=? WHERE id=1',(body,))
 return hashlib.sha256(body.encode()).hexdigest()
class StaleCatalogError(Exception):pass
def image_ext(raw):
 if raw.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
 if raw.startswith(b'\xff\xd8\xff'):return 'jpg'
 if raw[:6] in (b'GIF87a',b'GIF89a'):return 'gif'
 if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':return 'webp'
 if len(raw)>=24 and raw[4:8]==b'ftyp':
  size=int.from_bytes(raw[:4],'big')
  brands=[raw[8:12]]+[raw[i:i+4] for i in range(16,min(size,len(raw)),4)]
  if 16<=size<=len(raw) and any(b in (b'isom',b'iso2',b'mp41',b'mp42',b'avc1',b'M4V ') for b in brands):return 'mp4'
 raise ValueError('仅支持 PNG、JPG、WebP、GIF 图片和 MP4 视频')
def restore_backup(source):
 with zipfile.ZipFile(source) as z,tempfile.TemporaryDirectory(prefix='landmade-restore-') as temp:
  items=z.infolist();names=[i.filename for i in items]
  if len(names)!=len(set(names)) or len(items)>10000:raise ValueError('备份含重复或过多文件')
  if sum(i.file_size for i in items)>RESTORE_EXPANDED_MAX:raise ValueError('备份解压后最大 2GB')
  if z.getinfo('catalog.json').file_size>MAX:raise ValueError('产品资料过大')
  state=validate(json.loads(z.read('catalog.json')));pending=[]
  for item in items:
   if item.filename=='catalog.json':continue
   p=Path(item.filename)
   if len(p.parts)!=2 or p.parts[0]!='uploads' or p.name in ('.','..') or '\\' in item.filename:raise ValueError('备份含不允许的文件路径')
   staged=Path(temp)/p.name
   with z.open(item) as src,staged.open('wb') as dest:shutil.copyfileobj(src,dest,65536)
   with staged.open('rb') as f:image_ext(f.read(4096))
   dest=UP/p.name
   if dest.exists():
    def digest(path):
     h=hashlib.sha256()
     with path.open('rb') as f:
      for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
     return h.digest()
    if digest(dest)!=digest(staged):raise ValueError('备份图片存在同名冲突，请使用原始备份')
   pending.append((dest,staged))
  available={'/uploads/'+d.name for d,_ in pending}|{'/uploads/'+p.name for p in UP.iterdir() if p.is_file()}
  paths=[]
  for p in state['products']:paths+=p['images']+[p.get(k,'') for k in ('cover','hero','banner','channelBanner','cardImage')]
  paths += [c.get('hero','') for c in state['categories']]+[s['image'] for s in state['settings'].get('slides',[])]
  if any(p.startswith('/uploads/') and p not in available for p in paths):raise ValueError('备份缺少图片文件')
  snapshot=DATA/('before-restore-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json');snapshot.write_text(json.dumps(read_state(),ensure_ascii=False))
  for dest,staged in pending:
   if not dest.exists():shutil.copyfile(staged,dest)
  save_state(state)

class Handler(BaseHTTPRequestHandler):
 def valid_host(self):
  hosts=getattr(self.server,'allowed_hosts',{'127.0.0.1','localhost'})
  try:
   url=urlparse('http://'+self.headers.get('Host',''))
   return url.hostname in hosts and url.port==self.server.server_port and not url.username and not url.password and not url.path and not url.query and not url.fragment
  except ValueError:return False
 def valid_client(self):
  return allowed_peer(self.client_address[0],getattr(self.server,'lan_enabled',False))
 def deny_access(self):
  if not self.valid_client():
   message='此网站仅供本机和已开启共享的内网访问。'
  else:
   message='访问地址不正确或已过期，请向管理员获取最新地址。'
  return self.respond(403,{'error':message})
 def do_HEAD(self):self.do_GET()
 def session_token(self):
  try:
   cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));return cookie['landmade_session'].value if 'landmade_session' in cookie else ''
  except Exception:return ''
 def logged_in(self):
  token=self.session_token()
  with AUTH_LOCK:
   now=time.monotonic()
   for key in list(SESSIONS):
    if SESSIONS[key]<=now:SESSIONS.pop(key,None);PASSWORD_GRANTS.pop(key,None)
   return token in SESSIONS
 def password_access(self):
  with AUTH_LOCK:return self.session_token() in SESSIONS and PASSWORD_GRANTS.get(self.session_token(),0)>time.monotonic()

 def respond(self,code,body,kind='application/json; charset=utf-8',extra=None):
  if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode()
  if isinstance(body,str):body=body.encode()
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store' if 'json' in kind or 'html' in kind or 'zip' in kind else 'public, max-age=3600')
  for k,v in (extra or {}).items():self.send_header(k,v)
  self.end_headers()
  if self.command!='HEAD':
   try:self.wfile.write(body)
   except (BrokenPipeError,ConnectionResetError):pass
 def do_GET(self):
  if not self.valid_host() or not self.valid_client():return self.deny_access()
  path=unquote(urlparse(self.path).path)
  if path=='/api/network':return self.respond(200,network_info(self.server))
  if path=='/api/revision':
   admin=parse_qs(urlparse(self.path).query).get('admin')==['1']
   if admin and not self.logged_in():return self.respond(401,{'error':'请先登录管理后台'})
   with sqlite3.connect(DB) as db:body=db.execute('SELECT body FROM catalog WHERE id=1').fetchone()[0]
   return self.respond(200,{'revision':hashlib.sha256(body.encode()).hexdigest(),'mediaRevision':load_manifest(DATA)[1]})
  if path=='/api/auth/session':return self.respond(200,{'authenticated':self.logged_in()})
  if path=='/api/auth/password/access':
   if not self.logged_in():return self.respond(401,{'error':'请先登录管理后台'})
   return self.respond(200,{'allowed':self.password_access()})
  if path=='/api/state':
   admin=parse_qs(urlparse(self.path).query).get('admin')==['1']
   if admin and not self.logged_in():return self.respond(401,{'error':'请先登录管理后台'})
   return self.respond(200,client_state(admin))
  if path=='/api/backup':
   if not self.logged_in():return self.respond(401,{'error':'请先登录管理后台'})
   with tempfile.TemporaryDirectory(prefix='landmade-backup-') as folder:
    backup=Path(folder)/'backup.zip'
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as z:
     z.writestr('catalog.json',json.dumps(read_state(),ensure_ascii=False))
     for f in UP.iterdir():
      if f.is_file():z.write(f,'uploads/'+f.name)
    return self.stream_file(backup,'application/zip',download='landmade-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.zip')
  if path.startswith('/optimized/'):
   base=DATA/'optimized';rel=path[len('/optimized/'):]
   if not rel.endswith('.webp'):return self.respond(404,{'error':'文件不存在'})
  elif path.startswith('/uploads/'):base=UP;rel=path[len('/uploads/'):]
  else:base=ROOT/'static';rel='index.html' if path in ('/','/admin','/admin/') else path.lstrip('/')
  f=(base/rel).resolve()
  if not f.is_relative_to(base.resolve()) or not f.is_file():return self.respond(404,{'error':'文件不存在'})
  return self.stream_file(f,mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
 def stream_file(self,f,kind,download=None):
  stat=f.stat();size=stat.st_size;start=0;end=size-1;partial=False
  etag='"'+str(stat.st_mtime_ns)+'-'+str(size)+'"'
  extra={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store' if download or 'html' in kind else 'public, max-age=3600','ETag':etag}
  if download:extra['Content-Disposition']='attachment; filename="'+download+'"'
  elif self.headers.get('If-None-Match')==etag and 'html' not in kind:
   self.send_response(304)
   for k,v in extra.items():self.send_header(k,v)
   self.end_headers();return
  value=self.headers.get('Range') if kind=='video/mp4' and self.command!='HEAD' else None
  if value:
   m=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
   if not m or not any(m.groups()):return self.respond(416,b'',kind,{'Content-Range':f'bytes */{size}'})
   a,b=m.groups()
   if a:start=int(a);end=min(int(b),end) if b else end
   else:start=max(0,size-int(b))
   if start>=size or end<start:return self.respond(416,b'',kind,{'Content-Range':f'bytes */{size}'})
   partial=True
  self.send_response(206 if partial else 200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(max(0,end-start+1)))
  if kind=='video/mp4':self.send_header('Accept-Ranges','bytes')
  if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  for k,v in extra.items():self.send_header(k,v)
  self.end_headers()
  if self.command=='HEAD':return
  try:
   with f.open('rb') as stream:
    stream.seek(start);remaining=end-start+1
    while remaining:
     chunk=stream.read(min(65536,remaining))
     if not chunk:break
     self.wfile.write(chunk);remaining-=len(chunk)
  except (BrokenPipeError,ConnectionResetError):pass
 def do_POST(self):
  host=self.headers.get('Host','');origin=self.headers.get('Origin')
  if not self.valid_host() or not self.valid_client() or self.headers.get('X-Landmade')!='local' or (origin and origin!='http://'+host):return self.respond(403,{'error':'请求来源不正确'})
  path=urlparse(self.path).path
  if path not in ('/api/auth/login','/api/auth/logout') and not self.logged_in():return self.respond(401,{'error':'请先登录管理后台，或登录已过期；重新登录后再保存'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if path=='/api/restore/file':
    if size<=0 or size>RESTORE_MAX:raise ValueError('备份 ZIP 最大 1GB')
    with tempfile.TemporaryFile() as uploaded:
     remaining=size
     while remaining:
      chunk=self.rfile.read(min(65536,remaining))
      if not chunk:raise ValueError('备份上传中断，请重试')
      uploaded.write(chunk);remaining-=len(chunk)
     uploaded.seek(0);restore_backup(uploaded)
    if getattr(self.server,'optimize_uploads',False):queue_images(UP.iterdir(),DATA)
    return self.respond(200,{'ok':True})
   if size<=0 or size>MAX:raise ValueError('请求过大，单次上传请小于 60MB')
   body=json.loads(self.rfile.read(size))
   if path=='/api/auth/login':
    if not isinstance(body,dict) or not password_ok(body.get('password')):return self.respond(401,{'error':'密码不正确，请重试'})
    token=secrets.token_urlsafe(32)
    with AUTH_LOCK:SESSIONS[token]=time.monotonic()+SESSION_SECONDS
    return self.respond(200,{'ok':True},extra={'Set-Cookie':'landmade_session='+token+'; HttpOnly; SameSite=Strict; Path=/'})
   if path=='/api/auth/logout':
    with AUTH_LOCK:SESSIONS.pop(self.session_token(),None);PASSWORD_GRANTS.pop(self.session_token(),None)
    return self.respond(200,{'ok':True},extra={'Set-Cookie':'landmade_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
   if path=='/api/auth/password/verify':
    config=json.loads(AUTH_FILE.read_text());token=self.session_token()
    if not secret_matches(body.get('answer'),config.get('verification')):
     with AUTH_LOCK:PASSWORD_GRANTS.pop(token,None)
     return self.respond(403,{'error':'验证密码不正确，请根据提示重新输入'})
    with AUTH_LOCK:PASSWORD_GRANTS[token]=time.monotonic()+PASSWORD_GRANT_SECONDS
    return self.respond(200,{'ok':True})
   if path=='/api/auth/password/change':
    if not self.password_access():return self.respond(403,{'error':'请先完成“我是谁”验证，验证有效期为5分钟'})
    new_password=body.get('newPassword');confirmation=body.get('confirmPassword')
    if not isinstance(new_password,str) or not 6<=len(new_password)<=128:raise ValueError('新密码请使用6–128个字符')
    if new_password!=confirmation:raise ValueError('两次输入的新密码不一致')
    token=self.session_token()
    with AUTH_LOCK:
     if token not in SESSIONS or PASSWORD_GRANTS.get(token,0)<=time.monotonic():return self.respond(403,{'error':'验证已过期，请重新验证'})
     config=json.loads(AUTH_FILE.read_text());config.update(secret_record(new_password));write_auth(config)
     SESSIONS.clear();PASSWORD_GRANTS.clear()
    return self.respond(200,{'ok':True},extra={'Set-Cookie':'landmade_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
   if path=='/api/state':
    revision=save_state(body,require_revision=True)
    return self.respond(200,{'ok':True,'revision':revision,'state':client_state(True)})
   if path=='/api/upload':
    files=body.get('files',[])
    if not files or len(files)>100:raise ValueError('每次请选择 1–100 个图片或视频')
    pending=[]
    for f in files:
     raw=base64.b64decode(f['data'].split(',')[-1],validate=True)
     ext=image_ext(raw)
     if len(raw)>(60 if ext=='mp4' else 20)*1024*1024:raise ValueError('图片最大 20MB，MP4 视频最大 60MB')
     name=uuid.uuid4().hex+'.'+ext;pending.append((name,raw))
    for name,raw in pending:(UP/name).write_bytes(raw)
    if getattr(self.server,'optimize_uploads',False):queue_images([UP/name for name,_ in pending],DATA)
    return self.respond(200,{'images':['/uploads/'+n for n,_ in pending]})
   if path=='/api/restore':
    raw=base64.b64decode(body['data'].split(',')[-1],validate=True)
    restore_backup(io.BytesIO(raw))
    return self.respond(200,{'ok':True})
   self.respond(404,{'error':'接口不存在'})
  except StaleCatalogError as e:return self.respond(409,{'error':str(e)})
  except (ValueError,KeyError,TypeError,zipfile.BadZipFile) as e:self.respond(400,{'error':str(e)})
  except Exception as e:
   print('Request failed:',repr(e));self.respond(500,{'error':'保存失败，请检查本地磁盘或稍后重试'})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--open',action='store_true');p.add_argument('--lan',action='store_true',help='Share on active private local networks');args=p.parse_args()
 UP.mkdir(parents=True,exist_ok=True)
 if not DB.exists():raise SystemExit('缺少数据库，请先运行 prepare_assets.py')
 networks=local_networks() if args.lan else []
 if args.lan and not networks:raise SystemExit('未找到可用的局域网，请先连接公司 Wi-Fi 或有线网络后重试。')
 try:server=ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1',args.port),Handler)
 except PermissionError:raise SystemExit('系统未允许启动本地服务。请在终端直接运行启动网站.command。')
 except OSError:
  address='http://127.0.0.1:'+str(args.port)
  try:
   with urlopen(address+'/api/state',timeout=3) as response:existing=json.load(response)
   if not isinstance(existing,dict) or not all(k in existing for k in ('products','categories','settings')):raise ValueError('unexpected service')
   if args.lan:
    with urlopen(address+'/api/network',timeout=3) as response:sharing=json.load(response)
    if not sharing.get('lan'):raise SystemExit('当前网站仍是仅本机模式。请先关闭原服务窗口，再双击启动网站.command。')
  except Exception:raise SystemExit('端口被其他程序占用，暂时无法启动网站。')
  print('LANDMADE 已在运行，打开网站：'+address,flush=True)
  if args.open:webbrowser.open(address)
  raise SystemExit(0)
 server.lan_enabled=args.lan;server.optimize_uploads=True;update_network_access(server,networks)
 queue_images(UP.iterdir(),DATA)
 network_stop=threading.Event()
 if args.lan:threading.Thread(target=refresh_network_loop,args=(server,network_stop),daemon=True).start()
 print('LANDMADE 本地网站：http://127.0.0.1:'+str(args.port),flush=True)
 print('后台管理：http://127.0.0.1:'+str(args.port)+'/admin',flush=True)
 for address in server.lan_urls:print('同事访问：'+address+'　后台：'+address+'/#/admin/home',flush=True)
 if args.lan:
  write_share_addresses(server.lan_urls)
 if args.open:threading.Timer(.6,lambda:webbrowser.open('http://127.0.0.1:'+str(args.port))).start()
 try:server.serve_forever()
 except KeyboardInterrupt:print('\n网站已停止。')
 finally:network_stop.set();server.server_close()
