"""Independent placement regression checks; never touches the real database."""
from copy import deepcopy
from server import sync_product_images
old={
 'products':[{'id':'p','category':'gifts','categories':['gifts','home'],
              'cover':'/assets/cover.png','cardImage':'/assets/list.png',
              'hero':'/assets/hero.png','banner':'/assets/home.png','channelBanner':'/assets/channel.png'}],
 'settings':{'slides':[{'product':'p','image':'/assets/home.png','imageMode':'product'}]},
 'categories':[{'id':'gifts','heroProduct':'p','hero':'/assets/channel.png','heroMode':'shared'},
               {'id':'home','heroProduct':'p','hero':'/assets/custom.png','heroMode':'custom'}]
}
def apply(key,value):
 changed=deepcopy(old);changed['products'][0][key]=value
 return sync_product_images(changed,old)

home=apply('banner','/assets/new-home.png')
assert home['settings']['slides'][0]['image']=='/assets/new-home.png'
assert home['categories'][0]['hero']=='/assets/channel.png'
assert home['products'][0]['cardImage']=='/assets/list.png'
assert home['products'][0]['hero']=='/assets/hero.png'

channel=apply('channelBanner','/assets/new-channel.png')
assert channel['categories'][0]['hero']=='/assets/new-channel.png'
assert channel['settings']['slides'][0]['image']=='/assets/home.png'
assert channel['products'][0]['cardImage']=='/assets/list.png'
assert channel['products'][0]['hero']=='/assets/hero.png'

listing=apply('cardImage','/assets/new-list.png')
assert listing['products'][0]['cardImage']=='/assets/new-list.png'
assert listing['settings']['slides'][0]['image']=='/assets/home.png'
assert listing['categories'][0]['hero']=='/assets/channel.png'
assert listing['products'][0]['hero']=='/assets/hero.png'

for result in (home,channel,listing):assert result['categories'][1]['hero']=='/assets/custom.png'

legacy=deepcopy(old);legacy['products'][0].pop('channelBanner');legacy['categories'][0].update(hero='/assets/home.png',heroMode='custom')
changed=deepcopy(legacy);changed['products'][0]['banner']='/assets/new-home.png'
out=sync_product_images(changed,legacy)
assert out['products'][0]['channelBanner']=='/assets/home.png'
assert out['categories'][0]['hero']=='/assets/home.png'
assert out['settings']['slides'][0]['image']=='/assets/new-home.png'

changed=deepcopy(old);changed['products'][0]['categories']=['home']
out=sync_product_images(changed,old)
assert out['categories'][0]['heroProduct']==''
assert out['categories'][1]['hero']=='/assets/custom.png'
print('PASS: homepage, channel and waterfall images are independent; detail and manual images preserved; legacy images migrate safely.')
