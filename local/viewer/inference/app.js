import {ChunkCache} from './chunk-cache.js';
import {createFaceViewer} from './renderer.js';

const $=id=>document.getElementById(id),audio=$('audio'),video=$('reference');
const emotionLabels={amazement:'惊讶',anger:'愤怒',cheekiness:'俏皮',disgust:'厌恶',fear:'恐惧',grief:'悲痛',joy:'开心',outofbreath:'气喘',pain:'疼痛',sadness:'难过'};
const colors={joy:'#9aaa55',amazement:'#c99360',sadness:'#7290ae',anger:'#bd7065',grief:'#9888af'};
const subtitles=['平稳语气 · 基准表情','轻快讲述 · 笑意变化','意外发现 · 眉眼变化','四种情绪 · 连续过渡','告别叙事 · 低落情绪'];
let manifest,demo,details,jaw,cache,viewer,wanted=false,buffering=false,loading=true,epoch=0,frameEpoch=0,lastFrame=-1,lastChunk=-1;
let activeController,chartCursor,activeEmotion=[];
const timeLabel=s=>`${String(Math.floor(s/60)).padStart(2,'0')}:${(s%60).toFixed(2).padStart(5,'0')}`;
const status=(text,error=false)=>{$('status').textContent=text;$('status').classList.toggle('error',error);};
const overlay=text=>{$('overlay').hidden=!text;$('overlay').textContent=text||'';};
const setEnabled=on=>{for(const id of ['play','seek','prev','next'])$(id).disabled=!on;};
function setWanted(value){wanted=value;$('play').textContent=value?'Ⅱ 暂停':'▶ 播放';$('play').setAttribute('aria-label',value?'暂停':'播放');if(!value){audio.pause();video.pause();}}
function fail(error){if(error.name==='AbortError')return;console.error(error);setWanted(false);buffering=false;status(error.message||String(error),true);overlay('载入失败，请刷新重试；也可下载原视频查看。');}
async function json(url,signal){const r=await fetch(url,{signal});if(!r.ok)throw new Error(`数据载入失败：HTTP ${r.status}`);return r.json();}

function buildClips(){
  manifest.demos.forEach((d,index)=>{
    const button=document.createElement('button');button.className='clip';button.dataset.id=d.id;
    button.innerHTML=`<span class="clip-top"><span>DEMO ${String(index+1).padStart(2,'0')}</span><span>20s / 60fps</span></span><strong></strong><small></small>`;
    button.querySelector('strong').textContent=d.title;button.querySelector('small').textContent=subtitles[index];
    button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>{if(viewer)selectDemo(d);});$('clips').append(button);
  });
}
function drawChart(){
  const svg=$('chart');svg.replaceChildren();$('legend').replaceChildren();
  const ns='http://www.w3.org/2000/svg',make=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;svg.append(el);return el;};
  const x=t=>32+t/20*850,y=v=>130-v*115;
  [0,.5,1].forEach(v=>{make('line',{x1:32,y1:y(v),x2:882,y2:y(v),stroke:'#e6ebdf','stroke-dasharray':v===0?'0':'3 5'});make('text',{x:4,y:y(v)+3,fill:'#a0aa93','font-size':10},v.toFixed(1));});
  [0,5,10,15,20].forEach(t=>make('text',{x:x(t),y:153,fill:'#a0aa93','font-size':10,'text-anchor':t===20?'end':'start'},`${t}s`));
  activeEmotion=details.emotionNames.map((name,i)=>({name,i,max:Math.max(...details.emotion.map(row=>row[i]))})).filter(e=>e.max>0);
  for(const e of activeEmotion){
    const color=colors[e.name]||'#87976d';
    let path='';for(let frame=0;frame<demo.frameCount;frame+=2)path+=`${frame?'L':'M'}${x(frame/demo.fps).toFixed(2)},${y(details.emotion[frame][e.i]).toFixed(2)} `;
    make('path',{d:path,fill:'none',stroke:color,'stroke-width':2.2});
    const item=document.createElement('span');item.style.setProperty('--color',color);item.textContent=emotionLabels[e.name]||e.name;item.dataset.emotion=e.name;$('legend').append(item);
  }
  if(!activeEmotion.length){make('line',{x1:32,y1:y(0),x2:882,y2:y(0),stroke:'#98a786','stroke-width':2});make('text',{x:380,y:66,fill:'#a0aa93','font-size':12},'中性输入 · 全部情绪通道为 0');}
  chartCursor=make('line',{x1:32,y1:8,x2:32,y2:134,stroke:'#4d6845','stroke-width':1.2});
}
function drawWaveform(){
  if(!details)return;const canvas=$('waveform'),rect=canvas.getBoundingClientRect(),scale=devicePixelRatio||1;
  canvas.width=Math.round(rect.width*scale);canvas.height=Math.round(rect.height*scale);
  const ctx=canvas.getContext('2d');ctx.scale(scale,scale);ctx.strokeStyle='#a6b998';ctx.lineWidth=1.4;
  details.waveform.forEach((v,i)=>{const x=(i+.5)/details.waveform.length*rect.width,h=Math.max(1,Math.sqrt(v)*25);ctx.beginPath();ctx.moveTo(x,15-h/2);ctx.lineTo(x,15+h/2);ctx.stroke();});
}
function updateDetails(){
  const i=manifest.demos.indexOf(demo);$('clip-title').textContent=demo.title;$('detail-title').textContent=demo.title;$('clip-number').textContent=`${String(i+1).padStart(2,'0')} / 05`;
  $('transcript').textContent=details.transcript;$('tags').replaceChildren();
  const tags=Object.entries(demo.peakEmotions).map(([name,value])=>`${emotionLabels[name]||name} ≤ ${value.toFixed(2)}`);
  for(const label of tags.length?tags:['中性 · 全部情绪为 0']){const el=document.createElement('span');el.textContent=label;$('tags').append(el);}
  $('downloads').replaceChildren();
  for(const [label,url] of [['动画 NPZ',demo.downloads.motion],['逐帧 CSV',demo.downloads.metrics],['情绪 JSON',demo.downloads.track],['运行记录',demo.downloads.run],['原视频',demo.video],['语音 WAV',demo.audio]]){
    const a=document.createElement('a');a.textContent=label;a.href=url;a.download='';$('downloads').append(a);
  }
  drawChart();drawWaveform();
}
function updateReadout(t,frame){
  $('seek').value=Math.round(t*demo.fps);$('seek').setAttribute('aria-valuetext',timeLabel(t));$('time').textContent=`${timeLabel(t)} / ${timeLabel(demo.duration)}`;$('frame').textContent=`帧 ${frame+1} / ${demo.frameCount}`;
  if(chartCursor){chartCursor.setAttribute('x1',32+t/demo.duration*850);chartCursor.setAttribute('x2',32+t/demo.duration*850);}
  $('skin-rms').textContent=details.metrics.skin_rms[frame].toFixed(3);$('tongue-rms').textContent=details.metrics.tongue_rms[frame].toFixed(3);$('jaw-dy').textContent=details.metrics.jaw0_dy[frame].toFixed(3);
  for(const el of $('legend').children){const name=el.dataset.emotion,i=details.emotionNames.indexOf(name);el.textContent=`${emotionLabels[name]||name} ${details.emotion[frame][i].toFixed(2)}`;}
}
function syncVideo(force=false){
  if(!$('compare').checked||!demo)return;
  if(video.readyState>=1&&(force||Math.abs(video.currentTime-audio.currentTime)>.09))video.currentTime=Math.min(audio.currentTime,demo.duration-.001);
  video.playbackRate=audio.playbackRate;
  if(wanted&&!buffering&&!loading&&!audio.paused){if(video.paused)video.play().catch(()=>{});}else video.pause();
}
function showFrame(t){
  const position=Math.min(demo.frameCount-1,Math.max(0,t*demo.fps));
  // Media clocks can round a requested frame time down by a microsecond.
  const nearest=Math.round(position),exact=Math.abs(position-nearest)<.001?nearest:position;
  const frame=Math.floor(exact),index=cache.index(frame),data=cache.get(index);
  if(!data)return false;
  if(exact!==lastFrame){viewer.setFrame(data,frame-index*manifest.chunkFrames,exact-frame,jaw,frame);lastFrame=exact;}
  updateReadout(t,frame);
  if(index!==lastChunk){lastChunk=index;cache.focus(index);cache.load(index+1).catch(e=>{if(e.name!=='AbortError')console.warn('下一动画块预加载失败，将在播放时重试',e);});}
  return true;
}
async function resume(){
  if(!wanted||loading||buffering)return;const token=epoch;
  try{await audio.play();if(token!==epoch)return;if(!wanted){audio.pause();return;}syncVideo(true);status('正在播放 · 原始 60 fps 数据');}
  catch(e){if(token===epoch&&e.name!=='AbortError'){setWanted(false);status('浏览器未开始播放，请再次点击播放。',true);}}
}
async function ensureFrame(t){
  if(!cache||!viewer||!jaw)return;
  const token=++frameEpoch,clipToken=epoch,index=cache.index(Math.min(demo.frameCount-1,Math.floor(t*demo.fps)));
  cache.focus(index);
  if(showFrame(t)){buffering=false;overlay(null);syncVideo(true);if(wanted)resume();else status('已暂停 · 可逐帧查看');return;}
  buffering=true;audio.pause();video.pause();overlay('正在读取这一段动画…');status('缓冲中 · 音频已暂停，等待画面');
  try{
    await cache.load(index);if(token!==frameEpoch||clipToken!==epoch)return;
    buffering=false;showFrame(audio.currentTime);overlay(null);syncVideo(true);status('已就绪 · 可播放、逐帧或拖动进度');if(wanted)resume();
  }catch(e){if(token===frameEpoch&&clipToken===epoch)fail(e);}
}
async function selectDemo(selected){
  const token=++epoch;++frameEpoch;setWanted(false);loading=true;buffering=false;setEnabled(false);cache?.dispose();activeController?.abort();activeController=new AbortController();
  demo=selected;lastFrame=-1;lastChunk=-1;details=null;jaw=null;audio.src=demo.audio;audio.playbackRate=Number($('speed').value);audio.muted=$('mute').checked;video.src=demo.video;video.muted=true;
  $('seek').value=0;$('seek').max=demo.frameCount;$('clip-title').textContent=demo.title;$('detail-title').textContent=demo.title;$('transcript').textContent='载入中…';
  for(const button of $('clips').children)button.setAttribute('aria-pressed',String(button.dataset.id===demo.id));
  const url=new URL(location.href);url.searchParams.set('demo',demo.id);history.replaceState(null,'',url);
  overlay('载入片段与首帧…');status('校验通过 · 正在载入片段');
  cache=new ChunkCache(demo,{stride:manifest.stride,chunkFrames:manifest.chunkFrames});
  try{
    const [data,jawData]=await Promise.all([
      json(demo.details,activeController.signal),fetch(demo.jaw,{signal:activeController.signal}).then(async r=>{if(!r.ok)throw new Error('下颌动画载入失败');return new Float32Array(await r.arrayBuffer());}),cache.load(0)]);
    if(token!==epoch)return;details=data;jaw=jawData;if(jaw.length!==demo.frameCount*7)throw new Error('下颌帧数不匹配');
    updateDetails();loading=false;setEnabled(true);await ensureFrame(0);status('已就绪 · 点击播放开始');
  }catch(e){if(token===epoch)fail(e);}
}
function seek(t){
  if(loading||!demo)return;t=Math.max(0,Math.min(demo.duration,t));audio.currentTime=t;ensureFrame(t);
}
$('play').addEventListener('click',()=>{if(wanted){setWanted(false);status('已暂停');}else{setWanted(true);if(audio.currentTime>=demo.duration-.005)seek(0);else ensureFrame(audio.currentTime);}});
$('seek').addEventListener('input',e=>seek(Number(e.target.value)/demo.fps));
$('prev').addEventListener('click',()=>{setWanted(false);seek((Math.round(audio.currentTime*demo.fps)-1)/demo.fps);});
$('next').addEventListener('click',()=>{setWanted(false);seek((Math.round(audio.currentTime*demo.fps)+1)/demo.fps);});
$('speed').addEventListener('change',()=>{audio.playbackRate=Number($('speed').value);video.playbackRate=audio.playbackRate;});
$('mute').addEventListener('change',()=>audio.muted=$('mute').checked);
$('compare').addEventListener('change',()=>{$('video-stage').hidden=!$('compare').checked;$('stages').classList.toggle('comparing',$('compare').checked);if(!$('compare').checked)video.pause();else syncVideo(true);});
$('appearance').addEventListener('change',()=>viewer?.setAppearance($('appearance').value));
$('reset-view').addEventListener('click',()=>viewer?.reset());
audio.addEventListener('ended',()=>{if($('loop').checked&&wanted)seek(0);else{setWanted(false);status('播放结束 · 可逐帧查看或重新播放');}});
audio.addEventListener('error',()=>{if(demo)fail(new Error('音频载入失败，请刷新或下载 WAV 检查。'));});
video.addEventListener('loadedmetadata',()=>syncVideo(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden){setWanted(false);status('页面已切到后台，回放暂停');}});
document.addEventListener('keydown',e=>{if(e.code==='Space'&&!['INPUT','SELECT','BUTTON','TEXTAREA','SUMMARY'].includes(document.activeElement.tagName)&&!loading){e.preventDefault();$('play').click();}});
new ResizeObserver(drawWaveform).observe($('waveform').parentElement);
function tick(){
  requestAnimationFrame(tick);
  if(viewer&&demo&&!loading&&!buffering&&details){if(!showFrame(Math.min(audio.currentTime,demo.duration)))ensureFrame(audio.currentTime);syncVideo();}
  viewer?.render();
}
async function init(){
  try{
    manifest=await json('/demo-data/v3-20s-01-05/web/manifest.json');buildClips();
    status('5 段数据校验通过 · 正在载入 v3 头模和材质');viewer=await createFaceViewer($('viewport'),manifest.scene);
    requestAnimationFrame(tick);
    const id=new URL(location.href).searchParams.get('demo');await selectDemo(manifest.demos.find(d=>d.id===id)||manifest.demos[0]);
  }catch(e){fail(e);}
}
window.addEventListener('pagehide',()=>{cache?.dispose();activeController?.abort();viewer?.dispose();audio.pause();video.pause();});
init();
