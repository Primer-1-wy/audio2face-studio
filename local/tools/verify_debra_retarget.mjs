import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {debraWeights,DEBRA_RULES,debraMappedChannels,DEBRA_EYE_CHANNELS} from '../viewer/debra-retarget.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const data=JSON.parse(fs.readFileSync(path.join(root,'viewer/data.json')));
const scene=JSON.parse(fs.readFileSync(path.join(root,'viewer/official-debra/scene.json')));
const native=new Set(scene.parts.flatMap(p=>p.morphNames));
for(const target of Object.keys(DEBRA_RULES))assert(native.has(target),`Missing native shape: ${target}`);
const names=[...native],channels=data.blendshapes.names,rows=data.blendshapes.values;
assert(debraWeights(names,channels,new Array(channels.length).fill(0)).every(v=>v===0),'Neutral must stay neutral');
for(const channel of debraMappedChannels) {
  assert(channels.includes(channel));if(DEBRA_EYE_CHANNELS.includes(channel))continue;
  const neutral=new Array(channels.length).fill(0);neutral[channels.indexOf('jawOpen')]=.5;
  const altered=neutral.slice();altered[channels.indexOf(channel)]=1;
  assert.notDeepEqual(debraWeights(names,channels,neutral),debraWeights(names,channels,altered),`Inactive mapping: ${channel}`);
}
let samples=0,max=0;const baked={};
for(const spec of scene.parts){
  const weights=[];
  for(let frame=0;frame<rows.length;frame++)weights.push(debraWeights(spec.morphNames,channels,rows[frame]));
  baked[spec.name]=weights;
}
for(let i=0;i<rows.length;i++)for(const f of i===rows.length-1?[0]:[0,.25,.5,.75]) {
  const input=rows[i].map((v,k)=>v*(1-f)+rows[Math.min(i+1,rows.length-1)][k]*f);
  const weights=debraWeights(names,channels,input);assert(weights.every(v=>Number.isFinite(v)&&v>=0&&v<=1));max=Math.max(max,...weights);samples++;
}
const manifest=JSON.parse(fs.readFileSync(path.join(root,'assets/debra-official/manifest.json')));
for(const f of manifest.files)assert.equal(fs.statSync(path.join(root,'assets/debra-official',f.path)).size,f.bytes);
const report={status:'PASS',sourceFiles:manifest.files.length,sourceBytes:manifest.files.reduce((n,f)=>n+f.bytes,0),frames:rows.length,interpolatedSamples:samples,mappedChannels:debraMappedChannels.length,unmappedChannels:channels.filter(n=>!debraMappedChannels.includes(n)),maxNativeWeight:max,neutralPreserved:true,allRulesReferenceExistingNativeShapes:true};
fs.writeFileSync(path.join(root,'verification-debra-retarget.json'),JSON.stringify(report,null,2));
if(process.argv.includes('--export-weights'))fs.writeFileSync(path.join(root,'verification-debra-weights.json'),JSON.stringify(baked));
console.log(JSON.stringify(report,null,2));
