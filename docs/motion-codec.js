// delta16-gzip-v1: little-endian signed int16 differences, frame-major.
// Geometry step .001 cm; the last four eye channels use .01 degrees.
export async function decodeDelta16(input,stride=88831){
  const bytes=new Uint8Array(input);
  let buffer=input;
  if(bytes[0]===0x1f&&bytes[1]===0x8b){
    if(typeof DecompressionStream==='undefined')throw new Error('当前浏览器不支持动画解压，请使用新版 Chrome、Edge、Safari 或 Firefox。');
    buffer=await new Response(new Blob([input]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  }
  if(!buffer.byteLength||buffer.byteLength%(stride*2)!==0)throw new Error('压缩动画块长度无效');
  const encoded=new DataView(buffer),out=new Float32Array(buffer.byteLength/2),previous=new Int32Array(stride);
  for(let offset=0;offset<out.length;offset+=stride){
    for(let c=0;c<stride;c++){
      const value=previous[c]+encoded.getInt16((offset+c)*2,true);
      if(value<-32768||value>32767)throw new Error('压缩动画值越界');
      previous[c]=value;out[offset+c]=value*(c>=stride-4?.01:.001);
    }
  }
  return out.buffer;
}
