const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const COMMIT = '112c5eb3408afd065ac8974b2c6ea9ab0e3965c6';
const fields = ['model','epochs','checkpoint','data_path','actor','fps','language','emotions','host','port','root'];
const stages = {environment:'环境与依赖', data:'数据与划分', preprocess:'预处理 / PCA',train:'模型训练',export:'ONNX 导出',inference:'验证动画'};
const statuses = {starting:'正在连接',running:'运行中',succeeded:'完成 · 待质量验收',failed:'执行失败',cancelled:'已停止',unknown:'远端状态未知',skipped:'跳过'};
let checked = '', checkedAt = 0, busy = false, jobs = [], selectedJob = '', noticeTimer, apiFailed = false;
const element = (tag, text, className) => {const n=document.createElement(tag);n.textContent=text;if(className)n.className=className;return n;};
function notice(text, error=false) { const n=$('#notice');n.textContent=text;n.hidden=false;n.classList.toggle('error',error);clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>n.hidden=true,error?14000:6500); }
function openTab(name, scroll=false) {
  if(!['data','config','jobs','references'].includes(name))name='data';
  $$('[data-tab]').forEach(n=>{const active=n.dataset.tab===name;n.setAttribute('aria-selected',String(active));n.tabIndex=active?0:-1;});
  $$('[role=tabpanel]').forEach(n=>n.hidden=n.id!=='panel-'+name);
  history.replaceState(null,'','#'+name);
  if(scroll) $('.tabs').scrollIntoView({behavior:'smooth',block:'start'});
}
$$('[data-tab]').forEach(n=>{n.addEventListener('click',()=>openTab(n.dataset.tab));n.addEventListener('keydown',e=>{const list=$$('[data-tab]');let i=list.indexOf(n);if(e.key==='ArrowRight')i=(i+1)%list.length;else if(e.key==='ArrowLeft')i=(i+list.length-1)%list.length;else return;e.preventDefault();list[i].focus();openTab(list[i].dataset.tab);});});
$$('[data-go]').forEach(n=>n.addEventListener('click',()=>openTab(n.dataset.go,true)));
$$('[data-source]').forEach(n=>{n.href=`https://github.com/NVIDIA/Audio2Face-3D-Training-Framework/blob/${COMMIT}/${n.dataset.source}`;n.target='_blank';n.rel='noreferrer';});
function plan(){const p=Object.fromEntries(fields.map(k=>[k,$('#'+k).value.trim()]));p.dataset=$('[name=dataset]:checked').value;for(const k of ['port','epochs','fps'])p[k]=Number(p[k]);return p;}
const signature=()=>JSON.stringify(plan());
function persist(){try{localStorage.setItem('a2f-training-plan-v1',JSON.stringify(plan()));}catch{}}
function update(changed=false){
  const p=plan(), sample=p.dataset==='sample', diffusion=p.model==='diffusion';
  if(changed){checked='';checkedAt=0;persist();$('#environment-results').hidden=true;}
  $('#sample-config').hidden=!sample;$('#custom-config').hidden=sample;
  $('#dataset-summary').textContent=sample?'NVIDIA Claire 官方样例':'自定义角色 · '+p.actor;
  $('#plan-dataset').textContent=sample?'官方 Claire 样例':p.actor||'自定义角色';
  $('#plan-model').textContent=diffusion?'Diffusion':'Regression';
  $('#plan-epochs').textContent=p.epochs+' epochs';$('#plan-mode').textContent=p.checkpoint?'从兼容权重微调':'从头训练';
  $('#route-note').textContent=diffusion?'官方默认 400 轮，batch size = 1。完成训练与导出后，使用一段留出音频生成顶点验证动画。':'官方默认 50 轮，batch size = 32。该版本尚未实现 Regression Python 推理；导出后需要到 Maya-ACE 验证。';
  const items=['训练权重 · weights.pth','部署模型 · ONNX 与配置',diffusion?'一段留出音频的验证动画 · NPY':'Maya-ACE 部署文件 · 待外部验证'];
  $('#deliverables').replaceChildren(...items.map(s=>element('li',s)));
  const ready=checked===signature()&&Date.now()-checkedAt<600000;
  const active=jobs.some(j=>!['succeeded','failed','cancelled'].includes(j.status));
  $('#start-training').disabled=!ready||busy||active;
  $('#inspect').disabled=busy;
  $('#connection-dot').classList.toggle('ready',ready);
  $('#connection-title').textContent=ready?'训练机检查通过':p.host?'训练机待检查':'尚未连接 GPU 训练机';
  $('#connection-note').textContent=ready?p.host+' · 检查结果有效期 10 分钟；启动前将再次检查环境。':'现在可以准备数据和导出运行包；连接 Linux / WSL + NVIDIA GPU 后开始训练。';
  $('#plan-status').replaceChildren(element('span','',ready?'dot ready':'dot'),element('span',ready?'检查通过 · 可以启动':p.host?'待检查训练机':'待连接训练机'));
  $('#launch-note').textContent=active?'已有任务运行或状态未知，请先查看运行记录。':ready?'将下载依赖和数据，在训练机实际执行并占用 GPU。':'先填写训练机信息并通过检查。';
  $('#plan-preview').textContent=[`框架：${COMMIT.slice(0,12)}`,`训练目录：${p.root}`,`数据：${sample?'官方 Claire（自动下载）':p.data_path||'待填写'}`,`模型：${p.model} / ${p.epochs} epochs`,p.checkpoint?`初始化权重：${p.checkpoint}`:'从头训练','', '环境检查 → 获取依赖 → 配对检查', '按 shot 留出约 20% → 训练集预处理', '训练 → 检查 weights.pth → ONNX 导出',diffusion?'留出音频推理 → 检查 NPY 产物':'外部 Maya-ACE 验证', '', '导出包在 GPU 机器运行：','python3 worker.py run-plan plan.json'].join('\n');
}
try{const saved=JSON.parse(localStorage.getItem('a2f-training-plan-v1')||'null');if(saved){fields.forEach(k=>{if(saved[k]!=null)$('#'+k).value=saved[k];});const source=$(`[name=dataset][value="${saved.dataset==='custom'?'custom':'sample'}"]`);source.checked=true;}}catch{}
$('#config-form').addEventListener('submit',e=>e.preventDefault());
$('#config-form').addEventListener('input',()=>update(true));
$('#model').addEventListener('change',()=>{$('#epochs').value=$('#model').value==='diffusion'?400:50;update(true);});
$$('[name=dataset]').forEach(n=>n.addEventListener('change',()=>update(true)));
$('#smoke-preset').addEventListener('click',()=>{$('#epochs').value=5;update(true);notice('已设置 5 轮，用于验证流程；不代表训练质量达标。');});
$('#official-preset').addEventListener('click',()=>{$('#epochs').value=$('#model').value==='diffusion'?400:50;update(true);});
$('#reset-config').addEventListener('click',()=>{$('#config-form').reset();$('[name=dataset][value=sample]').checked=true;update(true);notice('已恢复官方样例与默认训练参数。');});
async function request(path, body){const response=await fetch('/api/training/'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-A2F-Workbench':'1'},body:JSON.stringify(body)}:{cache:'no-store'});if(!response.ok){const e=await response.json().catch(()=>({error:'本地服务没有返回有效 API 结果，请重新启动 serve_preview.py'}));throw Error(e.error||`请求失败 (${response.status})`);}return response;}
function renderChecks(result){const box=$('#environment-results');box.hidden=false;box.replaceChildren(element('strong',result.ready?'环境检查通过':'环境尚未就绪',result.ready?'good':'bad'));for(const c of result.checks||[]){box.append(element('p',(c.ok?'✓ ':'× ')+c.name,c.ok?'good':'bad'));const d=element('details','');d.append(element('summary','详情'),element('p',c.detail));box.append(d);}if(result.dataset)box.append(element('p',`已配对 ${result.dataset.shots.length} 个片段。`));if(result.sample_download_pending)box.append(element('p','官方数据集尚未下载，将在启动后下载并再次检查。'));box.append(element('p',result.note||''));}
$('#inspect').addEventListener('click',async()=>{if(!plan().host){openTab('config');$('#host').focus();notice('请填写训练机 SSH 地址；没有训练机时可以先导出运行包。');return;}const key=signature();busy=true;checked='';update();$('#inspect').textContent='正在检查…';try{const result=await (await request('inspect',{plan:plan()})).json();if(key!==signature()){notice('配置已变化，请重新检查当前配置。');return;}renderChecks(result);if(result.ready){checked=key;checkedAt=Date.now();}notice(result.ready?'训练机检查通过。':'检查完成，有项目需要处理。',!result.ready);}catch(e){notice(e.message,true);}finally{busy=false;$('#inspect').textContent='检查训练机 ↗';update();}});
$('#download-kit').addEventListener('click',async()=>{const b=$('#download-kit');b.disabled=true;try{const response=await request('bundle',{plan:plan()});const url=URL.createObjectURL(await response.blob());const link=element('a','');link.href=url;link.download='a2f-training-kit.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);notice('运行包已导出：配置、GPU 执行脚本与说明。训练尚未启动。');}catch(e){notice(e.message,true);}finally{b.disabled=false;}});
$('#start-training').addEventListener('click',async()=>{busy=true;update();try{const j=await (await request('start',{plan:plan()})).json();selectedJob=j.id;openTab('jobs',true);notice('任务已提交，正在连接训练机。');await refreshJobs();}catch(e){notice(e.message,true);}finally{busy=false;update();}});
function renderJob(){
  const j=jobs.find(x=>x.id===selectedJob)||jobs.at(-1);if(!j)return;selectedJob=j.id;$('#job-select').value=j.id;
  $('#job-state').textContent=statuses[j.status]||j.status;$('#job-detail').textContent=j.detail||`${j.plan.model} · ${j.plan.epochs} 轮 · ${j.plan.host}`;
  $('#cancel-job').disabled=['succeeded','failed','cancelled'].includes(j.status);
  $('#job-stages').replaceChildren(...Object.entries(stages).map(([key,label])=>{const state=j.stages[key];return element('div',label+' · '+(state?statuses[state]||state:'等待'), 'run-stage '+(state||''));}));
  const log=$('#job-log'),atBottom=log.scrollHeight-log.scrollTop-log.clientHeight<45;log.textContent=j.log_tail||'等待训练机返回日志…';if(atBottom)log.scrollTop=log.scrollHeight;
  const a=$('#job-artifacts');a.hidden=!j.artifacts;if(j.artifacts){a.replaceChildren(element('strong','产物保存在 GPU 训练机'),...Object.entries(j.artifacts).map(([k,v])=>element('p',k+'：'+(Array.isArray(v)?v.join(', '):v))));}
}
async function refreshJobs(){try{const data=await (await request('status')).json();jobs=data.jobs;$('#job-count').textContent=jobs.length;$('#empty-jobs').hidden=!!jobs.length;$('#jobs-content').hidden=!jobs.length;$('#job-select').replaceChildren(...[...jobs].reverse().map(j=>{const o=element('option',j.id+' · '+(statuses[j.status]||j.status));o.value=j.id;return o;}));renderJob();update();apiFailed=false;}catch(e){if(!apiFailed){notice(e.message,true);apiFailed=true;}}}
$('#job-select').addEventListener('change',()=>{selectedJob=$('#job-select').value;renderJob();});$('#refresh-jobs').addEventListener('click',refreshJobs);
$('#cancel-job').addEventListener('click',async()=>{const b=$('#cancel-job');b.disabled=true;try{const r=await(await request('cancel',{id:selectedJob})).json();notice(r.detail);await refreshJobs();}catch(e){notice(e.message,true);}finally{renderJob();}});
// Local metadata preflight; all file bytes stay in the browser.
async function wavInfo(file){const b=await file.slice(0,262144).arrayBuffer(),v=new DataView(b),text=(o,n)=>new TextDecoder().decode(b.slice(o,o+n));if(text(0,4)!=='RIFF'||text(8,4)!=='WAVE')throw Error('WAV 不是 RIFF/WAVE');let rate,bits,channels,format,size;for(let i=12;i+8<=b.byteLength;){const id=text(i,4),n=v.getUint32(i+4,true);if(id==='fmt '&&n>=16&&i+24<=b.byteLength){format=v.getUint16(i+8,true);channels=v.getUint16(i+10,true);rate=v.getUint32(i+12,true);bits=v.getUint16(i+22,true);}if(id==='data'){size=n;break;}i+=8+n+(n%2);}if(format!==1||!rate||!channels||!bits||size===undefined)throw Error('需要标准 PCM WAV，或 WAV 头部超出预检范围');if(rate<16000||bits<16)throw Error('音频需 ≥16 kHz / 16 bit');return{duration:size/(rate*channels*bits/8),rate,bits};}
async function npyInfo(file){const b=await file.slice(0,65560).arrayBuffer(),v=new DataView(b),dec=new TextDecoder('latin1');if(dec.decode(b.slice(1,6))!=='NUMPY'||v.getUint8(0)!==147)throw Error('无效 NPY；请检查是否是 Git LFS 指针');const major=v.getUint8(6);if(![1,2,3].includes(major))throw Error('不支持的 NPY 版本');const start=major===1?10:12,length=major===1?v.getUint16(8,true):v.getUint32(8,true);if(length>65536)throw Error('NPY 头部过大');const header=dec.decode(b.slice(start,start+length));const match=header.match(/['"]shape['"]\s*:\s*\(([^)]+)\)/),dtype=header.match(/['"]descr['"]\s*:\s*['"]([<>=|]f[48])['"]/);if(!match||!dtype)throw Error('NPY 需要 float32 / float64 数值顶点');const shape=match[1].split(',').map(s=>s.trim()).filter(Boolean).map(Number);if(shape.length!==3||shape[2]!==3||shape.some(v=>!Number.isSafeInteger(v)||v<=0))throw Error('NPY 形状应为 [帧数, 顶点数, 3]');if(start+length+shape.reduce((a,b)=>a*b,1)*Number(dtype[1].at(-1))!==file.size)throw Error('NPY 文件大小与头部不一致');return shape;}
$('#choose-folder').addEventListener('click',()=>$('#folder-input').click());
$('#folder-input').addEventListener('change',async e=>{
  const files=[...e.target.files],box=$('#folder-result');if(!files.length)return;box.hidden=false;box.textContent='正在本地检查文件元数据…';
  const mapping=new Map(files.map(f=>[f.webkitRelativePath.split('/').slice(1).join('/'),f])), audios=[...mapping.keys()].filter(s=>/^audio\/[^/]+\.wav$/.test(s));const errors=[],warnings=[],verts=new Set();let paired=0,seconds=0;const fps=Number($('#fps').value)||30;
  for(const key of audios){const name=key.slice(6,-4),candidate=[`cache/skin/${name}/${name}.npy`,`cache/skin/${name}/${name}.pc2`,`cache/skin/${name}/${name}.xml`,`cache/skin/${name}.npy`,`cache/skin/${name}.pc2`,`cache/skin/${name}.xml`].find(n=>mapping.has(n));if(!candidate){errors.push(name+'：缺少同名动画缓存');continue;}try{if(!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(name))throw Error('片段名仅支持字母、数字、下划线和横线');const wav=await wavInfo(mapping.get(key));if(candidate.endsWith('.npy')){const shape=await npyInfo(mapping.get(candidate));verts.add(shape[1]);if(Math.abs(shape[0]/fps-wav.duration)>Math.max(.12,2/fps))throw Error('音频 / 动画时长不一致；请核对配置中的 FPS');}else if(candidate.endsWith('.xml')&&!mapping.has(candidate.replace(/\.xml$/,'.mc')))throw Error('缺少配套 .mc 文件');else warnings.push(name+'：PC2 / MC 需在官方预处理阶段进一步验证');paired++;seconds+=wav.duration;if(wav.duration<3||wav.duration>30)warnings.push(name+'：建议片段长度 3–30 秒');}catch(err){errors.push(name+'：'+err.message);}}
  if(paired<5)errors.push('本工作台至少需要 5 个配对片段以留出验证集；这是工作台规则，不是官方最低数量。');if(verts.size>1)errors.push('片段之间的顶点数量不一致。');
  box.replaceChildren(element('strong',errors.length?'需要补齐 / 修正数据':'文件元数据检查通过',errors.length?'bad':'good'),element('p',`${audios.length} 段录音 · ${paired} 对有效文件 · ${seconds.toFixed(1)} 秒 · 按 ${fps} FPS 检查`));
  for(const s of errors.slice(0,10))box.append(element('p','× '+s,'bad'));for(const s of warnings.slice(0,5))box.append(element('p','提示：'+s));box.append(element('p','这里只检查文件配对与元数据，未逐点检查 NaN、拓扑顺序、头部稳定或音画同步。请在 DCC 中检查标注质量。数据尚未上传。'));
});
update();openTab(location.hash.slice(1)||'data');await refreshJobs();
try{const data=await(await request('data')).json();if(data.seconds)$('#sample-seconds').textContent=data.seconds.toFixed(2);}catch{}
setInterval(()=>{if(!document.hidden)refreshJobs();},5000);
