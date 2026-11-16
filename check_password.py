"""Password changes tested only with random credentials in a temporary auth file."""
import server,json,secrets,tempfile,threading,time
from pathlib import Path
from urllib.request import Request,build_opener,HTTPCookieProcessor,ProxyHandler
from urllib.error import HTTPError
from http.cookiejar import CookieJar
original_auth=server.AUTH_FILE
original_bytes=original_auth.read_bytes()
with tempfile.TemporaryDirectory(prefix='landmade-password-test-') as tmp:
 server.AUTH_FILE=Path(tmp)/'auth.json'
 old_password=secrets.token_urlsafe(20);new_password=secrets.token_urlsafe(24);answer=secrets.token_urlsafe(18)
 verification=server.secret_record(answer);server.write_auth(dict(server.secret_record(old_password),verification=verification))
 initial=json.loads(server.AUTH_FILE.read_text());server.SESSIONS.clear();server.PASSWORD_GRANTS.clear()
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
 base='http://127.0.0.1:'+str(http.server_port)
 jar1=CookieJar();jar2=CookieJar()
 client1=build_opener(ProxyHandler({}),HTTPCookieProcessor(jar1));client2=build_opener(ProxyHandler({}),HTTPCookieProcessor(jar2))
 def request(path,data=None,client=client1):
  req=Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Landmade':'local','Origin':base})
  try:
   with client.open(req) as r:return r.status,json.load(r)
  except HTTPError as e:return e.code,json.load(e)
 try:
  assert request('/api/auth/password/access')[0]==401
  assert request('/api/auth/password/verify',{'answer':answer})[0]==401
  change={'newPassword':new_password,'confirmPassword':new_password}
  assert request('/api/auth/password/change',change)[0]==401
  assert request('/api/auth/login',{'password':old_password})[0]==200
  assert request('/api/auth/password/access')[1]['allowed'] is False
  assert request('/api/auth/password/change',change)[0]==403
  assert request('/api/auth/password/verify',{'answer':'wrong'})[0]==403
  assert request('/api/auth/password/access')[1]['allowed'] is False
  assert request('/api/auth/password/verify',{'answer':answer})[0]==200
  assert request('/api/auth/password/access')[1]['allowed'] is True
  assert request('/api/auth/logout',{})[0]==200
  assert request('/api/auth/login',{'password':old_password})[0]==200
  assert request('/api/auth/password/access')[1]['allowed'] is False
  assert request('/api/auth/password/verify',{'answer':answer})[0]==200
  token=next(iter(jar1)).value;server.PASSWORD_GRANTS[token]=time.monotonic()-1
  assert request('/api/auth/password/change',change)[0]==403
  assert request('/api/auth/password/verify',{'answer':answer})[0]==200
  assert request('/api/auth/password/change',{'newPassword':new_password,'confirmPassword':'mismatch'})[0]==400
  assert request('/api/auth/password/change',{'newPassword':'short','confirmPassword':'short'})[0]==400
  assert server.password_ok(old_password)
  assert request('/api/auth/login',{'password':old_password},client2)[0]==200
  assert request('/api/auth/password/access',client=client2)[1]['allowed'] is False
  assert request('/api/auth/password/change',change,client2)[0]==403
  assert request('/api/auth/password/change',change)[0]==200
  assert server.password_ok(new_password) and not server.password_ok(old_password)
  assert request('/api/auth/session')[1]['authenticated'] is False
  assert request('/api/auth/session',client=client2)[1]['authenticated'] is False
  assert request('/api/auth/login',{'password':old_password})[0]==401
  assert request('/api/auth/login',{'password':new_password})[0]==200
  assert request('/api/auth/password/access')[1]['allowed'] is False
  saved=json.loads(server.AUTH_FILE.read_text());assert saved['verification']==verification and saved['salt']!=initial['salt']
  raw=server.AUTH_FILE.read_text();assert new_password not in raw and old_password not in raw and answer not in raw
  assert server.AUTH_FILE.stat().st_mode & 0o777==0o600
  print('PASS: login and challenge required; wrong/expired challenge blocked; session-bound gate; confirmation checked; atomic hashed password saved; all sessions revoked; verification preserved.')
 finally:
  http.shutdown();http.server_close();server.AUTH_FILE=original_auth
  assert original_auth.read_bytes()==original_bytes
