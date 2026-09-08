/**
 * SyncedTrackPlayer - Coherent Multi-Track Engine.
 *
 * Uses a single AudioWorklet to mix all SATB tracks synchronously.
 * This ensures perfect phase-coherence and zero drift, especially on iOS.
 */
class SyncedTrackPlayer {
  constructor(chantId) {
    this.chantId = chantId;
    this.tracks = new Map();      // audioId -> {url, voiceType, audioElement, sourceNode, gainNode, volume, muted}
    this.buffers = new Map();     // voiceType -> AudioBuffer (for Safari 1.0x)
    this.bufferSources = [];      // Active buffer sources
    
    this.isPlaying = false;
    this.isPaused = false;
    this.duration = 0;
    
    this.playbackRate = 1.0;
    this.pauseOffset = 0;
    this.startTime = 0;
    
    this.onEndedCallback = null;
    this.progressCallback = null;
    this.animationFrameId = null;
    this.syncIntervalId = null;
    this.seekToken = 0;

    this.currentSoloTrack = null;
    this.isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
    this.trackOutputScale = 0.6;
    this.driftCorrectionThreshold = 0.3;
    this.driftCorrectionIntervalMs = 8000;
    
    this._initAudioGraph();
  }

  _initAudioGraph() {
    const ctx = AudioContextManager.getContext();
    this.masterGain = ctx.createGain();
    this.compressor = ctx.createDynamicsCompressor();
    this.masterGain.gain.value = 0.9;
    this.compressor.threshold.value = -6;
    this.compressor.knee.value = 12;
    this.compressor.ratio.value = 3;
    this.compressor.attack.value = 0.006;
    this.compressor.release.value = 0.18;
    this.masterGain.connect(this.compressor);
    this.compressor.connect(ctx.destination);
  }

  addTrack(audioId, url, voiceType) {
    const audio = new Audio(url);
    audio.crossOrigin = "anonymous";
    audio.load();

    const ctx = AudioContextManager.getContext();
    let sourceNode = null;
    // We only create MediaElementSource on non-Safari (PC stable mode)
    if (!this.isSafari) {
        try { sourceNode = ctx.createMediaElementSource(audio); } catch(e) {}
    }

    const gainNode = ctx.createGain();
    if (sourceNode) sourceNode.connect(gainNode);
    gainNode.connect(this.masterGain);

    this.tracks.set(String(audioId), {
      url,
      voiceType: voiceType || 'S',
      audioElement: audio,
      sourceNode,
      gainNode,
      volume: 1.0,
      muted: false
    });
  }

  isLoaded() {
    return this.tracks.size > 0;
  }

  // ─── Playback Logic ───────────────────────────────────────────────────────

  _shouldUseStandaloneNative() {
    // Safari speed change -> strictly standalone native (no Web Audio routing)
    return this.isSafari && Math.abs(this.playbackRate - 1.0) > 0.01;
  }

  async play() {
    const ctx = AudioContextManager.getContext();
    if (!ctx || !(await AudioContextManager.ensureResumed())) return false;
    if (this.isPlaying) return false;

    try {
      let started = false;
      if (this._shouldUseStandaloneNative()) {
        return this._playSafariNative();
      } else if (this.isSafari) {
        started = await this._playSafariBuffer();
      } else {
        started = await this._playPCMedia();
      }
      return started;
    } catch (e) { return false; }
  }

  async _playPCMedia() {
    await this._preparePCTracksForTime(this.pauseOffset, this.seekToken);
    const playPromises = [];
    this.tracks.forEach(track => {
        track.audioElement.playbackRate = this.playbackRate;
        playPromises.push(track.audioElement.play());
    });
    await Promise.all(playPromises);
    this.isPlaying = true;
    this.isPaused = false;
    this._startSyncInterval();
    this._startProgressUpdates();
    this._applyAllParameters();
    this._setupPCEnded();
    return true;
  }

  async _playSafariBuffer() {
    const ctx = AudioContextManager.getContext();
    await this.loadAllBuffers();
    
    const startTime = ctx.currentTime + 0.1;
    this.bufferSources = [];

    this.tracks.forEach((track, id) => {
        const buf = this.buffers.get(track.voiceType);
        if (!buf) return;

        const source = ctx.createBufferSource();
        source.buffer = buf;
        source.connect(track.gainNode);
        
        // Start from exactly where we are
        source.start(startTime, this.pauseOffset);
        this.bufferSources.push(source);
        
        if (id === Array.from(this.tracks.keys())[0]) {
            source.onended = () => this._onEnded();
        }
    });

    this.startTime = startTime;
    this.isPlaying = true;
    this.isPaused = false;
    this._startProgressUpdates();
    this._applyAllParameters();
    return true;
  }

  async _playSafariNative() {
    const fallbackVoiceType = this.tracks.size
      ? this.tracks.values().next().value.voiceType
      : 'S';
    const voiceType = this.currentSoloTrack || fallbackVoiceType;
    const track = Array.from(this.tracks.values()).find(t => t.voiceType === voiceType);
    if (!track) return false;

    // Disconnect from Web Audio to avoid Safari routing bugs during speed change
    if (track.sourceNode) track.sourceNode.disconnect();

    track.audioElement.playbackRate = this.playbackRate;
    track.audioElement.currentTime = this.pauseOffset;
    track.audioElement.preservesPitch = true;
    track.audioElement.webkitPreservesPitch = true;
    
    try {
        await track.audioElement.play();
        this.isPlaying = true;
        this.isPaused = false;
        this._startProgressUpdates();
        track.audioElement.onended = () => this._onEnded();
        return true;
    } catch (e) { return false; }
  }

  pause() {
    if (!this.isPlaying) return;
    this.pauseOffset = this.getCurrentTime();
    
    this.tracks.forEach(t => t.audioElement.pause());
    this._stopBufferSourcesManually();

    this.isPlaying = false;
    this.isPaused = true;
    this._stopSyncInterval();
    this._stopProgressUpdates();
    if (this.progressCallback) this.progressCallback(this.pauseOffset, this.getDuration());
  }

  stop() {
    this.pause();
    this.pauseOffset = 0;
    this.isPaused = false;
  }

  async seekTo(time) {
    const targetTime = Math.max(0, Math.min(time, this.getDuration()));
    this.pauseOffset = targetTime;
    const wasPlaying = this.isPlaying;
    const token = ++this.seekToken;

    if (this.isSafari) {
        if (this.progressCallback) this.progressCallback(targetTime, this.getDuration());
        if (!wasPlaying) return;

        this._stopBufferSourcesManually();
        this.tracks.forEach(t => {
            try {
                t.audioElement.pause();
                t.audioElement.currentTime = targetTime;
            } catch(e) {}
        });
        this.isPlaying = false;
        this.isPaused = true;
        this._stopProgressUpdates();
        await this.play();
        return;
    }

    if (!wasPlaying) {
        await this._preparePCTracksForTime(targetTime, token);
        if (this.progressCallback) this.progressCallback(targetTime, this.getDuration());
        return;
    }

    this.tracks.forEach(t => t.audioElement.pause());
    this._stopBufferSourcesManually();
    this.isPlaying = false;
    this.isPaused = true;
    this._stopSyncInterval();
    this._stopProgressUpdates();

    try {
        await this._preparePCTracksForTime(targetTime, token);
        if (token !== this.seekToken) return;
        const playPromises = [];
        this.tracks.forEach(track => {
            track.audioElement.playbackRate = this.playbackRate;
            playPromises.push(track.audioElement.play());
        });
        await Promise.all(playPromises);
        if (token !== this.seekToken) return;
        this.isPlaying = true;
        this.isPaused = false;
        this._startSyncInterval();
        this._startProgressUpdates();
        this._applyAllParameters();
        this._setupPCEnded();
        this._forcePCSync(targetTime);
        this._startTemporaryTightSync();
    } catch (e) { return; }
  }

  // ─── Sync & State ─────────────────────────────────────────────────────────

  async loadAll() {
    if (!this.isSafari) {
      this.tracks.forEach(track => track.audioElement.load());
      return Promise.resolve();
    }
    return this.loadAllBuffers();
  }

  async loadAllBuffers() {
    const ctx = AudioContextManager.getContext();
    const promises = Array.from(this.tracks.values()).map(async track => {
      // Pre-load for MediaElement (PC)
      track.audioElement.load();
      
      // Load for Buffer (Safari 1.0x)
      if (this.buffers.has(track.voiceType)) return;
      try {
        const response = await fetch(track.url);
        const arrayBuffer = await response.arrayBuffer();
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
        this.buffers.set(track.voiceType, audioBuffer);
        this.duration = Math.max(this.duration, audioBuffer.duration);
      } catch (e) {}
    });
    return Promise.all(promises);
  }

  async prefetchTrack(audioId) {
    const track = this.tracks.get(String(audioId));
    if (track) track.audioElement.load();
  }

  setPlaybackRate(rate) {
    const oldRate = this.playbackRate;
    this.playbackRate = Math.max(0.4, Math.min(2.0, rate));
    
    if (this.isSafari && this.isPlaying) {
        // Toggle engine if switching between 1.0 and stretched
        if ((Math.abs(oldRate - 1.0) < 0.01 && Math.abs(rate - 1.0) > 0.01) ||
            (Math.abs(oldRate - 1.0) > 0.01 && Math.abs(rate - 1.0) < 0.01)) {
            this.pause();
            this.play();
            return;
        }
    }

    this.tracks.forEach(track => {
        track.audioElement.playbackRate = this.playbackRate;
    });
  }

  _applyAllParameters() {
    const ctx = AudioContextManager.getContext();
    const now = ctx.currentTime;
    this.tracks.forEach((track, id) => {
        let vol = track.muted ? 0 : track.volume;
        if (this.currentSoloTrack && id !== this.currentSoloTrack) vol = 0;
        track.gainNode.gain.setTargetAtTime(vol * this.trackOutputScale, now, 0.02);
    });
  }

  getCurrentTime() {
    if (!this.isPlaying) return this.pauseOffset;
    if (this._shouldUseStandaloneNative()) {
        const vt = this.currentSoloTrack || 'S';
        const t = Array.from(this.tracks.values()).find(tr => tr.voiceType === vt);
        return t ? t.audioElement.currentTime : this.pauseOffset;
    }
    if (this.isSafari) {
        return Math.min(this.duration, this.pauseOffset + (AudioContextManager.getContext().currentTime - this.startTime));
    }
    // PC MediaElement fallback
    return Array.from(this.tracks.values())[0].audioElement.currentTime;
  }

  getDuration() {
    if (this.duration) return this.duration;
    let bestDuration = 0;
    this.tracks.forEach(track => {
        const duration = track.audioElement.duration;
        if (Number.isFinite(duration) && duration > bestDuration) {
            bestDuration = duration;
        }
    });
    if (bestDuration > 0) {
        this.duration = bestDuration;
        return bestDuration;
    }
    return 0;
  }

  toggleSolo(audioId) {
    const id = String(audioId);
    const oldSolo = this.currentSoloTrack;
    this.currentSoloTrack = (this.currentSoloTrack === id) ? null : id;
    
    if (this.isPlaying && this._shouldUseStandaloneNative() && oldSolo !== this.currentSoloTrack) {
        this.pause();
        this.play();
    }
    this._applyAllParameters();
    return !!this.currentSoloTrack;
  }

  mute(audioId) {
    const t = this.tracks.get(String(audioId));
    if (t) { t.muted = true; this._applyAllParameters(); }
  }

  unmute(audioId) {
    const t = this.tracks.get(String(audioId));
    if (t) { t.muted = false; this._applyAllParameters(); }
  }

  isMuted(audioId) {
    const track = this.tracks.get(String(audioId));
    return track ? track.muted : false;
  }
  getSoloTrack() { return this.currentSoloTrack; }
  getVolume(audioId) {
    const track = this.tracks.get(String(audioId));
    return track ? track.volume : 1;
  }
  setVolume(audioId, v) { 
    const t = this.tracks.get(String(audioId));
    if (t) { t.volume = v; this._applyAllParameters(); }
  }

  // ─── PC Sync Helpers ──────────────────────────────────────────────────────

  _stopBufferSourcesManually() {
    this.bufferSources.forEach(source => {
        try {
            source.onended = null;
            source.stop();
        } catch(e) {}
    });
    this.bufferSources = [];
  }

  async _preparePCTracksForTime(time, token) {
    const tracks = Array.from(this.tracks.values());
    await Promise.all(tracks.map(track => this._seekPCTrack(track, time, token)));
    if (token !== this.seekToken) return;
    this._forcePCSync(time);
  }

  _seekPCTrack(track, time, token) {
    return new Promise(resolve => {
        const audio = track.audioElement;
        let done = false;
        const cleanup = () => {
            audio.removeEventListener('seeked', onReady);
            audio.removeEventListener('canplay', onReady);
            audio.removeEventListener('canplaythrough', onReady);
            audio.removeEventListener('loadedmetadata', onReady);
            clearTimeout(timeoutId);
        };
        const finish = () => {
            if (done) return;
            done = true;
            cleanup();
            resolve();
        };
        const onReady = () => {
            if (token !== this.seekToken) {
                finish();
                return;
            }
            if (audio.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA || Math.abs(audio.currentTime - time) < 0.05) {
                finish();
            }
        };
        const timeoutId = setTimeout(finish, 4500);
        audio.addEventListener('seeked', onReady);
        audio.addEventListener('canplay', onReady);
        audio.addEventListener('canplaythrough', onReady);
        audio.addEventListener('loadedmetadata', onReady);
        audio.preload = 'auto';
        try {
            audio.currentTime = time;
        } catch(e) {}
        if (audio.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA && Math.abs(audio.currentTime - time) < 0.05) {
            finish();
        }
    });
  }

  _startSyncInterval() {
    this._stopSyncInterval();
    this.syncIntervalId = setInterval(() => {
        if (!this.isPlaying || this.isSafari) return;
        const arr = Array.from(this.tracks.values());
        const ref = arr[0].audioElement.currentTime;
        arr.slice(1).forEach(t => {
            if (Math.abs(t.audioElement.currentTime - ref) > this.driftCorrectionThreshold) {
                this._smoothResyncTrack(t, ref);
            }
        });
    }, this.driftCorrectionIntervalMs);
  }

  _stopSyncInterval() { if (this.syncIntervalId) clearInterval(this.syncIntervalId); }

  _forcePCSync(time) {
    if (this.isSafari) return;
    this.tracks.forEach(track => {
        if (Math.abs(track.audioElement.currentTime - time) > 0.03) {
            try { track.audioElement.currentTime = time; } catch(e) {}
        }
    });
  }

  _startTemporaryTightSync() {
    if (this.isSafari) return;
    let checks = 0;
    const intervalId = setInterval(() => {
        if (!this.isPlaying || checks >= 12) {
            clearInterval(intervalId);
            return;
        }
        checks += 1;
        const arr = Array.from(this.tracks.values());
        if (!arr.length) return;
        const ref = arr[0].audioElement.currentTime;
        arr.slice(1).forEach(track => {
            if (Math.abs(track.audioElement.currentTime - ref) > 0.08) {
                this._smoothResyncTrack(track, ref);
            }
        });
    }, 300);
  }

  _smoothResyncTrack(track, time) {
    const ctx = AudioContextManager.getContext();
    const now = ctx.currentTime;
    const currentGain = track.gainNode.gain.value;
    track.gainNode.gain.cancelScheduledValues(now);
    track.gainNode.gain.setValueAtTime(currentGain, now);
    track.gainNode.gain.linearRampToValueAtTime(0, now + 0.025);

    setTimeout(() => {
        if (!this.isPlaying || this.isSafari) return;
        track.audioElement.currentTime = time;
        this._applyAllParameters();
    }, 30);
  }

  _setupPCEnded() {
    const first = Array.from(this.tracks.values())[0];
    if (first) first.audioElement.onended = () => this._onEnded();
  }

  _onEnded() {
    this.pause();
    this.pauseOffset = 0;
    if (this.onEndedCallback) this.onEndedCallback();
  }

  _startProgressUpdates() {
    const update = () => {
      if (!this.isPlaying) return;
      if (this.progressCallback) this.progressCallback(this.getCurrentTime(), this.getDuration());
      this.animationFrameId = requestAnimationFrame(update);
    };
    update();
  }

  _stopProgressUpdates() { if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId); }

  destroy() {
    this.stop();
    this.tracks.forEach(t => { t.audioElement.src = ''; t.gainNode.disconnect(); });
    this.tracks.clear();
    this.buffers.clear();
  }

  onProgress(cb) { this.progressCallback = cb; }
  onEnded(cb) { this.onEndedCallback = cb; }
}

window.SyncedTrackPlayer = SyncedTrackPlayer;
