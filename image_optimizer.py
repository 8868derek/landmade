"""Non-destructive WebP display copies. Originals and catalog paths are retained."""
from pathlib import Path
import json,hashlib,threading,tempfile,os,sys,io
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'image_tools'))
LOCK=threading.RLock()
POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='image-display')
CACHE={}
HARD_LIMIT=300000
PRESETS={'thumb':(320,40*1024,(84,80)), 'card':(1120,180*1024,(86,82,78)), 'display':(2240,280000,(88,84,80))}

def load_manifest(data):
 path=Path(data)/'optimized/manifest.json'
 try:stamp=path.stat().st_mtime_ns
 except FileNotFoundError:return {},''
 with LOCK:
  key=str(path)
  if CACHE.get(key,(None,))[0]!=stamp:
   try:CACHE[key]=(stamp,json.loads(path.read_text()).get('files',{}))
   except (OSError,ValueError):return {},''
  return CACHE[key][1],str(stamp)

def write_entries(data,entries):
 folder=Path(data)/'optimized';folder.mkdir(parents=True,exist_ok=True)
 with LOCK:
  current,_=load_manifest(data);files=dict(current);files.update(entries)
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=folder,prefix='.manifest-',delete=False) as f:
   json.dump({'version':1,'files':files},f,ensure_ascii=False);name=f.name
  try:os.replace(name,folder/'manifest.json')
  finally:
   if os.path.exists(name):os.unlink(name)

def optimize_image(source,data,persist=True):
 from PIL import Image,ImageOps,ImageCms
 source=Path(source);folder=Path(data)/'optimized';folder.mkdir(parents=True,exist_ok=True)
 raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest();key='/uploads/'+source.name
 old,_=load_manifest(data)
 if old.get(key,{}).get('sha256')==digest and all((folder/v['url'].split('/')[-1]).is_file() and (folder/v['url'].split('/')[-1]).stat().st_size<=HARD_LIMIT for v in old[key]['variants'].values()):return key,old[key]
 with Image.open(io.BytesIO(raw)) as original:
  if getattr(original,'n_frames',1)>1:return key,None
  image=ImageOps.exif_transpose(original);image.load();icc=image.info.get('icc_profile')
  alpha=image.mode in ('RGBA','LA') or 'transparency' in image.info
  image=image.convert('RGBA' if alpha else 'RGB')
  if icc:
   try:
    srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
    image=ImageCms.profileToProfile(image,io.BytesIO(icc),srgb,outputMode=image.mode)
    icc=srgb.tobytes()
   except (ValueError,TypeError,OSError,ImageCms.PyCMSError):pass
  if icc and len(icc)>65536:icc=None
  variants={}
  for kind,(edge,target,qualities) in PRESETS.items():
   resized=image.copy();resized.thumbnail((edge,edge),Image.Resampling.LANCZOS)
   for quality in qualities:
    buf=io.BytesIO();resized.save(buf,'WEBP',quality=quality,method=5,alpha_quality=100,icc_profile=icc or b'')
    encoded=buf.getvalue()
    if len(encoded)<=target:break
   # Keep a hard byte ceiling even for highly detailed/noisy source images.
   # Resize from the original on each attempt to avoid cumulative resampling.
   while len(encoded)>HARD_LIMIT:
    edge=max(1,int(max(resized.size)*.88));resized=image.copy();resized.thumbnail((edge,edge),Image.Resampling.LANCZOS)
    buf=io.BytesIO();resized.save(buf,'WEBP',quality=quality,method=5,alpha_quality=100,icc_profile=icc or b'');encoded=buf.getvalue()
    if max(resized.size)==1 and len(encoded)>HARD_LIMIT:raise ValueError('无法生成 300KB 以内的展示图')
   name=source.stem+'-'+digest[:12]+'-300k-'+kind+'.webp';destination=folder/name
   with tempfile.NamedTemporaryFile(dir=folder,prefix='.image-',delete=False) as f:f.write(encoded);temp=f.name
   try:os.replace(temp,destination)
   finally:
    if os.path.exists(temp):os.unlink(temp)
   variants[kind]={'url':'/optimized/'+name,'width':resized.width,'height':resized.height,'bytes':len(encoded),'quality':quality}
  entry={'sha256':digest,'sourceBytes':len(raw),'variants':variants}
 if persist:write_entries(data,{key:entry})
 return key,entry

def queue_images(paths,data):
 def run(source):
  try:optimize_image(source,data)
  except Exception as e:print('图片展示版生成失败（继续使用原图）：'+Path(source).name+' '+str(e),flush=True)
 for path in paths:
  if Path(path).suffix.lower() in ('.jpg','.jpeg','.png','.webp','.gif'):POOL.submit(run,path)

def client_variants(state,data):
 files,stamp=load_manifest(data);needed=set()
 def scan(value):
  if isinstance(value,str) and value.startswith('/uploads/'):needed.add(value)
  elif isinstance(value,list):
   for v in value:scan(v)
  elif isinstance(value,dict):
   for v in value.values():scan(v)
 scan(state)
 return {key:files[key]['variants'] for key in needed if key in files},stamp

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=ROOT/'data');p.add_argument('--sample',nargs='*');args=p.parse_args()
 files=[args.data/'uploads'/name for name in args.sample] if args.sample else sorted(f for f in (args.data/'uploads').iterdir() if f.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.gif'))
 entries={};failures=[]
 def job(path):
  try:return optimize_image(path,args.data,persist=False)
  except Exception as e:return '/uploads/'+path.name,{'error':str(e)}
 with ThreadPoolExecutor(max_workers=2) as workers:
  for i,(key,entry) in enumerate(workers.map(job,files),1):
   if entry and 'error' not in entry:entries[key]=entry
   elif entry:failures.append((key,entry['error']))
   if i%25==0:print('Processed '+str(i)+' / '+str(len(files)),flush=True)
 write_entries(args.data,entries)
 before=sum(v['sourceBytes'] for v in entries.values());after=sum(v['variants']['display']['bytes'] for v in entries.values())
 report={'images':len(entries),'sourceBytes':before,'displayBytes':after,'reductionPercent':round((1-after/before)*100,1) if before else 0,'failures':failures}
 (args.data/'optimized/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
