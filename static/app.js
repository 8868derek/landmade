'use strict';
let state, stateIsAdmin=false, routeVersion=0, heroTimer, heroCleanup, viewProduct, viewIndex=0, returnFocus, draft, dirty=false, uploading=false;
const app=document.querySelector('#app'), viewer=document.querySelector('#viewer');
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=x=>JSON.parse(JSON.stringify(x));
const internalUnlocked=()=>!stateIsAdmin&&state?._internal===true;
const publicProducts=()=>state.products.filter(p=>p.published).sort((a,b)=>b.created-a.created);
const productCategories=p=>p.categories?.length?p.categories:[p.category];
const inCategory=(p,id)=>productCategories(p).includes(id);
const catBy=id=>state.categories.find(c=>c.id===id);
const productBy=id=>state.products.find(p=>p.id===id);
const banner=p=>p?.banner!==undefined?p.banner:state.settings.slides.find(s=>s.product===p?.id)?.image||'';
function channelBanner(c,p,catalog=state){if(c.heroMode==='custom')return c.hero||'';const shared=p?.channelBanner||p?.banner||catalog.settings.slides.find(s=>s.product===p?.id)?.image||'';return c.heroMode==='shared'?(shared||c.hero||p?.hero||p?.cover):(c.hero||shared||p?.hero||p?.cover)}
function channelProduct(c,catalog=state){const products=catalog.products.filter(p=>p.published&&inCategory(p,c.id)).sort((a,b)=>b.created-a.created);return products.find(p=>p.id===c.heroProduct)||products[0]}
function arrivalProducts(catalog=state){const visible=new Set(catalog.categories.filter(c=>!c.hidden).map(c=>c.id));const available=catalog.products.filter(p=>p.published&&productCategories(p).some(id=>visible.has(id))).sort((a,b)=>b.created-a.created);return Array.isArray(catalog.settings.newArrivals)?catalog.settings.newArrivals.map(id=>available.find(p=>p.id===id)).filter(Boolean).slice(0,3):available.slice(0,3)}
function homeCollectionProducts(catalog=state,includeUnavailable=false){const ranked=new Map((Array.isArray(catalog.settings.homeCollectionOrder)?catalog.settings.homeCollectionOrder:[]).map((id,i)=>[id,i]));const all=[...catalog.products].sort((a,b)=>(ranked.get(a.id)??Infinity)-(ranked.get(b.id)??Infinity)||b.created-a.created);const visible=new Set(catalog.categories.filter(c=>!c.hidden).map(c=>c.id));return includeUnavailable?all:all.filter(p=>p.published&&productCategories(p).some(id=>visible.has(id)))}
function moveHomeCollection(ids,id,target){const from=ids.indexOf(id);if(from<0||!Number.isInteger(target)||target<0||target>=ids.length)return ids;const next=[...ids];next.splice(from,1);next.splice(target,0,id);return next}
function channelCollectionProducts(category,catalog=state,includeUnavailable=false){const ranked=new Map((category.productOrder||[]).map((id,i)=>[id,i]));return catalog.products.filter(p=>inCategory(p,category.id)&&(includeUnavailable||p.published&&!category.hidden)).sort((a,b)=>(ranked.get(a.id)??Infinity)-(ranked.get(b.id)??Infinity)||b.created-a.created)}
function selectProductRole(product,role,src){product[role]=src&&product[role]!==src?src:'';if(role==='banner')product.bannerSource='custom';return Boolean(product[role])}
function applyDraftRole(role,src){const selected=selectProductRole(draft,role,src),id=role==='banner'?'#use-home-banner':role==='channelBanner'?'#use-channel-banner':null;if(id){const checkbox=document.querySelector(id);checkbox.checked=selected;checkbox.dispatchEvent(new Event('input',{bubbles:true}));checkbox.dispatchEvent(new Event('change',{bubbles:true}))}dirty=true}
const image=p=>p.cardImage||p.cover||p.images[0]||'/assets/logo.png';
const isVideo=src=>/\.mp4$/i.test(src||'');
function displayImage(src){return state?.mediaVariants?.[src]?.display?.url||src}
function media(src,attrs='',mode='preview'){if(isVideo(src))return `<video src="${E(src)}#t=0.1" ${attrs} playsinline preload="metadata" ${mode==='play'?'controls':mode==='banner'?'muted loop autoplay':'muted'}></video>`;const variants=state?.mediaVariants?.[src];if(!variants)return `<img src="${E(src)}" ${attrs}>`;const thumb=mode==='thumb',large=mode==='banner'||mode==='carousel'||mode==='play',chosen=variants[thumb?'thumb':large?'display':'card'];const unique=new Map();if(!thumb)[variants.card,variants.display].forEach(v=>{if(v)unique.set(v.width,v.url)});const sizes=large?(mode==='play'?'80vw':'100vw'):'(max-width:600px) 50vw, (max-width:1800px) 33vw, 600px';return `<img src="${E(chosen?.url||src)}" ${unique.size?`srcset="${[...unique].sort((a,b)=>a[0]-b[0]).map(([w,url])=>E(url)+' '+w+'w').join(', ')}" sizes="${sizes}"`:''} data-original="${E(src)}" onerror="this.onerror=null;this.removeAttribute('srcset');this.src=this.dataset.original" ${attrs}>`}

const opt=(value,label,current)=>`<option value="${E(value)}" ${value===current?'selected':''}>${E(label)}</option>`;
const notice=(msg)=>{const t=document.querySelector('#toast');t.textContent=msg;t.classList.add('show');clearTimeout(notice.timer);notice.timer=setTimeout(()=>t.classList.remove('show'),3200)};
async function api(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Landmade':'local'},body:JSON.stringify(data)});let out;try{out=await r.json()}catch{throw Error('本地服务没有响应，请确认启动窗口仍在运行')}if(!r.ok)throw Object.assign(Error(out.error||'操作失败'),{status:r.status});return out}
async function save(next){const out=await api('/api/state',next);next._revision=out.revision;state=out.state||next;dirty=false;localStorage.setItem('landmade-catalog-update',Date.now()+'-'+Math.random())}
function nav(active='__home',overlay=false){return `<header class="site-header ${overlay?'overlay':''}"><a class="brand" href="#/" aria-label="LANDMADE 首页"><img src="/assets/logo.png" alt="蓝箭造办 LANDMADE"></a><nav class="nav" aria-label="产品分类"><a class="${active==='__home'?'active':''}" href="#/" aria-label="INDEX 首页"><span class="nav-en" aria-hidden="true">INDEX</span><span class="nav-zh" aria-hidden="true">首页</span></a>${state.categories.map(c=>`<a class="${c.id===active?'active':''}" href="#/category/${encodeURIComponent(c.id)}" aria-label="${E(c.en)} ${E(c.zh)}"><span class="nav-en" aria-hidden="true">${E(c.en)}</span><span class="nav-zh" aria-hidden="true">${E(c.zh)}</span></a>`).join('')}${internalNav(active)}</nav></header>`}
function internalNav(active){
 if(internalUnlocked()){
  const exit=stageIcon('<path d="M7 2H3v12h4m3-10 4 4-4 4m-4-4h8"/>');
  return `<button type="button" class="internal-entry is-unlocked" data-internal-exit>${exit}<span class="internal-entry-label">退出内部浏览</span></button>`;
 }
 const lock=stageIcon('<rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5 7V5a3 3 0 0 1 6 0v2m-3 3v1"/>');
 const current=active==='__internal';
 return `<a class="internal-entry${current?' is-current':''}" href="#/internal" ${current?'aria-current="page"':''}>${lock}<span class="internal-entry-label">内部浏览</span></a>`;
}
function footer(){return `<footer class="site-footer"><a href="#/" aria-label="首页"><img src="/assets/logo.png" alt="LANDMADE"></a><div class="right"><span>Objects for everyday living.</span><a class="admin-link" href="#/admin/products">后台管理 ↗</a></div></footer>`}
const imageStages={design:{label:'设计完成',icon:'<path d="M3 13l1-4 7-7 3 3-7 7-4 1zM9 4l3 3"/>'},making:{label:'制作中',icon:'<circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2"/>'},listed:{label:'已上架',icon:'<circle cx="8" cy="8" r="6"/><path d="M5 8l2 2 4-4"/>'}};
function imageStage(p,src){
 const stage=p.imageStatuses?.[src];
 return Object.prototype.hasOwnProperty.call(imageStages,stage)?stage:'design';
}
function stageIcon(path){
 return `<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}
function stageBadge(p,src){
 const key=imageStage(p,src),stage=imageStages[key];
 return `<span class="stage-badge stage-${E(key)}" aria-label="图片状态：${stage.label}">${stageIcon(stage.icon)}${stage.label}</span>`;
}
function card(p,masonry=false,position){return `<a class="card" ${position!==undefined?`data-channel-order="${position}"`:''} href="#/product/${encodeURIComponent(p.id)}"><div class="card-photo ${isVideo(image(p))?'has-video':''}">${media(image(p),`alt="${E(p.zh||p.en)}" loading="lazy" decoding="async" ${masonry?'':'width="600" height="600"'}`)}</div><div class="card-caption">${E(p.en)}<span class="go">→</span><div class="zh">${E(p.zh)}</div>${stageBadge(p,image(p))}</div></a>`}
function heading(en,zh,right=''){return `<div class="section-head"><div><h2${en==='NEW ARRIVALS'?' class="new-arrivals-title"':''}>${E(en)}</h2><div class="sub">${E(zh)}</div></div>${right}</div>`}
function empty(text='这个分类还没有上架产品'){return `<div class="empty">${E(text)}<small>可在后台添加产品，保存后会显示在这里。</small></div>`}
function slides(){return state.settings.slides.filter(s=>productBy(s.product)?.published)}
function slideCopy(slide, product, settings){
 return {
  title:slide.title?.trim()||product?.en||product?.zh||settings.headline,
  subtitle:slide.subtitle?.trim()||product?.zh||product?.en||settings.tagline
 };
}
function heroPanel(slide,index){
 const product=productBy(slide.product);
 const copy=slideCopy(slide,product,state.settings);
 return `<div class="hero-slide ${index===0?'is-active':''}" data-panel="${index}" aria-hidden="${index!==0}" ${index!==0?'inert':''}><a class="hero-backdrop" href="#/product/${E(slide.product)}" aria-label="查看轮播产品">${media(slide.image,`alt="${E(productBy(slide.product)?.zh)}" decoding="async"`,'carousel')}</a><div class="hero-inner"><div class="hero-copy"><h1>${E(copy.title)}</h1><div class="zh">${E(copy.subtitle)}</div><a class="explore" href="#/product/${E(slide.product)}">Explore design <small>探索产品</small> →</a></div></div></div>`}
function heroMarkup(){const list=slides();return list.map(heroPanel).join('')+`${list.length>1?'<button class="arrow prev" data-slide-prev aria-label="上一张">‹</button><button class="arrow next" data-slide-next aria-label="下一张">›</button>':''}<div class="hero-dots">${list.map((slide,i)=>`<button type="button" data-slide="${i}" class="${i===0?'active':''}" aria-label="第 ${i+1} 张：${E(productBy(slide.product)?.zh||slide.title||'轮播内容')}" aria-pressed="${i===0}"><span class="hero-thumb">${media(slide.image,'alt="" aria-hidden="true"','thumb')}</span></button>`).join('')}</div><div class="counter" aria-live="off">01 / ${String(list.length).padStart(2,'0')}</div>`}
function setPanelInteractive(panel,active){panel.inert=!active;panel.querySelectorAll('a,button,input,video').forEach(el=>{if(!active){if(!el.hasAttribute('data-panel-tabindex'))el.setAttribute('data-panel-tabindex',el.getAttribute('tabindex')??'none');el.setAttribute('tabindex','-1')}else if(el.hasAttribute('data-panel-tabindex')){const previous=el.getAttribute('data-panel-tabindex');if(previous==='none')el.removeAttribute('tabindex');else el.setAttribute('tabindex',previous);el.removeAttribute('data-panel-tabindex')}})}
function initHero(){
 const hero=document.querySelector('#home-hero');if(!hero)return;
 const panels=[...hero.querySelectorAll('[data-panel]')],dots=[...hero.querySelectorAll('[data-slide]')];if(!panels.length)return;
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');let index=0,busy=false,pending=null,disposed=false,removeTimer;
 const videos=panels.map(p=>p.querySelector('video'));
 panels.forEach((panel,i)=>{setPanelInteractive(panel,i===0);const v=videos[i];if(v){v.loop=false;v.removeAttribute('loop');v.removeAttribute('autoplay');v.muted=true;v.pause()}});
 const ready=panels.map(panel=>{const asset=panel.querySelector('img,video');if(asset.tagName==='VIDEO')return Promise.resolve(true);return new Promise(resolve=>{if(asset.complete)return resolve(asset.naturalWidth>0);const finish=ok=>{clearTimeout(timeout);asset.removeEventListener('load',loaded);asset.removeEventListener('error',failed);resolve(ok)},loaded=()=>finish(true),failed=()=>finish(false),timeout=setTimeout(()=>finish(false),8000);asset.addEventListener('load',loaded,{once:true});asset.addEventListener('error',failed,{once:true})})});
 function arm(ms){clearTimeout(heroTimer);if(disposed||document.hidden||panels.length<2)return;heroTimer=setTimeout(()=>change(index+1,false),ms)}
 function playCurrent(reset=false){if(disposed||document.hidden)return;const v=videos[index];if(!v){arm(7000);return}if(reset)try{v.currentTime=0}catch{}v.loop=panels.length===1;arm(10000);const playing=v.play();if(playing?.catch)playing.catch(()=>{if(!disposed&&v===videos[index])arm(7000)})}
 async function change(next,manual=true){
  next=(next+panels.length)%panels.length;if(disposed||next===index)return;if(busy){pending={next,manual};return}busy=true;clearTimeout(heroTimer);
  // Skip unavailable media instead of repeatedly attempting the same broken slide.
  let found=false;for(let n=0;n<panels.length-1;n++){if(await ready[next]){found=true;break}next=(next+1)%panels.length;if(next===index)break}
  if(disposed)return;if(!found||next===index){busy=false;arm(7000);if(manual)notice('轮播素材暂时无法读取，请在后台检查');return}
  const old=panels[index],incoming=panels[next];videos[index]?.pause();old.classList.add('is-leaving');old.classList.remove('is-active');old.setAttribute('aria-hidden','true');setPanelInteractive(old,false);
  setPanelInteractive(incoming,true);incoming.setAttribute('aria-hidden','false');incoming.classList.add('is-active');index=next;
  dots.forEach((dot,i)=>{dot.classList.toggle('active',i===index);dot.setAttribute('aria-pressed',String(i===index))});hero.querySelector('.counter').textContent=String(index+1).padStart(2,'0')+' / '+String(panels.length).padStart(2,'0');
  const finish=()=>{old.classList.remove('is-leaving');busy=false;playCurrent(true);if(pending){const request=pending;pending=null;change(request.next,request.manual)}};
  if(reduce.matches)finish();else removeTimer=setTimeout(finish,950);
 }
 const handlers=videos.map((v,i)=>{if(!v)return null;const ended=()=>{if(i===index&&!disposed&&!document.hidden)change(index+1,false)},progress=()=>{if(i===index&&!busy&&!v.paused&&!v.ended)arm(10000)},error=()=>{if(i===index&&!disposed)change(index+1,false)};v.addEventListener('ended',ended);v.addEventListener('timeupdate',progress);v.addEventListener('error',error);return {ended,progress,error}});
 dots.forEach(dot=>dot.onclick=()=>change(Number(dot.dataset.slide)));hero.querySelector('[data-slide-prev]')?.addEventListener('click',()=>change(index-1));hero.querySelector('[data-slide-next]')?.addEventListener('click',()=>change(index+1));
 const visibility=()=>{clearTimeout(heroTimer);if(document.hidden)videos[index]?.pause();else if(videos[index]?.ended)change(index+1,false);else playCurrent()};document.addEventListener('visibilitychange',visibility);playCurrent(true);
 heroCleanup=()=>{disposed=true;clearTimeout(heroTimer);clearTimeout(removeTimer);document.removeEventListener('visibilitychange',visibility);videos.forEach((v,i)=>{if(!v)return;v.pause();const h=handlers[i];v.removeEventListener('ended',h.ended);v.removeEventListener('timeupdate',h.progress);v.removeEventListener('error',h.error)})};
}

function stageFilters(){
 const all={label:'综合',icon:'<rect x="2" y="2" width="4.5" height="4.5" rx=".7"/><rect x="9.5" y="2" width="4.5" height="4.5" rx=".7"/><rect x="2" y="9.5" width="4.5" height="4.5" rx=".7"/><rect x="9.5" y="9.5" width="4.5" height="4.5" rx=".7"/>'};
 const stages=Object.entries(imageStages).filter(([key])=>key!=='design'||internalUnlocked());
 const filters=[['all',all],...stages];
 return `<div class="filters" role="group" aria-label="按作品状态筛选">${filters.map(([key,stage])=>{
  const active=key==='all';
  return `<button type="button" data-stage-filter="${key}" class="${active?'active':''}" aria-pressed="${active}">${stageIcon(stage.icon)}${stage.label}</button>`;
 }).join('')}</div>`;
}
function bindStageCollection(section,products,pageSize,renderCard,afterRender){
 const grid=section.querySelector('[data-stage-grid]');
 const load=section.querySelector('.load-wrap');
 const count=section.querySelector('[data-stage-count]');
 const buttons=[...section.querySelectorAll('[data-stage-filter]')];
 let selected='all',limit=pageSize;
 function renderGrid(){
  const matches=selected==='all'?products:products.filter(product=>imageStage(product,image(product))===selected);
  grid.innerHTML=matches.slice(0,limit).map(renderCard).join('')
   ||(selected==='all'?empty():'<div class="empty stage-empty">这个状态下暂无作品</div>');
  if(count)count.textContent=matches.length+' Products';
  afterRender?.();
  load.hidden=matches.length<=limit;
  load.querySelector('button').hidden=load.hidden;
 }
 buttons.forEach(button=>button.onclick=()=>{
  const next=selected===button.dataset.stageFilter?'all':button.dataset.stageFilter;
  if(next===selected)return;
  selected=next;
  limit=pageSize;
  buttons.forEach(option=>{
   const active=option.dataset.stageFilter===selected;
   option.classList.toggle('active',active);
   option.setAttribute('aria-pressed',String(active));
  });
  renderGrid();
 });
 load.querySelector('button').onclick=()=>{limit+=pageSize;renderGrid()};
 renderGrid();
}

function showHome(){const all=homeCollectionProducts(),arrivals=arrivalProducts(),sl=slides();app.innerHTML=nav('__home',true)+`<main>${sl.length?`<section class="hero has-backdrop" id="home-hero" aria-label="精选产品轮播">${heroMarkup(sl[0])}</section>`:`<section class="hero"><div class="hero-inner"><div class="hero-copy"><h1>${E(state.settings.headline)}</h1><div class="zh">${E(state.settings.tagline)}</div></div></div></section>`}${arrivals.length?`<section class="section">${heading('NEW ARRIVALS','新近上架','<a class="text-link" href="#collection">View all <span>→</span></a>')}<div class="product-grid latest">${arrivals.map(p=>card(p)).join('')}</div></section>`:''}<section class="section" id="collection">${heading('COLLECTION','全部作品',stageFilters())}<div class="product-grid" id="collection-grid" data-stage-grid></div><div class="load-wrap" id="load-wrap"><button type="button" class="outline-btn" id="load-more">Load more <small>加载更多</small></button></div></section></main>`+footer();
 bindStageCollection(document.querySelector('#collection'),all,12,product=>card(product));
 document.querySelector('a[href="#collection"]')?.addEventListener('click',e=>{e.preventDefault();document.querySelector('#collection').scrollIntoView({behavior:'smooth'})});
 if(sl.length)initHero();
}
function showCategory(id){const c=catBy(id);if(!c)return notFound();const list=channelCollectionProducts(c);const hp=list.find(p=>p.id===c.heroProduct)||list.find(p=>c.hero&&[p.channelBanner,p.banner,p.cover,...p.images].includes(c.hero))||channelProduct(c);const pic=channelBanner(c,hp);app.innerHTML=nav(id,Boolean(pic))+`<main>${pic?`<section class="hero channel has-backdrop" aria-label="${E(c.zh)}频道大图">${hp?`<a class="hero-backdrop" href="#/product/${encodeURIComponent(hp.id)}" aria-label="查看${E(hp.zh||hp.en)}详情">${media(pic,`alt="${E(hp.zh||hp.en)}"`,'banner')}</a>`:`<div class="hero-backdrop">${media(pic,`alt="${E(c.zh)}"`,'banner')}</div>`}</section>`:''}<section class="section channel-collection">${heading(c.en,c.zh,`<span class="muted" data-stage-count aria-live="polite"></span>`)}${stageFilters()}<div class="masonry" id="category-grid" data-stage-grid></div><div class="load-wrap" id="category-load"><button type="button" class="outline-btn" id="more-category">Load more <small>加载更多</small></button></div></section></main>`+footer();
 bindStageCollection(document.querySelector('.channel-collection'),list,15,(product,index)=>card(product,true,index),alignChannelProducts);
}
function alignChannelProducts(){const grid=document.querySelector('#category-grid');if(!grid)return;const count=detailPhotoBreakpoint.matches?2:3;if(grid.dataset.columns===String(count)&&grid.querySelector('.channel-product-column'))return;const cards=[...grid.querySelectorAll('[data-channel-order]')].sort((a,b)=>Number(a.dataset.channelOrder)-Number(b.dataset.channelOrder));if(!cards.length)return;const fragment=document.createDocumentFragment(),columns=Array.from({length:count},()=>{const col=document.createElement('div');col.className='channel-product-column';fragment.appendChild(col);return col});cards.forEach((card,i)=>columns[i%count].appendChild(card));grid.replaceChildren(fragment);grid.dataset.columns=String(count)}
const detailPhotoBreakpoint=matchMedia('(max-width:600px)');
function alignDetailPhotos(){const grid=document.querySelector('.detail-photos');if(!grid)return;const count=detailPhotoBreakpoint.matches?2:3;if(grid.dataset.columns===String(count))return;const photos=[...grid.querySelectorAll('[data-photo]')].sort((a,b)=>Number(a.dataset.photo)-Number(b.dataset.photo));const fragment=document.createDocumentFragment(),columns=Array.from({length:count},()=>{const col=document.createElement('div');col.className='detail-photo-column';fragment.appendChild(col);return col});photos.forEach((photo,i)=>columns[i%count].appendChild(photo));grid.replaceChildren(fragment);grid.dataset.columns=String(count)}
const alignProductLayouts=()=>{alignDetailPhotos();alignChannelProducts()};if(detailPhotoBreakpoint.addEventListener)detailPhotoBreakpoint.addEventListener('change',alignProductLayouts);else detailPhotoBreakpoint.addListener(alignProductLayouts);
function showProduct(id){const p=productBy(id);if(!p||!p.published)return notFound();const c=catBy(p.category);app.innerHTML=nav(p.category)+`<main><div class="detail-intro"><div class="breadcrumb"><a href="#/">Home</a> / <a href="#/category/${E(c.id)}">${E(c.en)}</a> / ${E(p.en)}</div><div class="intro-grid"><div><h1>${E(p.en)}</h1><div class="zh">${E(p.zh)}</div></div>${p.description||p.descriptionZh?`<div class="detail-description">${E(p.description).replace(/\n/g,'<br>')}<div class="zh">${E(p.descriptionZh)}</div></div>`:''}</div></div><div class="detail-gallery"><div class="detail-photos">${p.images.map((src,i)=>`<button class="photo-btn ${isVideo(src)?'has-video':''}" data-photo="${i}" aria-label="查看第 ${i+1} 个素材">${media(src,`alt="${E(p.mediaNames?.[src]||p.zh)} · ${i+1}" loading="lazy"`)}<span class="photo-stage">${stageBadge(p,src)}</span><span class="expand">⤢</span></button>`).join('')}</div><div class="back"><a class="text-link" href="#/category/${E(c.id)}">← Back to collection <small>返回频道</small></a></div></div></main>`+footer();alignDetailPhotos();document.querySelectorAll('[data-photo]').forEach(b=>b.onclick=()=>openViewer(p,Math.max(0,Number(b.dataset.photo))))}
function notFound(){app.innerHTML=nav()+`<main class="empty">产品暂未上架，或页面不存在。<small><a href="#/">← 返回首页</a></small></main>`+footer()}
function openViewer(p,i){returnFocus=document.activeElement;viewProduct=p;viewIndex=i;drawViewer();viewer.showModal();centerViewerThumb();document.body.style.overflow='hidden'}
function drawViewer(){
 releaseViewerZoom();
 const p=viewProduct,source=p.images[viewIndex],video=isVideo(source);
 viewer.querySelector('.viewer-stage video')?.pause();
 viewer.innerHTML=`
  <div class="viewer-header">
   <div class="viewer-top">${E(p.en)}<small>${E(p.zh)}</small><small>${String(viewIndex+1).padStart(2,'0')} / ${String(p.images.length).padStart(2,'0')}</small></div>
   <button type="button" class="viewer-close" aria-label="关闭大图">×</button>
  </div>
  <div class="viewer-main">
   <button type="button" class="viewer-prev" aria-label="上一张">‹</button>
   <div class="viewer-media">
    <div class="viewer-stage"><div class="viewer-canvas">${media(source,`class="viewer-image" alt="${E(p.zh)}" draggable="false"`,'play')}</div></div>
    <button type="button" class="viewer-zoom" aria-pressed="false"${video?' hidden':''}>
     <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path class="viewer-icon-enlarge" d="M6 2H2v4m8-4h4v4m0 4v4h-4m-4 0H2v-4"/>
      <path class="viewer-icon-fit" d="M2 6h4V2m8 4h-4V2m4 8h-4v4m-8-4h4v4"/>
     </svg>
     <span class="viewer-zoom-label">放大 200%</span>
    </button>
   </div>
   <button type="button" class="viewer-next" aria-label="下一张">›</button>
  </div>
  <div class="viewer-bottom">
   <div class="viewer-count">${String(viewIndex+1).padStart(2,'0')} — ${E(p.mediaNames?.[source]||p.zh||p.en)} ${stageBadge(p,source)}</div>
   <div class="viewer-thumbs">${p.images.map((s,i)=>`<button type="button" class="${i===viewIndex?'active':''}" data-thumb="${i}" aria-label="第 ${i+1} 张"${i===viewIndex?' aria-current="true"':''}>${media(s,'alt=""','thumb')}</button>`).join('')}</div>
   <div class="viewer-hint">${video?'← → 切换 · Esc 关闭':'点击图片可放大 · ← → 切换 · Esc 关闭'}</div>
  </div>`;
 viewer.querySelector('.viewer-close').onclick=()=>viewer.close();
 viewer.querySelector('.viewer-prev').onclick=()=>{moveViewer(-1);viewer.querySelector('.viewer-prev').focus()};
 viewer.querySelector('.viewer-next').onclick=()=>{moveViewer(1);viewer.querySelector('.viewer-next').focus()};
 viewer.querySelectorAll('[data-thumb]').forEach(button=>button.onclick=()=>{
  viewIndex=Number(button.dataset.thumb);
  drawViewer();
  viewer.querySelector('.viewer-thumbs .active').focus({preventScroll:true});
 });
 centerViewerThumb();
 if(!video)configureViewerZoom(source);
}
function centerViewerThumb(){
 const thumbs=viewer.querySelector('.viewer-thumbs'),active=thumbs.querySelector('.active');
 if(active)thumbs.scrollLeft=active.offsetLeft-(thumbs.clientWidth-active.offsetWidth)/2;
}
function configureViewerZoom(source){
 const stage=viewer.querySelector('.viewer-stage');
 const image=stage.querySelector('img');
 const zoom=viewer.querySelector('.viewer-zoom');
 const label=zoom.querySelector('.viewer-zoom-label');
 const hint=viewer.querySelector('.viewer-hint');
 const previewSrc=image.getAttribute('src'),previewSet=image.getAttribute('srcset');
 const zoomed=()=>stage.classList.contains('is-zoomed');
 let drag=null;
 function layout(center=false){
  const {clientWidth,clientHeight}=stage;
  if(!image.naturalWidth||!clientWidth||!clientHeight)return;
  const fit=Math.min(clientWidth/image.naturalWidth,clientHeight/image.naturalHeight);
  const scale=fit*(zoomed()?2:1);
  const width=Math.floor(image.naturalWidth*scale);
  const height=Math.floor(image.naturalHeight*scale);
  if(zoomed()){
   const anchorX=center===true ? 0.5 : (stage.scrollLeft+clientWidth/2)/stage.scrollWidth;
   const anchorY=center===true ? 0.5 : (stage.scrollTop+clientHeight/2)/stage.scrollHeight;
   image.style.width=width+'px';
   image.style.height=height+'px';
   stage.scrollLeft=stage.scrollWidth*anchorX-clientWidth/2;
   stage.scrollTop=stage.scrollHeight*anchorY-clientHeight/2;
  }
  // Follow the visible photo edge when the image leaves space inside the stage.
  zoom.style.insetInlineEnd=(Math.max(0,(clientWidth-width)/2)+10)+'px';
  zoom.style.insetBlockEnd=(Math.max(0,(clientHeight-height)/2)+10)+'px';
 }
 function toggle(){
  const enlarged=!zoomed();
  if(enlarged&&!image.naturalWidth)return;
  stage.classList.toggle('is-zoomed',enlarged);
  zoom.setAttribute('aria-pressed',String(enlarged));
  label.textContent=enlarged?'适应窗口':'放大 200%';
  hint.textContent=enlarged?'拖动查看细节 · 方向键移动 · Esc 关闭':'点击图片可放大 · ← → 切换 · Esc 关闭';
  if(enlarged){
   layout(true);
   image.removeAttribute('srcset');
   image.src=source;
  }else{
   image.removeAttribute('style');
   if(previewSet)image.setAttribute('srcset',previewSet);
   image.setAttribute('src',previewSrc);
   stage.scrollLeft=stage.scrollTop=0;
   layout();
  }
 }
 zoom.onclick=toggle;
 image.onclick=()=>{if(!zoomed())toggle()};
 image.addEventListener('load',()=>layout());
 if('ResizeObserver' in window){
  viewerZoomObserver=new ResizeObserver(()=>layout());
  viewerZoomObserver.observe(stage);
 }
 stage.addEventListener('pointerdown',event=>{
  if(!zoomed()||event.button!==0)return;
  drag={id:event.pointerId,x:event.clientX+stage.scrollLeft,y:event.clientY+stage.scrollTop};
  stage.setPointerCapture(event.pointerId);
  stage.classList.add('is-dragging');
 });
 stage.addEventListener('pointermove',event=>{
  if(drag?.id!==event.pointerId)return;
  stage.scrollLeft=drag.x-event.clientX;
  stage.scrollTop=drag.y-event.clientY;
 });
 stage.addEventListener('lostpointercapture',()=>{
  drag=null;
  stage.classList.remove('is-dragging');
 });
}
function moveViewer(n){
 viewIndex=(viewIndex+n+viewProduct.images.length)%viewProduct.images.length;
 drawViewer();
}
let viewerZoomObserver;
function releaseViewerZoom(){
 viewerZoomObserver?.disconnect();
 viewerZoomObserver=null;
}
viewer.addEventListener('close',()=>{
 releaseViewerZoom();
 viewer.querySelector('.viewer-stage video')?.pause();
 document.body.style.overflow='';
 returnFocus?.focus();
});
viewer.addEventListener('keydown',event=>{
 if(event.target.tagName==='VIDEO')return;
 const directions={ArrowRight:[1,0],ArrowLeft:[-1,0],ArrowDown:[0,1],ArrowUp:[0,-1]};
 const direction=directions[event.key];
 if(!direction)return;
 const [x,y]=direction;
 const zoomedStage=viewer.querySelector('.viewer-stage.is-zoomed');
 if(zoomedStage){
  event.preventDefault();
  zoomedStage.scrollLeft+=x*72;
  zoomedStage.scrollTop+=y*72;
 }else if(x){
  event.preventDefault();
  moveViewer(x);
  viewer.querySelector('.viewer-thumbs .active')?.focus({preventScroll:true});
 }
});
function adminShell(tab,body){app.innerHTML=`<div class="admin"><header class="admin-bar"><div style="display:flex;align-items:center"><a href="#/"><img src="/assets/logo.png" alt="LANDMADE"></a><strong>本地管理</strong></div><div style="display:flex;align-items:center;gap:20px"><a class="text-link" href="#/" target="_blank" rel="noopener">查看前台 ↗</a><button class="btn small" id="admin-logout">退出登录</button></div></header><div class="admin-layout"><nav class="sidebar"><a class="${tab==='home'?'active':''}" href="#/admin/home">首页管理</a><a class="${tab==='channels'?'active':''}" href="#/admin/channels">二级页面管理</a><a class="${tab==='products'?'active':''}" href="#/admin/products">产品图片管理</a><a class="${tab==='backup'?'active':''} sidebar-secondary" href="#/admin/backup">备份与恢复</a><a class="${tab==='internal'?'active':''}" href="#/admin/internal">内部浏览设置</a><a class="${tab==='password'?'active':''}" href="#/admin/password">修改密码</a></nav><main class="admin-main">${body}</main></div></div>`;document.querySelector('#admin-logout').onclick=()=>safe(async()=>{if(dirty&&!confirm('还有未保存的修改，确定退出登录？'))return;await api('/api/auth/logout',{});dirty=false;route()})}
function adminProducts(){adminShell('products',`<div class="admin-title"><div><h1>产品图片管理</h1><p class="muted">每个产品一组素材：名称 → 频道与标签 → 图片／视频 → 保存。</p></div><a class="btn primary" href="#/admin/edit/new">＋ 上传新产品</a></div><div class="toolbar"><input class="control" id="product-query" placeholder="搜索产品名称"><select class="control" id="product-cat" style="width:160px"><option value="">所有分类</option>${state.categories.map(c=>opt(c.id,c.zh,'')).join('')}</select><select class="control" id="product-status" style="width:130px"><option value="">全部状态</option><option value="live">已上架</option><option value="draft">已下架</option></select></div><div id="admin-list"></div>`);
 const render=()=>{const q=document.querySelector('#product-query').value.toLowerCase(),cat=document.querySelector('#product-cat').value,status=document.querySelector('#product-status').value;const list=[...state.products].sort((a,b)=>b.created-a.created).filter(p=>(p.en+' '+p.zh).toLowerCase().includes(q)&&(!cat||inCategory(p,cat))&&(!status||(status==='live')===p.published));document.querySelector('#admin-list').innerHTML=list.length?`<table class="admin-table"><thead><tr><th>产品 / ${list.length}</th><th>分类</th><th>状态</th><th>操作</th></tr></thead><tbody>${list.map(p=>`<tr><td><a class="product-cell" href="#/admin/edit/${E(p.id)}">${media(image(p),`alt=""`)}<span>${E(p.zh||p.en)}<small>${E(p.en)} · ${p.images.length} 个素材${p.demo?' · 示例':''}</small></span></a></td><td>${E(productCategories(p).map(id=>catBy(id)?.zh).join(" / "))}</td><td><span class="status ${p.published?'live':''}">${p.published?'已上架':'已下架'}</span></td><td><div class="row-actions"><a class="btn small" href="#/admin/edit/${E(p.id)}">编辑</a><button class="btn small" data-publish="${E(p.id)}">${p.published?'下架':'上架'}</button><button class="btn small danger" data-delete="${E(p.id)}">删除</button></div></td></tr>`).join('')}</tbody></table>`:empty('没有符合条件的产品');document.querySelectorAll('[data-publish]').forEach(b=>b.onclick=()=>safe(async()=>{const next=clone(state),p=next.products.find(p=>p.id===b.dataset.publish);p.published=!p.published;if(p.published)p.created=Date.now();await save(next);render();notice(p.published?'产品已上架':'产品已下架')}));document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>safe(async()=>{const p=productBy(b.dataset.delete);if(!confirm(`删除「${p.zh||p.en}」及其组图？\n建议先下载备份。此操作会从展示中移除产品。`))return;const next=clone(state);next.products=next.products.filter(x=>x.id!==p.id);next.settings.slides=next.settings.slides.filter(s=>s.product!==p.id);next.categories.forEach(c=>{if(c.heroProduct===p.id){c.heroProduct='';c.hero=''}});await save(next);render();notice('产品已删除')}))};render();document.querySelectorAll('#product-query,#product-cat,#product-status').forEach(el=>el.addEventListener(el.tagName==='INPUT'?'input':'change',render))}
async function safe(fn){try{await fn()}catch(e){notice(e.message);console.error(e)}}
function newId(){return crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2)}
function adminEdit(id){
 const original=id==='new'?null:productBy(id);if(id!=='new'&&!original)return notFound();
 draft=clone(original||{id:newId(),en:'',zh:'',category:state.categories[0].id,categories:[state.categories[0].id],description:'',descriptionZh:'',cover:'',hero:'',images:[],published:true,created:Date.now(),imageStatuses:{},mediaNames:{}});
 draft.imageStatuses ||= {};draft.mediaNames ||= {};if(original&&draft.cardImage===undefined)draft.cardImage=draft.cover||draft.images[0]||'';draft.banner=banner(draft);draft.bannerSource='custom';if(draft.channelBanner===undefined)draft.channelBanner=state.categories.find(c=>c.heroProduct===draft.id)?.hero||draft.banner||draft.hero||'';const slide=state.settings.slides.find(s=>s.product===draft.id),assigned=state.categories.filter(c=>c.heroProduct===draft.id);let channelPlacementChanged=false;dirty=false;
 adminShell('products',`<div class="admin-title"><div><h1>${original?'编辑产品':'上传新产品'}</h1><p class="muted">一个产品一组图片／视频。填写名称、选择频道、上传素材，最后保存。</p></div><a class="btn" href="#/admin/products">返回产品列表</a></div><form id="product-form">
 <section class="panel"><h2><span class="step-number">1</span> 产品信息</h2><div class="form-grid"><label class="field">产品名称 *<input name="zh" value="${E(draft.zh||draft.en)}" required maxlength="120" placeholder="例如：端午·成香茶礼盒"></label><label class="field">状态标签<select name="stage" id="product-stage">${Object.entries(imageStages).map(([key,v])=>opt(key,v.label,imageStage(draft,image(draft)))).join('')}</select></label></div><div class="field">上传到哪个频道 *（可多选）<div class="channel-checks">${state.categories.map(c=>`<label class="check"><input type="checkbox" name="categories" value="${E(c.id)}" ${inCategory(draft,c.id)?'checked':''}>${E(c.zh)}</label>`).join('')}</div></div><label class="field description-zh-field">产品描述<textarea name="descriptionZh" maxlength="1000" placeholder="显示在产品详情页的大图上方">${E(draft.descriptionZh)}</textarea></label><details class="optional-fields"><summary>英文名称与英文描述（选填）</summary><div class="form-grid"><label class="field">英文名称<input name="en" value="${E(draft.en===draft.zh?'':draft.en)}" maxlength="120"></label><label class="field">英文描述<textarea name="description" maxlength="1000">${E(draft.description)}</textarea></label></div></details></section>
 <section class="panel"><h2><span class="step-number">2</span> 上传图片／视频 <small class="muted" id="image-total"></small></h2><div class="upload-zone" id="drop-zone"><label class="btn primary">＋ 选择图片或视频<input id="image-files" type="file" accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,.mp4" multiple hidden></label><p>可以多选或拖入。原图最大 20MB，MP4 最大 60MB。静态图片上传后自动生成 300KB 以内的网页展示版，原图保留；视频和动态图保留原文件。</p><p class="muted">文件名 2 默认作为瀑布流推荐展示图，非方图自动居中裁切为1:1（保留原图）。详情组图按原比例展示。每张图片下有三个独立用途标签，点击选择，再次点击可取消；修改后保存。</p><div id="upload-status" class="busy-note"></div></div><div class="three-role-previews">${[['banner','首页推荐展示图','首页顶部大图轮播'],['channelBanner','频道页推荐展示图','频道页顶部大图'],['cardImage','瀑布流推荐展示图','1:1方图 · 非方图自动居中裁切']].map(([key,label,help])=>`<div class="role-preview-card"><div data-role-preview="${key}"></div><strong>${label}</strong><small>${help}</small><button type="button" class="btn small" data-clear-role="${key}">取消选择</button></div>`).join('')}</div><div class="edit-images" id="edit-images"></div></section>
 <section class="panel"><h2><span class="step-number">3</span> 首页／频道展示设置</h2><p class="muted">点击用途标签选择，再次点击取消；首页或频道推荐取消后会停用对应大图。瀑布流推荐取消后暂用默认封面，产品照常展示。三种用途独立保存。</p><div class="placement-options"><label class="check"><input id="use-home-banner" name="homepageBanner" type="checkbox" ${slide?'checked':''}> 启用首页推荐展示图</label><label class="check"><input id="use-channel-banner" name="channelBanner" type="checkbox" ${assigned.length?'checked':''}> 启用频道页推荐展示图</label></div><div id="banner-options"><div id="home-copy-fields"><h3>首页推荐展示图</h3><div class="banner-edit-row"><div id="product-banner-preview">${draft.banner?media(draft.banner,`class="setting-image" alt="首页推荐展示图预览"`):''}</div><div><label class="btn">另传首页推荐展示图<input type="file" id="product-banner-file" accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,.mp4" hidden></label><p class="muted">16:9，左侧留给首页文案。</p></div></div><div class="form-grid"><label class="field">首页大图英文标题<textarea name="bannerTitle" maxlength="120" placeholder="留空则跟随产品英文名称">${E(slide?.title)}</textarea></label><label class="field">首页大图中文文案<input name="bannerSubtitle" maxlength="120" value="${E(slide?.subtitle)}" placeholder="留空则跟随产品名称"></label></div></div><div id="channel-banner-fields"><h3>频道页推荐展示图</h3><div class="banner-edit-row"><div id="channel-banner-preview">${draft.channelBanner?media(draft.channelBanner,`class="setting-image" alt="频道页推荐展示图预览"`):''}</div><div><label class="btn">另传频道页推荐展示图<input type="file" id="channel-role-file" accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,.mp4" hidden></label><p class="muted">16:9，铺满频道顶部，不显示文案。</p></div></div><div class="field">用于哪些频道<div class="channel-checks">${state.categories.map(c=>`<label class="check"><input type="checkbox" name="bannerCategories" value="${E(c.id)}" ${assigned.some(a=>a.id===c.id)?'checked':''}>${E(c.zh)}</label>`).join('')}</div><small class="muted">不单独指定时，使用该产品所属频道。每个频道设一张顶部大图。</small></div></div></div></section>
 <div class="save-bar"><label class="check"><input name="published" type="checkbox" ${draft.published?'checked':''}> 在前台展示</label><button class="btn primary" type="submit" id="save-product">保存产品</button></div></form>`);
 const form=document.querySelector('#product-form');form.addEventListener('input',e=>{dirty=true;if(['channelBanner','bannerCategories','categories'].includes(e.target.name))channelPlacementChanged=true});drawEditImages();
 const placement=()=>{const home=document.querySelector('#use-home-banner').checked,channel=document.querySelector('#use-channel-banner').checked;document.querySelector('#banner-options').hidden=!home&&!channel;document.querySelector('#home-copy-fields').hidden=!home;document.querySelector('#channel-banner-fields').hidden=!channel;const selected=[...form.querySelectorAll('input[name=categories]:checked')].map(el=>el.value);form.querySelectorAll('input[name=bannerCategories]').forEach(el=>{el.closest('label').hidden=!selected.includes(el.value);if(!selected.includes(el.value))el.checked=false})};placement();document.querySelectorAll('#use-home-banner,#use-channel-banner,input[name=categories]').forEach(el=>el.onchange=placement);
 document.querySelector('#product-stage').onchange=e=>{draft.images.forEach(src=>draft.imageStatuses[src]=e.target.value);dirty=true;drawEditImages()};
 bindUpload('#image-files','#drop-zone',async(paths,files)=>{const stage=document.querySelector('#product-stage').value;paths.forEach((src,i)=>{draft.imageStatuses[src]=stage;draft.mediaNames[src]=files[i].name.replace(/\.[^.]+$/,'');const base=files[i].name.replace(/\.[^.]+$/,'');if(base==='2'&&!original&&draft.cardImage===undefined){draft.cover=src;draft.cardImage=src}});draft.images.push(...paths);if(!draft.cover)draft.cover=paths[0];if(draft.cardImage===undefined)draft.cardImage=paths[0];dirty=true;drawEditImages()});
 const drawBanner=()=>{if(['cover','hero'].includes(draft.bannerSource))draft.banner=draft[draft.bannerSource];document.querySelector('#product-banner-preview').innerHTML=draft.banner?media(draft.banner,`class="setting-image" alt="页面大图预览"`):''};
 bindUpload('#product-banner-file',null,async paths=>{draft.banner=paths[0];draft.bannerSource='custom';dirty=true;drawBanner();drawEditImages()});
 bindUpload('#channel-role-file',null,async paths=>{draft.channelBanner=paths[0];channelPlacementChanged=true;dirty=true;drawEditImages();document.querySelector('#channel-banner-preview').innerHTML=media(draft.channelBanner,`class="setting-image" alt="频道页推荐展示图预览"`)});
 form.onsubmit=e=>{e.preventDefault();safe(async()=>{if(uploading)throw Error('请等待上传完成');const f=new FormData(form);draft.zh=f.get('zh').trim();draft.en=f.get('en').trim()||draft.zh;draft.description=f.get('description').trim();draft.descriptionZh=f.get('descriptionZh').trim();draft.categories=f.getAll('categories');if(!draft.categories.length)throw Error('请至少选择一个频道');draft.category=draft.categories.includes(draft.category)?draft.category:draft.categories[0];draft.published=f.get('published')==='on';if(!draft.images.length)throw Error('请至少上传一张图片或一个视频');
 const next=clone(state),index=next.products.findIndex(p=>p.id===draft.id);if(index<0)next.products.push(draft);else next.products[index]=draft;
 if(f.get('homepageBanner')==='on'){if(!draft.banner)throw Error('请先选择首页推荐展示图');const title=f.get('bannerTitle').trim(),subtitle=f.get('bannerSubtitle').trim();const existing=next.settings.slides.filter(s=>s.product===draft.id);if(existing.length)existing.forEach((s,i)=>{s.image=draft.banner;s.imageMode='product';if(i===0){s.title=title;s.subtitle=subtitle}});else next.settings.slides.unshift({image:draft.banner,product:draft.id,title,subtitle,imageMode:'product'})}else next.settings.slides=next.settings.slides.filter(s=>s.product!==draft.id);
 if(channelPlacementChanged&&f.get('channelBanner')!=='on')next.categories.forEach(c=>{if(c.heroProduct===draft.id){c.hero='';c.heroProduct='';c.heroMode='custom'}});
 if(channelPlacementChanged&&f.get('channelBanner')==='on'){const chosen=f.getAll('bannerCategories'),targets=chosen.length?chosen:draft.categories;if(targets.some(id=>!draft.categories.includes(id)))throw Error('频道大图只能用于该产品所属的频道');if(!draft.channelBanner)throw Error('请先选择频道页推荐展示图');next.categories.forEach(c=>{if(c.heroProduct===draft.id&&!targets.includes(c.id)){c.hero='';c.heroProduct='';c.heroMode='custom'}if(targets.includes(c.id)){c.hero=draft.channelBanner;c.heroProduct=draft.id;c.heroMode='shared'}})}
 const b=document.querySelector('#save-product');b.disabled=true;try{await save(next);notice('产品已保存');location.hash='/admin/products'}finally{b.disabled=false}})};
}
function drawEditImages(){document.querySelectorAll('[data-role-preview]').forEach(el=>{const src=draft[el.dataset.rolePreview];el.innerHTML=src?media(src,`alt="当前用途图片"`):'<span class="muted">未选择</span>'});document.querySelectorAll('[data-clear-role]').forEach(b=>{b.disabled=!draft[b.dataset.clearRole];b.onclick=()=>{applyDraftRole(b.dataset.clearRole,null);drawEditImages()}});[['#product-banner-preview','banner'],['#channel-banner-preview','channelBanner']].forEach(([selector,key])=>{const el=document.querySelector(selector);if(el)el.innerHTML=draft[key]?media(draft[key],`class="setting-image" alt="当前推荐图片"`):'<span class="muted">未选择</span>'});const box=document.querySelector('#edit-images');document.querySelector('#image-total').textContent=`${draft.images.length} 个素材`;box.innerHTML=draft.images.map((src,i)=>`<div class="edit-image" draggable="true" data-drag="${i}">${media(src,`aria-label="第 ${i+1} 个素材"`,'play')}<label class="field compact-field">图片／视频名称<input data-media-name="${i}" value="${E(draft.mediaNames[src]||'素材 '+(i+1))}" maxlength="120"></label><label class="field compact-field">状态<select data-image-status="${i}">${Object.entries(imageStages).map(([key,v])=>opt(key,v.label,imageStage(draft,src))).join('')}</select></label><div class="image-options">${[['banner','首页推荐展示图'],['channelBanner','频道页推荐展示图'],['cardImage','瀑布流推荐展示图']].map(([key,label])=>`<button type="button" data-image-action="${key}" data-i="${i}" aria-pressed="${draft[key]===src}" class="role-tag ${draft[key]===src?'selected':''}">${draft[key]===src?'✓ ':''}${label}</button>`).join('')}<button type="button" data-image-action="left" data-i="${i}" ${i===0?'disabled':''} aria-label="向前移动">←</button><button type="button" data-image-action="right" data-i="${i}" ${i===draft.images.length-1?'disabled':''} aria-label="向后移动">→</button><button type="button" data-image-action="remove" data-i="${i}">移除</button></div></div>`).join('');
 box.querySelectorAll('[data-media-name]').forEach(el=>el.oninput=()=>{draft.mediaNames[draft.images[Number(el.dataset.mediaName)]]=el.value;dirty=true});box.querySelectorAll('[data-image-status]').forEach(el=>el.onchange=()=>{draft.imageStatuses[draft.images[Number(el.dataset.imageStatus)]]=el.value;dirty=true});
 box.querySelectorAll('[data-image-action]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.i),action=b.dataset.imageAction,src=draft.images[i];if(['banner','channelBanner','cardImage','cover'].includes(action)){applyDraftRole(action,src)}else if(action==='left'||action==='right'){const to=i+(action==='left'?-1:1);[draft.images[i],draft.images[to]]=[draft.images[to],draft.images[i]]}else{draft.images.splice(i,1);delete draft.imageStatuses[src];delete draft.mediaNames[src];if(draft.cover===src)draft.cover=draft.images[0]||'';if(draft.cardImage===src)applyDraftRole('cardImage',null);if(draft.banner===src)applyDraftRole('banner',null);if(draft.channelBanner===src)applyDraftRole('channelBanner',null);if(draft.hero===src)draft.hero=draft.images[0]||''}dirty=true;drawEditImages();const preview=document.querySelector('#product-banner-preview');if(preview&&draft.banner)preview.innerHTML=media(draft.banner,`class="setting-image" alt="首页推荐展示图预览"`);const cp=document.querySelector('#channel-banner-preview');if(cp&&draft.channelBanner)cp.innerHTML=media(draft.channelBanner,`class="setting-image" alt="频道页推荐展示图预览"`)});
 let from;box.querySelectorAll('[data-drag]').forEach(el=>{el.ondragstart=e=>{if(e.target.closest('input,select,video')){e.preventDefault();return}from=Number(el.dataset.drag);e.dataTransfer.setData('text/plain',String(from))};el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();if(!Number.isInteger(from))return;const to=Number(el.dataset.drag),[src]=draft.images.splice(from,1);draft.images.splice(to,0,src);from=undefined;dirty=true;drawEditImages()}});
}

const fileData=file=>new Promise((res,rej)=>{const reader=new FileReader();reader.onload=()=>res(reader.result);reader.onerror=()=>rej(Error('读取文件失败'));reader.readAsDataURL(file)});
async function upload(files,onProgress){const paths=[];for(let i=0;i<files.length;i++){const f=files[i];const video=f.type==='video/mp4'||/\.mp4$/i.test(f.name);if(!video&&!['image/png','image/jpeg','image/webp','image/gif'].includes(f.type))throw Error('支持 PNG / JPG / WebP / GIF 和 MP4');if(f.size>(video?60:20)*1024*1024)throw Error('图片最大 20MB，MP4 视频最大 60MB');onProgress?.(`正在上传 ${i+1} / ${files.length}：${f.name}`);const out=await api('/api/upload',{files:[{data:await fileData(f)}]});paths.push(...out.images)}return paths}
function bindUpload(inputId,zoneId,done){const input=document.querySelector(inputId),zone=document.querySelector(zoneId);const run=files=>safe(async()=>{if(!files.length)return;if(uploading)throw Error('有素材正在上传，请稍后');uploading=true;const status=document.querySelector('#upload-status');try{const paths=await upload([...files],s=>{if(status)status.textContent=s});await done(paths,[...files]);notice(`已上传 ${paths.length} 个素材，请保存修改`)}finally{uploading=false;if(status)status.textContent='';input.value=''}});input.onchange=()=>run(input.files);if(zone){zone.ondragover=e=>{e.preventDefault();zone.classList.add('dragover')};zone.ondragleave=()=>zone.classList.remove('dragover');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('dragover');run(e.dataTransfer.files)}}}
let settingsDraft,adminChannelId;
function adminSettings(){adminHome()}
function adminHome(){settingsDraft=clone(state);dirty=false;drawHomeManager()}
function arrivalManager(){const chosen=arrivalProducts(settingsDraft),ids=chosen.map(p=>p.id);return `<section class="panel" id="arrivals-manager"><h2>最新上架推荐 · ${chosen.length} / 3</h2><p class="muted">手动选择首页 NEW ARRIVALS 展示的产品，最多 3 个，按这里的顺序展示。撤销推荐不会下架产品，也不影响头图轮播和瀑布流。修改后点击底部「保存首页设置」。</p><div class="visual-picker">${chosen.map((p,i)=>`<div class="visual-choice latest-product-choice">${media(image(p),`alt="" loading="lazy"`)}<span>${i+1}. ${E(p.zh||p.en)}</span><div class="row-actions"><button type="button" class="btn small" data-arrival-move="${i}" data-step="-1" ${i===0?'disabled':''}>前移</button><button type="button" class="btn small" data-arrival-move="${i}" data-step="1" ${i===chosen.length-1?'disabled':''}>后移</button><button type="button" class="btn small danger" data-arrival-remove="${E(p.id)}">撤销推荐</button></div></div>`).join('')||'<p class="muted">暂未推荐产品，前台将隐藏最新上架推荐区。</p>'}</div><details class="optional-fields"><summary>＋ 选择推荐产品</summary><input id="arrival-search" class="control" placeholder="搜索产品名称"><div class="visual-picker">${settingsDraft.products.filter(p=>p.published&&!ids.includes(p.id)&&productCategories(p).some(id=>!settingsDraft.categories.find(c=>c.id===id)?.hidden)).sort((a,b)=>b.created-a.created).map(p=>`<button type="button" class="visual-choice" data-arrival-add="${E(p.id)}" data-arrival-name="${E((p.zh+' '+p.en).toLowerCase())}" ${chosen.length>=3?'disabled':''}>${media(image(p),`alt="" loading="lazy"`)}<span>${E(p.zh||p.en)}<small>${chosen.length>=3?'推荐位已满，请先撤销一个产品':'推荐到最新上架'}</small></span></button>`).join('')}</div></details></section>`}
function bindArrivalManager(){const update=ids=>{settingsDraft.settings.newArrivals=ids;dirty=true;drawHomeManager();document.querySelector('#arrivals-manager')?.scrollIntoView({block:'center'})};document.querySelectorAll('[data-arrival-add]').forEach(b=>b.onclick=()=>{const ids=arrivalProducts(settingsDraft).map(p=>p.id);if(ids.length>=3)return notice('最多推荐 3 个产品，请先撤销一个');if(!ids.includes(b.dataset.arrivalAdd))update([...ids,b.dataset.arrivalAdd])});document.querySelectorAll('[data-arrival-remove]').forEach(b=>b.onclick=()=>update(arrivalProducts(settingsDraft).map(p=>p.id).filter(id=>id!==b.dataset.arrivalRemove)));document.querySelectorAll('[data-arrival-move]').forEach(b=>b.onclick=()=>{const ids=arrivalProducts(settingsDraft).map(p=>p.id),i=Number(b.dataset.arrivalMove),to=i+Number(b.dataset.step);if(to<0||to>=ids.length)return;[ids[i],ids[to]]=[ids[to],ids[i]];update(ids)});document.querySelector('#arrival-search').oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('[data-arrival-add]').forEach(b=>b.hidden=!b.dataset.arrivalName.includes(q))}}
function homeCollectionManager(){const list=homeCollectionProducts(settingsDraft,true);const visible=new Set(settingsDraft.categories.filter(c=>!c.hidden).map(c=>c.id));return `<section class="panel" id="home-collection-manager"><div class="manager-row-title"><h2>首页瀑布流排序</h2><button type="button" class="btn small" id="collection-order-reset">恢复最新上传优先</button></div><p class="muted">调整首页 COLLECTION 全部作品的顺序：可上移、下移、置顶，或输入目标位置后点击「移动」。首页状态筛选沿用此顺序。修改后点击底部「保存首页设置」。已设置顺序时，新产品排在末尾；隐藏产品保留位置，前台会跳过。</p><div class="collection-order-list">${list.map((p,i)=>`<div class="collection-order-row" data-order-row="${E(p.id)}"><span class="collection-order-number">${i+1}</span>${media(image(p),`alt="" loading="lazy"`)}<div class="collection-order-name">${E(p.zh||p.en)}<small>${p.published?(productCategories(p).some(id=>visible.has(id))?'前台显示':'所属频道均已隐藏'):'产品已下架'}</small></div><div class="collection-order-actions"><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="-1" ${i===0?'disabled':''}>上移</button><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="1" ${i===list.length-1?'disabled':''}>下移</button><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="top" ${i===0?'disabled':''}>置顶</button><label class="collection-order-position">到第 <input type="number" min="1" max="${list.length}" value="${i+1}" data-collection-position="${E(p.id)}" aria-label="${E(p.zh||p.en)}目标位置"> 位</label><button type="button" class="btn small" data-collection-jump="${E(p.id)}">移动</button></div></div>`).join('')||'<p class="muted">还没有产品，请先上传。</p>'}</div></section>`}
function bindHomeCollectionManager(){const update=(id,to)=>{const ids=homeCollectionProducts(settingsDraft,true).map(p=>p.id);if(!Number.isInteger(to)||to<0||to>=ids.length)return notice('请输入 1 到 '+ids.length+' 之间的位置');settingsDraft.settings.homeCollectionOrder=moveHomeCollection(ids,id,to);dirty=true;redraw(id)};const redraw=id=>{const old=document.querySelector('.collection-order-list'),scroll=old?.scrollTop||0;document.querySelector('#home-collection-manager').outerHTML=homeCollectionManager();bindHomeCollectionManager();document.querySelector('.collection-order-list').scrollTop=scroll;if(id)document.querySelectorAll('[data-order-row]').forEach(row=>{if(row.dataset.orderRow===id)row.classList.add('order-row-changed')})};document.querySelectorAll('[data-collection-action]').forEach(b=>b.onclick=()=>{const ids=homeCollectionProducts(settingsDraft,true).map(p=>p.id),i=ids.indexOf(b.dataset.collectionAction);update(b.dataset.collectionAction,b.dataset.step==='top'?0:i+Number(b.dataset.step))});document.querySelectorAll('[data-collection-jump]').forEach(b=>b.onclick=()=>{const row=b.closest('[data-order-row]');update(b.dataset.collectionJump,Number(row.querySelector('[data-collection-position]').value)-1)});document.querySelector('#collection-order-reset').onclick=()=>{delete settingsDraft.settings.homeCollectionOrder;dirty=true;redraw();notice('已恢复最新上传优先，请保存首页设置')}}
function channelCollectionManager(){const list=channelCollectionProducts(settingsDraft.categories.find(c=>c.id===adminChannelId),settingsDraft,true);const visible=new Set(settingsDraft.categories.filter(c=>!c.hidden).map(c=>c.id));return `<section class="panel" id="channel-collection-manager"><div class="manager-row-title"><h2>频道内的产品 · 排序管理</h2><button type="button" class="btn small" id="collection-order-reset">恢复最新上传优先</button></div><p class="muted">调整当前频道瀑布流的顺序：可上移、下移、置顶，或输入目标位置后点击「移动」。每个频道独立排序，不影响首页或其他频道。修改后点击底部「保存二级页面设置」。已设置顺序时，新产品排在末尾；隐藏产品保留位置，前台会跳过。</p><div class="collection-order-list">${list.map((p,i)=>`<div class="collection-order-row" data-order-row="${E(p.id)}"><span class="collection-order-number">${i+1}</span>${media(image(p),`alt="" loading="lazy"`)}<div class="collection-order-name">${E(p.zh||p.en)}<small>${p.published?(productCategories(p).some(id=>visible.has(id))?'前台显示':'所属频道均已隐藏'):'产品已下架'}</small></div><div class="collection-order-actions"><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="-1" ${i===0?'disabled':''}>上移</button><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="1" ${i===list.length-1?'disabled':''}>下移</button><button type="button" class="btn small" data-collection-action="${E(p.id)}" data-step="top" ${i===0?'disabled':''}>置顶</button><label class="collection-order-position">到第 <input type="number" min="1" max="${list.length}" value="${i+1}" data-collection-position="${E(p.id)}" aria-label="${E(p.zh||p.en)}目标位置"> 位</label><button type="button" class="btn small" data-collection-jump="${E(p.id)}">移动</button></div></div>`).join('')||'<p class="muted">还没有产品，请先上传。</p>'}</div></section>`}
function bindChannelCollectionManager(){const update=(id,to)=>{const ids=channelCollectionProducts(settingsDraft.categories.find(c=>c.id===adminChannelId),settingsDraft,true).map(p=>p.id);if(!Number.isInteger(to)||to<0||to>=ids.length)return notice('请输入 1 到 '+ids.length+' 之间的位置');settingsDraft.categories.find(c=>c.id===adminChannelId).productOrder=moveHomeCollection(ids,id,to);dirty=true;redraw(id)};const redraw=id=>{const old=document.querySelector('.collection-order-list'),scroll=old?.scrollTop||0;document.querySelector('#channel-collection-manager').outerHTML=channelCollectionManager();bindChannelCollectionManager();document.querySelector('.collection-order-list').scrollTop=scroll;if(id)document.querySelectorAll('[data-order-row]').forEach(row=>{if(row.dataset.orderRow===id)row.classList.add('order-row-changed')})};document.querySelectorAll('[data-collection-action]').forEach(b=>b.onclick=()=>{const ids=channelCollectionProducts(settingsDraft.categories.find(c=>c.id===adminChannelId),settingsDraft,true).map(p=>p.id),i=ids.indexOf(b.dataset.collectionAction);update(b.dataset.collectionAction,b.dataset.step==='top'?0:i+Number(b.dataset.step))});document.querySelectorAll('[data-collection-jump]').forEach(b=>b.onclick=()=>{const row=b.closest('[data-order-row]');update(b.dataset.collectionJump,Number(row.querySelector('[data-collection-position]').value)-1)});document.querySelector('#collection-order-reset').onclick=()=>{delete settingsDraft.categories.find(c=>c.id===adminChannelId).productOrder;dirty=true;redraw();notice('已恢复最新上传优先，请保存二级页面设置')}}
function drawHomeManager(){adminShell('home',`<div class="admin-title"><div><h1>首页管理</h1><p class="muted">管理首页轮播大图、图上的文案和播放顺序。点击图片后进入对应产品详情。</p></div><a class="btn" href="#/">预览首页 ↗</a></div><section class="panel"><h2>频道显示与名称</h2><p class="muted">隐藏后，前台导航与筛选不显示该频道，频道内资料保留。产品若同时属于其他可见频道，仍可在那里展示。</p><div class="home-channel-head"><span>英文名称</span><span>中文名称</span><span>前台显示</span></div>${settingsDraft.categories.map(c=>`<div class="home-channel-row"><label class="field"><span class="sr-only">${E(c.id)} 英文频道名称</span><input data-home-channel="${E(c.id)}" data-key="en" value="${E(c.en)}" maxlength="40" aria-label="${E(c.zh)}英文名称"></label><label class="field"><span class="sr-only">${E(c.id)} 中文频道名称</span><input data-home-channel="${E(c.id)}" data-key="zh" value="${E(c.zh)}" maxlength="30" aria-label="${E(c.zh)}中文名称"></label><label class="check"><input data-channel-visible="${E(c.id)}" type="checkbox" ${c.hidden?'':'checked'}>显示</label></div>`).join('')}</section>${arrivalManager()}${homeCollectionManager()}<section class="panel"><h2>最新上传的产品</h2><p class="muted">可直接加入或下架首页头图轮播；只影响轮播，不影响产品和频道。修改后点击底部保存。</p><div class="visual-picker sync-product-shelf">${[...settingsDraft.products].sort((a,b)=>b.created-a.created).slice(0,6).map(p=>{const added=settingsDraft.settings.slides.some(s=>s.product===p.id);return `<div class="visual-choice latest-product-choice"><a href="#/admin/edit/${E(p.id)}">${media(image(p),`alt="" loading="lazy"`)}<span>${E(p.zh||p.en)}<small>${added?'已加入首页轮播':'未加入首页轮播'}</small></span></a><button type="button" class="btn small ${added?'danger':''}" data-home-toggle="${E(p.id)}">${added?'下架头图轮播':'加入头图轮播'}</button></div>`}).join('')}</div></section>${settingsDraft.settings.slides.map((s,i)=>{const p=settingsDraft.products.find(p=>p.id===s.product);return `<section class="panel"><div class="manager-row-title"><h2>首页大图 ${i+1} · ${E(p?.zh||p?.en||'产品')}</h2><div><button class="btn small" data-slide-move="${i}" data-step="-1" ${i===0?'disabled':''}>上移</button> <button class="btn small" data-slide-move="${i}" data-step="1" ${i===settingsDraft.settings.slides.length-1?'disabled':''}>下移</button> <button class="btn small danger" data-slide-remove="${i}">移出首页</button></div></div><div class="banner-edit-row"><div>${media(s.image,`class="manager-banner" alt="首页大图 ${i+1}"`)}<label class="btn small">替换图片／视频<input type="file" data-home-upload="${i}" accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,.mp4" hidden></label></div><div><label class="field">英文标题<textarea data-slide="${i}" data-key="title" maxlength="120" placeholder="留空则跟随产品英文名称">${E(s.title)}</textarea></label><label class="field">中文文案<input data-slide="${i}" data-key="subtitle" maxlength="120" value="${E(s.subtitle)}" placeholder="留空则跟随产品名称"></label><a class="text-link" href="#/admin/edit/${E(s.product)}">编辑这个产品 →</a><div class="synced-cover">${p?media(image(p),`alt="产品封面"`):''}<span>瀑布流推荐展示图 · 与图片管理同步</span></div><p class="muted">${p?.published?'产品已在前台展示':'产品已隐藏，本张轮播暂不在前台显示'}</p></div></div></section>`}).join('')}
 <section class="panel"><details><summary>＋ 从已上传的产品添加首页大图</summary><p class="muted">点击产品即可加入轮播；也可以在上传产品时勾选「用于首页大图轮播」。</p><input id="home-product-search" class="control" placeholder="搜索产品名称"><div class="visual-picker">${settingsDraft.products.filter(p=>!settingsDraft.settings.slides.some(s=>s.product===p.id)).map(p=>`<button class="visual-choice" data-home-product="${E(p.id)}" data-search-name="${E((p.zh+' '+p.en).toLowerCase())}">${media(p.banner||image(p),`alt="" loading="lazy"`)}<span>${E(p.zh||p.en)}</span></button>`).join('')}</div></details></section><div class="save-bar"><span id="settings-status" class="muted">修改后保存首页设置</span><button class="btn primary" id="save-settings">保存首页设置</button></div>`);
 bindArrivalManager();bindHomeCollectionManager();
 document.querySelectorAll('[data-home-channel]').forEach(el=>el.oninput=()=>{settingsDraft.categories.find(c=>c.id===el.dataset.homeChannel)[el.dataset.key]=el.value;dirty=true});
 document.querySelectorAll('[data-channel-visible]').forEach(el=>el.onchange=()=>{settingsDraft.categories.find(c=>c.id===el.dataset.channelVisible).hidden=!el.checked;dirty=true});
 document.querySelectorAll('[data-home-toggle]').forEach(b=>b.onclick=()=>{const id=b.dataset.homeToggle,p=settingsDraft.products.find(p=>p.id===id);if(settingsDraft.settings.slides.some(slide=>slide.product===id))settingsDraft.settings.slides=settingsDraft.settings.slides.filter(slide=>slide.product!==id);else settingsDraft.settings.slides.push({image:p.banner||image(p),product:id,title:'',subtitle:'',imageMode:'product'});dirty=true;drawHomeManager()});
 document.querySelectorAll('[data-slide][data-key]').forEach(el=>el.oninput=()=>{settingsDraft.settings.slides[Number(el.dataset.slide)][el.dataset.key]=el.value;dirty=true});document.querySelectorAll('[data-slide-move]').forEach(b=>b.onclick=()=>{const i=Number(b.dataset.slideMove),to=i+Number(b.dataset.step);[settingsDraft.settings.slides[i],settingsDraft.settings.slides[to]]=[settingsDraft.settings.slides[to],settingsDraft.settings.slides[i]];dirty=true;drawHomeManager()});document.querySelectorAll('[data-slide-remove]').forEach(b=>b.onclick=()=>{settingsDraft.settings.slides.splice(Number(b.dataset.slideRemove),1);dirty=true;drawHomeManager()});
 document.querySelectorAll('[data-home-product]').forEach(b=>b.onclick=()=>{const p=settingsDraft.products.find(p=>p.id===b.dataset.homeProduct);settingsDraft.settings.slides.push({image:p.banner||p.hero||image(p),product:p.id,title:'',subtitle:'',imageMode:'product'});dirty=true;drawHomeManager()});document.querySelector('#home-product-search').oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('[data-home-product]').forEach(b=>{if(b.dataset.searchName)b.hidden=!b.dataset.searchName.includes(q)})};
 document.querySelectorAll('[data-home-upload]').forEach(el=>el.onchange=()=>safe(async()=>{if(!el.files.length)return;await managerUpload(el,src=>{const slide=settingsDraft.settings.slides[Number(el.dataset.homeUpload)];slide.image=src;const p=settingsDraft.products.find(p=>p.id===slide.product);slide.imageMode='product';if(p){p.banner=src;p.bannerSource='custom'}},drawHomeManager)}));bindManagerSave('首页设置已保存');
}
function adminChannels(){settingsDraft=clone(state);dirty=false;adminChannelId=state.categories.some(c=>c.id===adminChannelId)?adminChannelId:state.categories[0].id;drawChannelManager()}
function drawChannelManager(){const c=settingsDraft.categories.find(c=>c.id===adminChannelId),p=channelProduct(c,settingsDraft),pic=channelBanner(c,p,settingsDraft);adminShell('channels',`<div class="admin-title"><div><h1>二级页面管理</h1><p class="muted">导航点击频道后，直接进入二级页：顶部大图＋产品瀑布流。没有图上文案和“最新上架”板块。</p></div><a class="btn" href="#/category/${E(c.id)}">预览此频道 ↗</a></div><div class="manager-tabs">${settingsDraft.categories.map(cat=>`<button class="${cat.id===c.id?'active':''}" data-channel-tab="${E(cat.id)}">${E(cat.zh)}</button>`).join('')}</div><section class="panel"><div class="manager-row-title"><h2>${E(c.zh)} · 频道大图</h2><button type="button" class="btn danger" id="channel-banner-remove" ${pic?'':'disabled'}>撤下频道页展示图</button></div><p class="muted">${pic?'当前频道顶部展示大图。撤下后只隐藏这张大图，频道产品照常展示；原图片保留，可重新选择。':'当前频道未展示顶部大图。选择图片或产品后，可重新展示。'} 修改后点击底部「保存二级页面设置」。</p>${pic?media(pic,`class="channel-manager-banner" alt="${E(c.zh)}频道大图预览"`):'<div class="empty">频道顶部大图未展示<small>下方产品瀑布流正常显示</small></div>'}<label class="btn primary">选择／替换频道大图<input type="file" id="channel-banner-upload" accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,.mp4" hidden></label><details class="optional-fields"><summary>或者：从本频道已上传的产品选一张</summary><div class="visual-picker">${settingsDraft.products.filter(p=>inCategory(p,c.id)).map(p=>`<button class="visual-choice" data-channel-product="${E(p.id)}">${media(p.channelBanner||p.hero||p.banner||image(p),`alt="" loading="lazy"`)}<span>${E(p.zh||p.en)}</span></button>`).join('')||'<p class="muted">本频道暂无产品，请先到产品图片管理上传。</p>'}</div></details></section>
 ${channelCollectionManager()}
 <section class="panel"><details><summary>导航名称和顺序（需要时再修改）</summary><div class="form-grid" style="margin-top:16px"><label class="field">英文导航<input data-nav-key="en" value="${E(c.en)}" maxlength="40"></label><label class="field">小中文导航<input data-nav-key="zh" value="${E(c.zh)}" maxlength="30"></label></div><button class="btn small" id="channel-up" ${settingsDraft.categories.indexOf(c)===0?'disabled':''}>导航向前移动</button> <button class="btn small" id="channel-down" ${settingsDraft.categories.indexOf(c)===settingsDraft.categories.length-1?'disabled':''}>导航向后移动</button></details></section><div class="save-bar"><span id="settings-status" class="muted">修改后保存二级页面设置</span><button class="btn primary" id="save-settings">保存二级页面设置</button></div>`);
 bindChannelCollectionManager();
 document.querySelectorAll('[data-channel-tab]').forEach(b=>b.onclick=()=>{adminChannelId=b.dataset.channelTab;drawChannelManager()});document.querySelectorAll('[data-nav-key]').forEach(el=>el.oninput=()=>{c[el.dataset.navKey]=el.value;dirty=true});for(const [id,step] of [['channel-up',-1],['channel-down',1]])document.querySelector('#'+id).onclick=()=>{const i=settingsDraft.categories.indexOf(c),to=i+step;[settingsDraft.categories[i],settingsDraft.categories[to]]=[settingsDraft.categories[to],settingsDraft.categories[i]];dirty=true;drawChannelManager()};
 document.querySelector('#channel-banner-remove').onclick=()=>{c.hero='';c.heroProduct='';c.heroMode='custom';dirty=true;drawChannelManager();notice('已撤下频道页展示图，请保存二级页面设置')};
 document.querySelector('#channel-banner-upload').onchange=()=>safe(async()=>{const input=document.querySelector('#channel-banner-upload');if(!input.files.length)return;await managerUpload(input,src=>{c.hero=src;c.heroMode='custom';c.heroProduct=''},drawChannelManager)});
 document.querySelectorAll('[data-channel-product]').forEach(b=>b.onclick=()=>{const p=settingsDraft.products.find(p=>p.id===b.dataset.channelProduct);c.hero=p.channelBanner||p.hero||p.banner||image(p);c.heroProduct=p.id;c.heroMode='shared';dirty=true;drawChannelManager()});bindManagerSave('二级页面设置已保存');
}
async function managerUpload(input,done,draw){if(uploading)throw Error('请等待当前上传完成');uploading=true;const status=document.querySelector('#settings-status');if(status)status.textContent='正在上传…';try{const paths=await upload([input.files[0]]);done(paths[0]);dirty=true;draw();notice('图片已上传，点击底部保存后生效')}finally{uploading=false;const s=document.querySelector('#settings-status');if(s)s.textContent='请保存修改'}}
function bindManagerSave(message){document.querySelector('#save-settings').onclick=()=>safe(async()=>{if(uploading)throw Error('请等待上传完成');const b=document.querySelector('#save-settings');b.disabled=true;try{await save(settingsDraft);settingsDraft=clone(state);if(location.hash.includes('/channels'))drawChannelManager();else drawHomeManager();notice(message);document.querySelector('#settings-status').textContent='已保存'}finally{b.disabled=false}})}

function adminBackup(){adminShell('backup',`<div class="admin-title"><div><h1>备份与恢复</h1><p class="muted">资料保存在这台电脑的项目 data 文件夹中。建议定期将备份复制到其他硬盘。</p></div></div><section class="panel"><h2>下载完整备份</h2><p class="muted">包含产品信息、导航、展示排序及上传的图片／视频。下载按流传输；可恢复 1GB 以内 ZIP（解压后最大 2GB）。</p><a class="btn primary" href="/api/backup" download>下载备份 ZIP</a></section><section class="panel"><h2>从备份恢复</h2><p class="muted">恢复会替换当前产品和设置。恢复前请先下载当前备份。系统也会在 data 中保留恢复前的数据快照。</p><label class="btn">选择备份 ZIP<input type="file" id="restore-file" accept=".zip" hidden></label><p class="muted" id="restore-status"></p></section><section class="panel"><h2>本地使用说明</h2><p class="muted">保持启动网站的终端窗口运行，关闭窗口会停止本地网站。<br>图片文件不会上传到互联网。把整个 landmade-local 文件夹复制到新电脑即可迁移。<br>从产品中移除的图片会保留在本地数据目录，便于恢复和备份；前台不再展示。</p></section>`);document.querySelector('#restore-file').onchange=e=>safe(async()=>{const f=e.target.files[0];if(!f)return;if(!confirm('恢复此备份将替换当前所有产品与设置。\n已下载当前备份，确认继续？')){e.target.value='';return}if(f.size>1024*1024*1024)throw Error('备份 ZIP 最大 1GB；更大的资料可复制整个项目文件夹迁移');const status=document.querySelector('#restore-status');status.textContent='正在恢复，请稍候…';try{const response=await fetch('/api/restore/file',{method:'POST',headers:{'Content-Type':'application/zip','X-Landmade':'local'},body:f}),out=await response.json();if(!response.ok)throw Error(out.error||'恢复失败');state=await api('/api/state');notice('备份已恢复');adminBackup()}finally{if(status.isConnected)status.textContent=''}})}
async function adminPassword(){
 const access=await api('/api/auth/password/access');if(!location.hash.startsWith('#/admin/password'))return;
 if(!access.allowed){
  adminShell('password',`<div class="admin-title"><div><h1>修改密码 · 身份验证</h1><p class="muted">验证通过后，才能进入修改密码页面。</p></div></div><section class="panel password-panel"><p class="password-question">提示：<strong>我是谁</strong></p><form id="password-verify-form"><label class="field">验证密码<input name="answer" type="password" autocomplete="off" required maxlength="256" id="password-answer"></label><p class="login-error" id="password-error" role="alert"></p><button class="btn primary" type="submit">验证并继续 →</button></form></section>`);
  const form=document.querySelector('#password-verify-form');form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button'),error=document.querySelector('#password-error');button.disabled=true;error.textContent='';try{await api('/api/auth/password/verify',{answer:form.elements.answer.value});form.reset();await adminPassword()}catch(err){error.textContent=err.message;form.elements.answer.select()}finally{if(button.isConnected)button.disabled=false}};return;
 }
 adminShell('password',`<div class="admin-title"><div><h1>修改后台登录密码</h1><p class="muted">身份验证已通过，请设置新的登录密码。</p></div></div><section class="panel password-panel"><form id="password-change-form"><label class="field">新密码<input name="newPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required placeholder="6–128个字符"></label><label class="field">再次输入新密码<input name="confirmPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label><p class="muted">保存后，所有已登录的后台将退出，需使用新密码重新登录。</p><p class="login-error" id="password-error" role="alert"></p><button class="btn primary" type="submit">保存新密码</button></form></section>`);
 const form=document.querySelector('#password-change-form');form.oninput=()=>dirty=true;form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button'),error=document.querySelector('#password-error');error.textContent='';if(form.elements.newPassword.value!==form.elements.confirmPassword.value){error.textContent='两次输入的新密码不一致';return}button.disabled=true;try{await api('/api/auth/password/change',{newPassword:form.elements.newPassword.value,confirmPassword:form.elements.confirmPassword.value});form.reset();dirty=false;state=null;notice('密码已修改，请使用新密码重新登录');location.hash='/admin/home'}catch(err){error.textContent=err.message;if(err.status===403){form.reset();dirty=false;await adminPassword()}}finally{if(button.isConnected)button.disabled=false}};
}

function internalAccessChanged(action){
 try{localStorage.setItem('landmade-internal-update',action+':'+Date.now()+'-'+Math.random())}catch{}
}

function showInternal(){
 document.title='内部浏览 · LANDMADE';
 app.innerHTML=nav('__internal')+`<main class="login-page internal-login">
  <section class="login-panel" aria-labelledby="internal-heading">
   <div class="login-eyebrow">INTERNAL ACCESS</div>
   <h1 id="internal-heading">内部浏览</h1>
   <p class="muted">输入内部浏览密码，查看完整作品。</p>
   <form id="internal-login-form">
    <label class="field">内部浏览密码<input name="password" type="password" autocomplete="current-password" maxlength="128" required></label>
    <p class="login-error" role="alert"></p>
    <button class="btn primary" type="submit">解锁浏览 →</button>
   </form>
   <a class="login-home" href="#/">← 返回公开首页</a>
  </section></main>`;
 const form=document.querySelector('#internal-login-form');
 const input=form.elements.password;
 const button=form.querySelector('button');
 const error=form.querySelector('.login-error');
 form.onsubmit=async event=>{
  event.preventDefault();
  button.disabled=true;
  error.textContent='';
  try{
   await api('/api/auth/internal/login',{password:input.value});
   form.reset();
   internalAccessChanged('unlock');
   if(form.isConnected)await route(true);
   else refreshPublicCatalog();
  }catch(err){
   error.textContent=err.message;
   if(form.isConnected)input.select();
  }finally{button.disabled=false}
 };
 input.focus({preventScroll:true});
}

async function adminInternal(ver){
 const preference=await api('/api/auth/internal/settings');
 if(ver!==routeVersion)return;
 const configured=preference.configured;
 adminShell('internal',`<div class="admin-title"><div><h1>内部浏览设置</h1>
  <p class="muted">访客可浏览设为前台展示的「制作中」和「已上架」作品。输入内部浏览密码后，可查看完整的前台作品。</p></div>
  <a class="btn" href="#/internal">查看内部入口 ↗</a></div>
  <section class="panel password-panel">
   <h2>${configured?'内部浏览密码':'设置内部浏览密码'}</h2>
   ${configured?`<div id="internal-password-summary">
    <p class="muted">密码已设置</p>
    <button class="btn primary" id="internal-password-edit" type="button" aria-controls="internal-settings-form">修改密码</button>
   </div>`:''}
   <form id="internal-settings-form" ${configured?'hidden':''}>
    <label class="field">${configured?'新的内部浏览密码':'内部浏览密码'}<input name="newPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label>
    <label class="field">${configured?'再次输入新密码':'再次输入密码'}<input name="confirmPassword" type="password" autocomplete="new-password" minlength="6" maxlength="128" required></label>
    <p class="muted">请使用 6–128 个字符，与后台管理密码分开设置。${configured?'修改后，已解锁的浏览器需要重新输入密码。':''}</p>
    <p class="login-error" role="alert"></p>
    <div class="row-actions">
     <button class="btn primary" type="submit">${configured?'保存修改':'保存内部浏览密码'}</button>
     ${configured?'<button class="btn" id="internal-password-cancel" type="button">取消</button>':''}
    </div>
   </form>
  </section>`);
 const form=document.querySelector('#internal-settings-form');
 const button=form.querySelector('button[type="submit"]');
 const error=form.querySelector('.login-error');
 const edit=document.querySelector('#internal-password-edit');
 const cancel=document.querySelector('#internal-password-cancel');
 if(configured){
  const summary=document.querySelector('#internal-password-summary');
  edit.onclick=()=>{
   summary.hidden=true;
   form.hidden=false;
   form.elements.newPassword.focus();
  };
  cancel.onclick=()=>{
   form.reset();
   error.textContent='';
   dirty=false;
   form.hidden=true;
   summary.hidden=false;
   edit.focus();
  };
 }
 form.oninput=()=>dirty=true;
 form.onsubmit=async event=>{
  event.preventDefault();
  error.textContent='';
  const newPassword=form.elements.newPassword.value;
  const confirmPassword=form.elements.confirmPassword.value;
  if(newPassword!==confirmPassword){error.textContent='两次输入的密码不一致';return}
  button.disabled=true;
  if(cancel)cancel.disabled=true;
  try{
   await api('/api/auth/internal/settings',{newPassword,confirmPassword});
   internalAccessChanged('lock');
   if(!form.isConnected)return;
   form.reset();
   dirty=false;
   notice(configured?'内部浏览密码已修改':'内部浏览密码已设置');
   await adminInternal(ver);
   if(ver===routeVersion)document.querySelector('#internal-password-edit')?.focus();
  }catch(err){error.textContent=err.message}
  finally{
   button.disabled=false;
   if(cancel)cancel.disabled=false;
  }
 };
}

function showLogin(){
 app.innerHTML=`<main class="login-page"><section class="login-panel"><a href="#/" aria-label="返回首页"><img src="/assets/logo.png" alt="蓝箭造办 LANDMADE"></a><div class="login-eyebrow">ADMIN ACCESS</div><h1>管理后台</h1><p class="muted">请输入管理密码进入。</p><form id="login-form"><label class="field">管理密码<input id="admin-password" name="password" type="password" autocomplete="current-password" required autofocus></label><p class="login-error" id="login-error" role="alert"></p><button class="btn primary" id="login-submit" type="submit">进入后台 →</button></form><a class="login-home" href="#/">← 返回产品展示</a></section></main>`;
 document.querySelector('#login-form').onsubmit=async e=>{e.preventDefault();const button=document.querySelector('#login-submit'),error=document.querySelector('#login-error');button.disabled=true;error.textContent='';try{await api('/api/auth/login',{password:document.querySelector('#admin-password').value});notice('登录成功');route()}catch(err){error.textContent=err.message;document.querySelector('#admin-password').select()}finally{if(button.isConnected)button.disabled=false}};
 document.querySelector('#admin-password').focus();
}
let lastHash=location.hash||'#/';
function stopPageMedia(){
 heroCleanup?.();
 heroCleanup=null;
 clearTimeout(heroTimer);
 document.querySelectorAll('video').forEach(video=>{
  video.pause();
  video.removeAttribute('src');
  video.querySelectorAll('source').forEach(source=>source.removeAttribute('src'));
  video.load();
 });
 if(viewer.open)viewer.close();
 viewer.replaceChildren();
 viewProduct=null;
}
function clearInternalView(){
 if(!internalUnlocked())return;
 stopPageMedia();
 state=null;
 app.replaceChildren();
}
async function exitInternalBrowse(button){
 button.disabled=true;
 try{
  await api('/api/auth/internal/logout',{});
  internalAccessChanged('lock');
  if(location.hash.startsWith('#/admin'))return;
  clearInternalView();
  history.replaceState(null,'','#/');
  await route(true);
 }catch(err){notice(err.message)}
 finally{button.disabled=false}
}
async function route(force=false){
 let hash=location.hash||'#/';
 if(hash==='#collection')hash='#/';
 if(uploading&&hash!==lastHash){
  history.replaceState(null,'',lastHash);
  notice('素材正在上传，请等待完成后再离开');
  return;
 }
 if(dirty&&hash!==lastHash&&!confirm('还有未保存的修改，确定离开？')){
  history.replaceState(null,'',lastHash);
  return;
 }
 dirty=false;
 stopPageMedia();
 lastHash=hash;
 const ver=++routeVersion;
 try{
  const parts=hash.slice(1).split('/').filter(Boolean).map(decodeURIComponent);
  const admin=parts[0]==='admin';
  if(admin){
   const session=await api('/api/auth/session');
   if(ver!==routeVersion)return;
   if(!session.authenticated){
    document.title='后台登录 · LANDMADE';
    showLogin();
    window.scrollTo({top:0,left:0,behavior:'auto'});
    return;
   }
  }
  if(force||admin||!state||stateIsAdmin){
   const catalog=await api('/api/state'+(admin?'?admin=1':''));
   if(ver!==routeVersion)return;
   state=catalog;
   stateIsAdmin=admin;
  }
  document.title='LANDMADE · 蓝箭造办';
  if(!parts.length)showHome();
  else if(parts[0]==='category')showCategory(parts[1]);
  else if(parts[0]==='product')showProduct(parts[1]);
  else if(parts[0]==='internal'){
   if(internalUnlocked()){
    history.replaceState(null,'','#/');
    lastHash='#/';
    showHome();
   }else showInternal();
  }
  else if(admin){
   document.title='后台管理 · LANDMADE';
   if(parts[1]==='edit')adminEdit(parts[2]);
   else if(parts[1]==='settings'||parts[1]==='home')adminHome();
   else if(parts[1]==='channels')adminChannels();
   else if(parts[1]==='backup')adminBackup();
   else if(parts[1]==='internal')await adminInternal(ver);
   else if(parts[1]==='password')await adminPassword();
   else adminProducts();
  }else notFound();
  if(ver===routeVersion)window.scrollTo({top:0,left:0,behavior:'auto'});
 }catch(e){
  if(ver!==routeVersion)return;
  app.innerHTML=`<main class="error">${E(e.message)}<p>请刷新页面后重试。</p><button class="btn" onclick="location.reload()">重新加载</button></main>`;
 }
}
document.addEventListener('click',event=>{
 const exit=event.target.closest('[data-internal-exit]');
 if(exit&&!event.defaultPrevented&&!exit.disabled){
  exitInternalBrowse(exit);
  return;
 }
 const link=event.target.closest('a[href]');
 if(!link||event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
 const url=new URL(link.href,location.href);
 if(url.origin!==location.origin||url.pathname!==location.pathname||url.search!==location.search||!url.hash.startsWith('#/')||url.hash==='#collection')return;
 event.preventDefault();
 if(location.hash!==url.hash)location.hash=url.hash;
});
window.addEventListener('hashchange',()=>route());window.addEventListener('beforeunload',e=>{if(dirty||uploading){e.preventDefault();e.returnValue=''}});if(location.pathname.startsWith('/admin')&&!location.hash)history.replaceState(null,'','#/admin/products');route();

// Synchronize idle admin and public tabs, including other devices on the LAN.
let checkingCatalog=false;
async function refreshPublicCatalog(){
 if(checkingCatalog||document.hidden||dirty||uploading||!state)return;
 const form=document.querySelector('#login-form,#internal-login-form,#internal-settings-form,#password-verify-form,#password-change-form');
 if(form||document.activeElement?.matches('input,textarea,select')||(viewer.open&&!internalUnlocked()))return;
 checkingCatalog=true;
 const hash=location.hash;
 const catalog=state;
 const ver=routeVersion;
 try{
  const admin=hash.startsWith('#/admin');
  const current=await api('/api/revision'+(admin?'?admin=1':''));
  if(ver!==routeVersion||catalog!==state||location.hash!==hash||dirty||uploading)return;
  const changedAccess=!admin&&Boolean(current.internal)!==internalUnlocked();
  const changedCatalog=current.revision!==catalog._revision||(current.mediaRevision||'')!==(catalog._mediaRevision||'');
  if(changedAccess||(!viewer.open&&changedCatalog)){
   const y=window.scrollY;
   if(changedAccess&&!current.internal)clearInternalView();
   await route(true);
   if(location.hash===hash)window.scrollTo({top:y,left:0,behavior:'auto'});
  }
 }catch(err){
  if(err.status===401&&ver===routeVersion&&location.hash.startsWith('#/admin')&&!dirty&&!uploading)await route();
 }finally{checkingCatalog=false}
}
window.addEventListener('storage',event=>{
 if(event.key==='landmade-internal-update'&&!location.hash.startsWith('#/admin')){
  if(event.newValue?.startsWith('lock:'))clearInternalView();
  route(true);
 }
 if(event.key==='landmade-catalog-update')refreshPublicCatalog();
});
window.addEventListener('focus',refreshPublicCatalog);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshPublicCatalog()});
setInterval(refreshPublicCatalog,8000);
