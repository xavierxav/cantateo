/**
 * AudioContextManager - Singleton for AudioContext
 */
const AudioContextManager = (function () {
  let audioContext = null;
  let isResumed = false;

  function getContext() {
    if (!audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) {
        console.warn('Web Audio API not supported');
        return null;
      }
      // 'interactive' hint → low latency. 
      // On iOS Safari, we must be careful with sampleRate. 
      // Most iOS devices run naturally at 48000Hz.
      const options = { latencyHint: 'interactive' };
      if (isIOS()) {
          options.sampleRate = 48000; 
      }
      audioContext = new AudioCtx(options);

      // Fix for WebKit bug 237322: ensures playback even when physical ringer switch is on silent
      if (window.navigator && window.navigator.audioSession) {
        window.navigator.audioSession.type = 'playback';
      }
    }
    return audioContext;
  }

  async function ensureResumed() {
    const ctx = getContext();
    if (!ctx) return false;

    if (ctx.state === 'suspended') {
      try {
        await ctx.resume();
        isResumed = true;
      } catch (e) {
        console.error('Failed to resume AudioContext:', e);
        return false;
      }
    }
    return true;
  }

  function getCurrentTime() {
    const ctx = getContext();
    return ctx ? ctx.currentTime : 0;
  }

  function isSupported() {
    return !!(window.AudioContext || window.webkitAudioContext);
  }

  /**
   * Détecte iOS/iPadOS. Sur iPadOS, navigator.platform vaut 'MacIntel'
   * mais maxTouchPoints > 1 trahit la tablette.
   */
  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  /**
   * Register an AudioWorklet module.
   * Ensures the module is only added once.
   */
  const registeredWorklets = new Set();
  async function registerWorklet(name, url) {
    const ctx = getContext();
    if (!ctx || !ctx.audioWorklet) return false;
    if (registeredWorklets.has(name)) return true;

    try {
      await ctx.audioWorklet.addModule(url);
      registeredWorklets.add(name);
      return true;
    } catch (e) {
      console.error(`Failed to register worklet ${name}:`, e);
      return false;
    }
  }

  return {
    getContext,
    ensureResumed,
    getCurrentTime,
    isSupported,
    isIOS,
    registerWorklet
  };
})();

window.AudioContextManager = AudioContextManager;
