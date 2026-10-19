// Keep the user's playback intent while model loading temporarily pauses audio.
export function createPlaybackController({audio,atEnd,rewind,onState,onError}) {
  let wanted=false,loading=false,request=0,load=0;
  const notify=()=>onState({wanted,loading});
  function pause() {wanted=false;request++;audio.pause();notify();}
  async function play() {
    wanted=true;notify();
    if(loading)return;
    const id=++request;
    if(atEnd())rewind();
    try {
      await audio.play();
      if(id===request)notify();
    } catch(error) {
      // A pause/seek/load can reject an earlier play promise with AbortError.
      if(id!==request)return;
      wanted=false;notify();onError(error);
    }
  }
  return {
    pause,play,
    toggle:()=>wanted?pause():play(),
    beginLoad() {loading=true;request++;audio.pause();notify();return ++load;},
    async endLoad(id,success=true) {
      if(id!==load)return;
      loading=false;
      if(!success){pause();return;}
      notify();
      if(wanted)await play();
    },
  };
}
