// Contact landmarks for the pinned r180 Face Cap mesh (2694 vertices).
// Local +Z points down the face. Each pair follows the upper/lower inner lip.
const LIP_PAIRS = [
  [1434,1417], [1436,1416], [1448,1414], [1449,1413], [1451,1094],
  [1453,1095], [1462,1096], [1464,1098], [1466,1100], [1467,1841], [1469,1548],
];
// Preserve ordinary articulation; smoothly compress the extreme tail.
const softLimit = (value,knee,limit) => value<=knee ? value : knee+(limit-knee)*Math.tanh((value-knee)/(limit-knee));

export function createFaceCapRetargeter(mesh) {
  const {position} = mesh.geometry.attributes;
  const deltas = mesh.geometry.morphAttributes.position;
  const names = mesh.morphTargetDictionary;
  if (position.count !== 2694 || !mesh.geometry.morphTargetsRelative) {
    throw new Error('Face Cap 唇部校准与当前模型不匹配');
  }
  const jaw = names.jawOpen, close = names.mouthClose;
  const closing = ['mouthClose','mouthRollUpper','mouthRollLower','mouthShrugLower'].map(n=>names[n]);
  if ([jaw,close,...closing].some(i=>i===undefined)) throw new Error('Face Cap 缺少唇部校准通道');
  const contacts = LIP_PAIRS.map(([upper,lower])=>({
    neutral:position.getZ(lower)-position.getZ(upper),
    deltas:deltas.map(d=>d.getZ(lower)-d.getZ(upper)),
  }));
  // These four shapes monotonically close all measured lip contacts.
  if (contacts.some(c=>c.deltas[jaw]<=0 || closing.some(i=>c.deltas[i]>0))) {
    throw new Error('Face Cap 唇部形变方向与校准不匹配');
  }
  const closingSet = new Set(closing);
  const neutralWidth=position.getX(1538)-position.getX(1427);
  const widthDeltas=deltas.map(d=>d.getX(1538)-d.getX(1427));
  const widening=Object.entries(names).filter(([name,i])=>name.startsWith('mouth') && widthDeltas[i]>0).map(([,i])=>i);
  const wideningSet=new Set(widening);
  const mouthWidth=weights=>neutralWidth+widthDeltas.reduce((sum,d,i)=>sum+d*weights[i],0);
  const gap = (c,w,includeClosing=true)=>c.neutral+c.deltas.reduce(
    (sum,delta,i)=>sum+(includeClosing || !closingSet.has(i) ? delta*w[i] : 0),0);
  return {
    contacts,
    widthRatio:weights=>mouthWidth(weights)/neutralWidth,
    apply(weights) {
      weights[jaw]=softLimit(weights[jaw],.38,.68);
      // Face Cap's mouthClose cancels a fully open jaw; Claire emits it as
      // an independent closure signal. A direct copy can invert the lips.
      weights[close] *= Math.max(0,Math.min(1,weights[jaw]));
      // Smile, dimple, stretch and press can widen the mouth simultaneously.
      // Compress their combined geometric width, preserving left/right ratios.
      const width=mouthWidth(weights);
      const targetWidth=softLimit(width,neutralWidth*1.18,neutralWidth*1.32);
      const fixedWidth=neutralWidth+widthDeltas.reduce((sum,d,i)=>sum+(wideningSet.has(i)?0:d*weights[i]),0);
      const widthScale=width>targetWidth ? Math.max(0,(targetWidth-fixedWidth)/(width-fixedWidth)) : 1;
      for(const i of widening) weights[i]*=widthScale;
      // Preserve smile/frown/asymmetry. If their combination already crosses
      // the lips, add only the small jaw separation needed for contact.
      let jawCorrection=0;
      for (const c of contacts) jawCorrection=Math.max(jawCorrection,-gap(c,weights,false)/c.deltas[jaw]);
      weights[jaw]+=jawCorrection;
      // Limit simultaneous roll/shrug/close shapes by available lip space.
      // Evaluate every interpolated frame, not only integer CSV frames.
      let closureScale=1;
      for (const c of contacts) {
        const available=gap(c,weights,false);
        const displacement=closing.reduce((sum,i)=>sum+c.deltas[i]*weights[i],0);
        if (displacement<0) closureScale=Math.min(closureScale,Math.max(0,available/-displacement));
      }
      for (const i of closing) weights[i]*=closureScale;
      return {jawCorrection,closureScale,widthScale};
    },
    gaps:weights=>contacts.map(c=>gap(c,weights)),
  };
}
