import {decodeDelta16} from './motion-codec.js';
// Each chunk holds 30 frames plus one overlapping frame for interpolation.
// Keep only a small window in memory; never load an entire 426 MB clip.
export class ChunkCache {
  constructor(demo, {stride=88831, chunkFrames=30, limit=4, encoding='float32', fetcher=(...args)=>fetch(...args)}={}) {
    Object.assign(this,{demo,stride,chunkFrames,limit,encoding,fetcher});
    this.ready=new Map();this.pending=new Map();this.disposed=false;
  }
  index(frame){return Math.min(this.demo.chunks.length-1,Math.floor(Math.max(0,frame)/this.chunkFrames));}
  get(index){const value=this.ready.get(index);if(value){this.ready.delete(index);this.ready.set(index,value);}return value;}
  focus(index){for(const [key,request] of this.pending){if(key!==index&&key!==index+1){request.controller.abort();this.pending.delete(key);}}}
  async load(index){
    if(this.disposed)throw new DOMException('Disposed','AbortError');
    if(index<0||index>=this.demo.chunks.length)return null;
    const cached=this.get(index);if(cached)return cached;
    if(this.pending.has(index))return this.pending.get(index).promise;
    const controller=new AbortController();
    const request={controller};
    request.promise=(async()=>{
      const response=await this.fetcher(this.demo.chunks[index],{signal:controller.signal});
      if(!response.ok)throw new Error(`动画块加载失败：HTTP ${response.status}`);
      const raw=await response.arrayBuffer();
      const buffer=this.encoding==='delta16-gzip-v1'?await decodeDelta16(raw,this.stride):raw;
      if(this.disposed||controller.signal.aborted)throw new DOMException('Aborted','AbortError');
      const count=Math.min(this.chunkFrames+1,this.demo.frameCount-index*this.chunkFrames);
      if(buffer.byteLength!==count*this.stride*4)throw new Error('动画块长度与帧数不匹配');
      const value=new Float32Array(buffer);this.ready.set(index,value);
      while(this.ready.size>this.limit)this.ready.delete(this.ready.keys().next().value);
      return value;
    })().finally(()=>{if(this.pending.get(index)===request)this.pending.delete(index);});
    this.pending.set(index,request);return request.promise;
  }
  dispose(){this.disposed=true;for(const r of this.pending.values())r.controller.abort();this.pending.clear();this.ready.clear();}
}
