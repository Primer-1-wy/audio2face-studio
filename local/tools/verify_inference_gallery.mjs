import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {ChunkCache} from '../viewer/inference/chunk-cache.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const manifest=JSON.parse(await fs.readFile(root+'demo-data/v3-20s-01-05/web/manifest.json','utf8'));
assert.equal(manifest.demos.length,5);
for(const demo of manifest.demos){
  const fetcher=async url=>({ok:true,arrayBuffer:async()=>{const b=await fs.readFile(root+url.slice(1));return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}});
  const cache=new ChunkCache(demo,{fetcher});
  // Boundary continuity, final frame, random seeking and bounded memory.
  const first=await cache.load(0),second=await cache.load(1),stride=manifest.stride;
  assert.deepEqual(first.subarray(30*stride,31*stride),second.subarray(0,stride));
  assert.equal(await cache.load(1),second);
  for(const index of [39,17,5,29,0])await cache.load(index);
  assert.equal(cache.ready.size,4);
  assert.equal((await cache.load(39)).length,30*stride);
  const frame=new Float32Array((await cache.load(17)).subarray(0,stride));
  assert(frame.every(Number.isFinite));
  cache.dispose();assert.equal(cache.ready.size,0);
  await assert.rejects(cache.load(0),{name:'AbortError'});
  console.log('PASS',demo.id,'overlap, last frame, random seek, LRU limit');
}
const shortDemo={chunks:['0','1','2'],frameCount:3};
const malformed=new ChunkCache(shortDemo,{stride:1,chunkFrames:1,fetcher:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(1)})});
await assert.rejects(malformed.load(0),/长度/);
let calls=0;
const blocked=new ChunkCache(shortDemo,{stride:1,chunkFrames:1,fetcher:(_url,{signal})=>{calls++;return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));}});
const p=blocked.load(0),p2=blocked.load(0);
assert.equal(calls,1);blocked.focus(2);
await assert.rejects(p,{name:'AbortError'});await assert.rejects(p2,{name:'AbortError'});
assert.equal(blocked.pending.size,0);blocked.dispose();
console.log('PASS malformed buffers, deduplicated requests and seek cancellation');
