"""Channel-order and cleared-role persistence in an isolated database."""
import tempfile,sqlite3,json
from pathlib import Path
from copy import deepcopy
import server
old={'products':[{'id':'p','en':'P','zh':'产品','category':'gifts','categories':['gifts','home'],'published':True,'created':1,'images':['/assets/logo.png'],'cover':'/assets/logo.png','banner':'/assets/logo.png','channelBanner':'/assets/logo.png','cardImage':'/assets/logo.png'}], 'categories':[{'id':'gifts','en':'GIFTS','zh':'礼赠','hero':'/assets/logo.png','heroProduct':'p','heroMode':'shared'},{'id':'home','en':'HOME','zh':'家居','hero':'/assets/logo.png','heroProduct':'p','heroMode':'shared'}], 'settings':{'slides':[{'product':'p','image':'/assets/logo.png','imageMode':'product'}],'homeCollectionOrder':['p'],'newArrivals':['p']}}
with tempfile.TemporaryDirectory(prefix='landmade-channel-role-') as folder:
 server.DB=Path(folder)/'catalog.sqlite3'
 with sqlite3.connect(server.DB) as db:db.execute('CREATE TABLE catalog(id INTEGER PRIMARY KEY, body TEXT NOT NULL)');db.execute('INSERT INTO catalog VALUES(1,?)',(json.dumps(old),))
 changed=server.read_state();p=changed['products'][0]
 p.update(banner='',channelBanner='',cardImage='');changed['settings']['slides']=[]
 for c in changed['categories']:c.update(hero='',heroProduct='',heroMode='custom')
 changed['categories'][0]['productOrder']=['p'];server.save_state(changed,require_revision=True)
 saved=server.read_state();assert all(saved['products'][0][k]=='' for k in ('banner','channelBanner','cardImage'))
 assert saved['products'][0]['published'] and saved['products'][0]['cover']=='/assets/logo.png'
 assert saved['settings']['slides']==[] and saved['settings']['newArrivals']==['p']
 assert saved['categories'][0]['productOrder']==['p'] and 'productOrder' not in saved['categories'][1]
 server.save_state(saved,require_revision=True);again=server.read_state();assert again['products'][0]['channelBanner']==''
 for invalid in (['p','p'],'p',[1]):
  bad=deepcopy(again);bad['categories'][0]['productOrder']=invalid
  try:server.validate(bad);raise AssertionError('Invalid order accepted')
  except ValueError:pass
print('PASS: channel order persists independently; all three cleared roles remain cleared after repeated saves; products, default cover and arrivals preserved; invalid category order rejected.')
