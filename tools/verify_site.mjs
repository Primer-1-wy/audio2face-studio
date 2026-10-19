import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {decodeDelta16} from '../docs/motion-codec.js';
import {ChunkCache} from '../docs/chunk-cache.js';

const site=fileURLToPath(new URL('../docs/',import.meta.url));
const read=async url=>{assert(!url.startsWith('/'),'Assets must work below a project subpath');const resolved=path.resolve(site,url);assert(resolved.startsWith(site));return fs.readFile(resolved);};
const json=async url=>JSON.parse(await read(url));
const manifest=await json('data/manifest.json');
assert.equal(manifest.encoding,'delta16-gzip-v1');assert.equal(manifest.demos.length,5);
const fetcher=async url=>({ok:true,arrayBuffer:async()=>{const b=await read(url);return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}});
for(const demo of manifest.demos){
  assert.equal(demo.fps,60);assert.equal(demo.frameCount,1200);assert.equal(demo.chunks.length,40);
  for(const url of [demo.audio,demo.video,demo.jaw,demo.details,...Object.values(demo.downloads),...demo.chunks])await fs.access(path.join(site,url));
  const cache=new ChunkCache(demo,{stride:manifest.stride,chunkFrames:manifest.chunkFrames,encoding:manifest.encoding,fetcher});
  const a=await cache.load(0),b=await cache.load(1);
  assert.deepEqual(a.subarray(30*manifest.stride,31*manifest.stride),b.subarray(0,manifest.stride));
  const last=await cache.load(39);assert.equal(last.length,30*manifest.stride);assert(last.every(Number.isFinite));
  for(const index of [20,3,17])await cache.load(index);assert.equal(cache.ready.size,4);cache.dispose();
  const detail=await json(demo.details);assert.equal(detail.emotion.length,1200);
  console.log('PASS',demo.id,'decode / overlapping frames / end / LRU / relative assets');
}
const scene=await json(manifest.scene);
for(const spec of [...Object.values(scene.canonical),...scene.parts])for(const key of ['base','uv','indices','sourceVertices','map','normalMap','roughnessMap'])if(spec[key])await read(spec[key]);
await assert.rejects(decodeDelta16(new ArrayBuffer(3)),/长度/);
const raw=new Int16Array([1,2,3,4,5, 1,-1,2,-2,0]);
const decoded=new Float32Array(await decodeDelta16(raw.buffer,5));
assert(Math.abs(decoded[0]-.001)<1e-8);assert(Math.abs(decoded[5]-.002)<1e-8);assert(Math.abs(decoded[6]-.01)<1e-8);
const html=await fs.readFile(path.join(site,'index.html'),'utf8');
assert(!html.includes('/demo-data/'));assert(!html.includes('127.0.0.1'));assert(html.includes('training.html'));
let total=0;
async function walk(folder){for(const item of await fs.readdir(folder,{withFileTypes:true})){const p=path.join(folder,item.name);if(item.isDirectory())await walk(p);else{const stat=await fs.stat(p);total+=stat.size;assert(stat.size<25*1024*1024,`Large site file: ${p}`);}}}
await walk(site);assert(total<1e9,'Site exceeds GitHub Pages size limit');
console.log('PASS site assets, malformed codec, all five clips, Pages size:',Math.round(total/1e6),'MB');
