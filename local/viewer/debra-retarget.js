// Hand-authored semantic mapping to Debra's own Reallusion shapes.
// This is a preview retarget, not NVIDIA's OmniGraph character-transfer solver.
export const DEBRA_RULES={
  Eye_Blink_L:[['eyeBlinkLeft',1]],Eye_Blink_R:[['eyeBlinkRight',1]],
  Eye_Wide_L:[['eyeWideLeft',.8]],Eye_Wide_R:[['eyeWideRight',.8]],
  Eye_Squint_L:[['eyeSquintLeft',.55]],Eye_Squint_R:[['eyeSquintRight',.55]],
  Brow_Drop_Left:[['browDownLeft',.8]],Brow_Drop_Right:[['browDownRight',.8]],
  Brow_Raise_Inner_Left:[['browInnerUp',.8]],Brow_Raise_Inner_Right:[['browInnerUp',.8]],
  Brow_Raise_Outer_Left:[['browOuterUpLeft',.8]],Brow_Raise_Outer_Right:[['browOuterUpRight',.8]],
  Cheek_Blow_L:[['cheekPuff',.8]],Cheek_Blow_R:[['cheekPuff',.8]],
  Cheek_Raise_L:[['cheekSquintLeft',.6]],Cheek_Raise_R:[['cheekSquintRight',.6]],
  Nose_Flank_Raise_L:[['noseSneerLeft',.8]],Nose_Flank_Raise_R:[['noseSneerRight',.8]],
  Mouth_Smile_L:[['mouthSmileLeft',.72]],Mouth_Smile_R:[['mouthSmileRight',.72]],
  Mouth_Frown_L:[['mouthFrownLeft',.7]],Mouth_Frown_R:[['mouthFrownRight',.7]],
  Mouth_Dimple_L:[['mouthDimpleLeft',.65]],Mouth_Dimple_R:[['mouthDimpleRight',.65]],
  Mouth_Pucker:[['mouthPucker',.65]],Mouth_Pucker_Open:[['mouthFunnel',.65]],
  Mouth_L:[['mouthLeft',.8],['jawLeft',.3]],Mouth_R:[['mouthRight',.8],['jawRight',.3]],
  Mouth_Widen:[['mouthStretchLeft',.3],['mouthStretchRight',.3]],
  Mouth_Top_Lip_Under:[['mouthRollUpper',.65]],Mouth_Bottom_Lip_Under:[['mouthRollLower',.65]],
  Mouth_Up:[['mouthShrugLower',.25]],Mouth_Top_Lip_Up:[['mouthShrugUpper',.3]],
  Mouth_Lips_Tight:[['mouthPressLeft',.25],['mouthPressRight',.25]],
  Mouth_Snarl_Lower_L:[['mouthLowerDownLeft',.65]],Mouth_Snarl_Lower_R:[['mouthLowerDownRight',.65]],
  Mouth_Snarl_Upper_L:[['mouthUpperUpLeft',.65]],Mouth_Snarl_Upper_R:[['mouthUpperUpRight',.65]],
  V_Tongue_Out:[['tongueOut',.7]],V_Tongue_Raise:[['tongueTipUp',.65]],
  V_Tongue_Lower:[['tongueTipDown',.35],['tongueDown',.35]],
  V_Tongue_up:[['tongueUp',.65]],V_Tongue_Narrow:[['tongueNarrow',.65]],
  V_Tongue_Curl_U:[['tongueRollUp',.65]],V_Tongue_Curl_D:[['tongueRollDown',.65]],
};
export const DEBRA_EYE_CHANNELS=['eyeLookUpLeft','eyeLookDownLeft','eyeLookInLeft','eyeLookOutLeft','eyeLookUpRight','eyeLookDownRight','eyeLookInRight','eyeLookOutRight'];
export const debraMappedChannels=[...new Set([...Object.values(DEBRA_RULES).flat().map(r=>r[0]),...DEBRA_EYE_CHANNELS,'jawOpen','mouthClose'])];
const clamp=x=>Math.max(0,Math.min(1,x));
export function debraWeights(names,channels,values) {
  const get=n=>{const i=channels.indexOf(n);return i<0?0:clamp(values[i]);};
  const jaw=get('jawOpen')*.76*(1-.55*get('mouthClose'));
  return names.map(name=>{
    if(name==='Jaw_Open')return jaw;
    if(name==='TeethMerged_Open_Mouth'||name==='TongueMerged_Open_Mouth')return jaw*1.25;
    let v=(DEBRA_RULES[name]||[]).reduce((sum,[n,gain])=>sum+get(n)*gain,0);
    if(name==='Eye_Squint_L')v*=1-get('eyeBlinkLeft');
    if(name==='Eye_Squint_R')v*=1-get('eyeBlinkRight');
    if(name==='Eye_Wide_L')v*=1-get('eyeBlinkLeft');
    if(name==='Eye_Wide_R')v*=1-get('eyeBlinkRight');
    // Rolling and pressing lips while the jaw is closed can push the opposing
    // lip surfaces through each other. Keep those secondary poses modest.
    if(['Mouth_Lips_Tight','Mouth_Top_Lip_Under','Mouth_Bottom_Lip_Under'].includes(name))v*=.35+.65*Math.min(1,jaw*2);
    return clamp(v);
  });
}
