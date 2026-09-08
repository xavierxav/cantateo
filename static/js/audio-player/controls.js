/**
 * Multi-track Audio Player Controls
 * 
 * Acts as a bridge between the UI (AudioUI), the Polling system (AudioPolling),
 * and the playback engines (Web Audio Sync or Legacy HTML5).
 */

// ============================================
// Configuration & State
// ============================================
const USE_WEB_AUDIO = typeof WebAudioPlayerManager !== 'undefined' && WebAudioPlayerManager.isSupported();

// Legacy state for HTML5 fallback
const playerState = {};
const previousVolumes = {};
const manualMutes = {};
let currentSoloTrack = null;
let sessionPreloadAttempted = false;
const activeTempoVariantPollers = new Map();
const pendingAppleTempoStates = new Map();

// Browser detection
const isSafariOS = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
const isIOSLike = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const USE_APPLE_TEMPO_VARIANTS = isSafariOS || isIOSLike;
const APPLE_TEMPO_VALUES = ['0.5', '1.0', '1.5'];

function getVoiceType(voice) {
  if (!voice) return '';
  return voice.voice_type || voice.type_voix || '';
}

function getVoiceLabelForAudio(audioId) {
  const wrapper = document.querySelector(`[data-audio-id="${audioId}"]`);
  return wrapper ? wrapper.dataset.voiceLabel : 'la piste';
}

function disableUnsupportedAudioControls(chantId) {
  const unsupported = document.getElementById(`audio-unsupported-${chantId}`);
  if (unsupported) unsupported.classList.remove('d-none');

  const root = document.getElementById(`draggable-player-${chantId}`);
  if (!root) return;

  const controls = [
    `#play-pause-btn-${chantId}`,
    `#advanced-toggle-${chantId}`,
    `#progress-bar-${chantId}`,
    `#speed-slider-${chantId}`
  ];

  controls.forEach(selector => {
    const el = root.querySelector(selector);
    if (el) {
      el.disabled = true;
      el.setAttribute('aria-disabled', 'true');
    }
  });

  root.querySelectorAll('.solo-btn, .mute-btn, .volume-slider').forEach(el => {
    el.disabled = true;
    el.setAttribute('aria-disabled', 'true');
  });

  root.querySelectorAll(`#apple-speed-controls-${chantId} [data-audio-action="speed"]`).forEach(el => {
    el.disabled = true;
    el.setAttribute('aria-disabled', 'true');
  });
}

// ============================================
// Player Initialization
// ============================================

/**
 * Initialize player for a chant
 */
function initializePlayer(chantId) {
  chantId = String(chantId);
  if (USE_WEB_AUDIO) {
    initializeWebAudioPlayer(chantId);
  } else {
    initializeLegacyPlayer(chantId);
    disableUnsupportedAudioControls(chantId);
  }
}

/**
 * Initialize Web Audio API player
 */
function initializeWebAudioPlayer(chantId) {
  const player = WebAudioPlayerManager.getPlayer(chantId);
  const container = document.getElementById('audio-container-' + chantId);
  if (!container) return;
  
  // Extract tracks from DOM
  container.querySelectorAll('div[id^="audio-"]').forEach(div => {
    const audioId = div.id.replace('audio-', '');
    const url = div.dataset.src;
    if (url && !player.tracks.has(audioId)) {
      player.addTrack(audioId, url, div.dataset.voiceType || div.dataset.voice_type);
      previousVolumes[audioId] = 1;
    }
  });

  configureAppleTempoControls(chantId);

  // Wire up UI updates
  if (!player.__cantateoCallbacksBound) {
    player.onProgress((currentTime, duration) => {
      AudioUI.updateProgressUI(chantId, currentTime, duration);
    });

    player.onEnded(() => onPlaybackEnded(chantId));
    player.__cantateoCallbacksBound = true;
  }

  // Sync initial duration
  if (player.isLoaded() && player.getDuration() > 0) {
    AudioUI.updateProgressUI(chantId, 0, player.getDuration());
  }


  // Background Preloading: only for the first page with audio in a session to save data.
  if (!sessionPreloadAttempted && !sessionStorage.getItem('cantateo_audio_preloaded')) {
    sessionStorage.setItem('cantateo_audio_preloaded', 'true');
    sessionPreloadAttempted = true;
    
    // Slight delay to prioritize UI rendering before CPU-intensive decoding
    setTimeout(() => {
      player.loadAll().catch(e => console.warn('[AudioEngine] Background preload failed:', e));
    }, 200);
  }
}

/**
 * Initialize legacy HTML5 player
 */
function initializeLegacyPlayer(chantId) {
  if (!playerState[chantId]) {
    playerState[chantId] = { isPlaying: false, duration: 0, currentTime: 0, playbackRate: 1.0 };
  }
}

// ============================================
// Playback Controls
// ============================================

/**
 * Toggle play/pause (Bridge)
 */
async function togglePlayPause(chantId) {
  chantId = String(chantId);
  if (!USE_WEB_AUDIO) {
    disableUnsupportedAudioControls(chantId);
    return;
  }
  if (USE_WEB_AUDIO) {
    await togglePlayPauseWebAudio(chantId);
  }
}

async function togglePlayPauseWebAudio(chantId) {
  initializePlayer(chantId);
  const player = WebAudioPlayerManager.getPlayer(chantId);
  const playBtn = document.getElementById('play-pause-btn-' + chantId);

  if (!player.isPlaying) {
    if (playBtn) playBtn.disabled = true;
    try {
      if (await player.play()) {
        AudioUI.updatePlayPauseIcons(chantId, true);
      }
    } catch (e) {
      console.error('Playback error:', e);
      // Restore play icon on error
      AudioUI.updatePlayPauseIcons(chantId, false);
    }
    if (playBtn) {
        playBtn.disabled = false;
        playBtn.setAttribute('aria-disabled', 'false');
    }
  } else {
    player.pause();
    AudioUI.updateProgressUI(chantId, player.getCurrentTime(), player.getDuration());
    AudioUI.updatePlayPauseIcons(chantId, false);
  }
}

function togglePlayPauseLegacy(chantId) {
  disableUnsupportedAudioControls(chantId);
}

function onPlaybackEnded(chantId) {
  AudioUI.updatePlayPauseIcons(chantId, false);
  AudioUI.updateProgressUI(chantId, 0, 0);
  if (playerState[chantId]) playerState[chantId].isPlaying = false;
}

/**
 * Legacy progress loop
 */
function updateProgressLegacy(chantId) {
  const state = playerState[chantId];
  if (!state || !state.isPlaying) return;

  const first = document.querySelector(`#audio-container-${chantId} audio`);
  if (!first) return;

  state.currentTime = first.currentTime;
  if (first.duration) state.duration = first.duration;

  AudioUI.updateProgressUI(chantId, state.currentTime, state.duration);

  if (first.ended) {
    onPlaybackEnded(chantId);
    return;
  }
  requestAnimationFrame(() => updateProgressLegacy(chantId));
}

function updateProgressIndicatorState(chantId, progress) {
  const bar = document.getElementById(`progress-bar-${chantId}`);
  if (!bar) return;
  const numeric = Number(progress);
  if (!Number.isFinite(numeric)) return;
  bar.value = numeric;
  bar.setAttribute('aria-valuenow', String(Math.round(numeric)));
  bar.setAttribute('aria-valuetext', `${Math.round(numeric)} pour cent`);
}

function seekTo(chantId, progress) {
  chantId = String(chantId);
  if (!USE_WEB_AUDIO) return;

  const player = WebAudioPlayerManager.getPlayer(chantId);
  player.seekTo((progress / 100) * player.getDuration())
    .then(() => AudioUI.updatePlayPauseIcons(chantId, player.isPlaying))
    .catch(error => {
      console.error('Seek error:', error);
      AudioUI.updatePlayPauseIcons(chantId, player.isPlaying);
    });
}

/**
 * Update playback speed (vitesse)
 */
function setPlaybackSpeed(chantId, rate) {
  chantId = String(chantId);
  rate = parseFloat(rate);
  
  if (!USE_WEB_AUDIO) {
    return;
  }

  if (USE_APPLE_TEMPO_VARIANTS) {
    requestAppleTempoVariant(chantId, rate);
    return;
  }

  const player = WebAudioPlayerManager.getPlayer(chantId);
  player.setPlaybackRate(rate);
}

/**
 * Apple/Safari uses server-generated tempo variants instead of playbackRate.
 */
function configureAppleTempoControls(chantId) {
  const sliderShell = document.getElementById(`speed-slider-shell-${chantId}`);
  const slider = document.getElementById(`speed-slider-${chantId}`);
  const appleControls = document.getElementById(`apple-speed-controls-${chantId}`);
  const root = document.getElementById(`draggable-player-${chantId}`);

  if (sliderShell) sliderShell.classList.toggle('d-none', USE_APPLE_TEMPO_VARIANTS);
  if (appleControls) appleControls.classList.toggle('d-none', !USE_APPLE_TEMPO_VARIANTS);

  if (USE_APPLE_TEMPO_VARIANTS) {
    if (slider) slider.value = '1.0';
    if (root && !root.dataset.currentAppleTempo) {
      root.dataset.currentAppleTempo = '1.0';
    }
    AudioUI.updateSpeedDisplay(chantId, root ? root.dataset.currentAppleTempo : '1.0');
    setTempoStatus(chantId, '');
    return;
  }

  if (slider) {
    slider.value = slider.value || '1.0';
  }
  AudioUI.updateSpeedDisplay(chantId, slider ? slider.value : '1.0');
}

function normalizeAppleTempo(rate) {
  const numeric = Number(rate);
  if (numeric <= 0.75) return '0.5';
  if (numeric >= 1.25) return '1.5';
  return '1.0';
}

async function requestAppleTempoVariant(chantId, rate) {
  chantId = String(chantId);
  const tempo = normalizeAppleTempo(rate);
  AudioUI.updateSpeedDisplay(chantId, tempo);

  const root = document.getElementById(`draggable-player-${chantId}`);
  if (root && root.dataset.currentAppleTempo === tempo) return;

  if (activeTempoVariantPollers.has(chantId)) {
    clearTimeout(activeTempoVariantPollers.get(chantId));
    activeTempoVariantPollers.delete(chantId);
  }
  pendingAppleTempoStates.delete(chantId);

  await loadAppleTempoVariant(chantId, tempo);
}

async function loadAppleTempoVariant(chantId, tempo) {
  const player = WebAudioPlayerManager.getPlayer(chantId);
  let pendingState = pendingAppleTempoStates.get(chantId);

  if (!pendingState) {
    const duration = player.getDuration();
    const currentTime = player.getCurrentTime();
    pendingState = {
      shouldResume: player.isPlaying,
      progressRatio: duration > 0 ? Math.max(0, Math.min(1, currentTime / duration)) : 0
    };
    pendingAppleTempoStates.set(chantId, pendingState);
  }

  if (player.isPlaying) {
    player.pause();
    AudioUI.updatePlayPauseIcons(chantId, false);
  }

  setTempoStatus(chantId, 'Chargement de la vitesse...');
  setTempoPlayDisabled(chantId, true);

  try {
    const response = await fetch(`/api/audio-variants/${chantId}/?tempo=${encodeURIComponent(tempo)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    if (data.status === 'ready') {
      await applyAppleTempoVoices(
        chantId,
        data.voices || [],
        tempo,
        pendingState.progressRatio,
        pendingState.shouldResume
      );
      pendingAppleTempoStates.delete(chantId);
      setTempoStatus(chantId, '');
      setTempoPlayDisabled(chantId, false);
      return;
    }

    if (data.status === 'generating') {
      setTempoStatus(chantId, 'Préparation de cette vitesse...');
      const timeoutId = window.setTimeout(() => {
        activeTempoVariantPollers.delete(chantId);
        loadAppleTempoVariant(chantId, tempo);
      }, 3000);
      activeTempoVariantPollers.set(chantId, timeoutId);
      return;
    }

    setTempoStatus(chantId, 'Cette vitesse n’est pas encore disponible.');
    pendingAppleTempoStates.delete(chantId);
  } catch (error) {
    console.error('Apple tempo variant error:', error);
    setTempoStatus(chantId, 'Impossible de charger cette vitesse.');
    pendingAppleTempoStates.delete(chantId);
  } finally {
    if (!activeTempoVariantPollers.has(chantId)) {
      setTempoPlayDisabled(chantId, false);
    }
  }
}

async function applyAppleTempoVoices(chantId, voices, tempo, progressRatio, shouldResume) {
  const container = document.getElementById(`audio-container-${chantId}`);
  if (!container || !voices.length) return;

  const oldPlayer = WebAudioPlayerManager.getPlayer(chantId);
  const voiceStates = captureVoiceStates(oldPlayer);

  voices.forEach(voice => {
    const voiceType = getVoiceType(voice);
    const stableId = `${chantId}_${voiceType}`;
    let div = document.getElementById(`audio-${stableId}`);
    if (!div) {
      div = document.createElement('div');
      div.id = `audio-${stableId}`;
      container.appendChild(div);
    }
    div.dataset.src = voice.url;
    div.dataset.voiceType = voiceType;
    div.dataset.voiceLabel = voice.label || '';
  });

  WebAudioPlayerManager.destroyPlayer(chantId);
  initializeWebAudioPlayer(chantId);
  const player = WebAudioPlayerManager.getPlayer(chantId);
  restoreVoiceStates(player, voiceStates);
  player.setPlaybackRate(1.0);

  const root = document.getElementById(`draggable-player-${chantId}`);
  if (root) root.dataset.currentAppleTempo = tempo;
  AudioUI.updateSpeedDisplay(chantId, tempo);

  if (progressRatio > 0 || shouldResume) {
    await player.loadAll();
    const targetTime = progressRatio * player.getDuration();
    player.seekTo(targetTime);
  }

  syncChantUI(chantId);
  if (shouldResume) {
    if (await player.play()) {
      AudioUI.updatePlayPauseIcons(chantId, true);
    }
  }
}

function captureVoiceStates(player) {
  const states = new Map();
  if (!player || !player.tracks) return states;
  const soloTrack = player.getSoloTrack();
  player.tracks.forEach((track, audioId) => {
    states.set(track.voiceType, {
      volume: player.getVolume(audioId),
      muted: player.isMuted(audioId),
      solo: soloTrack === audioId
    });
  });
  return states;
}

function restoreVoiceStates(player, states) {
  let soloAudioId = null;
  player.tracks.forEach((track, audioId) => {
    const state = states.get(track.voiceType);
    if (!state) return;
    player.setVolume(audioId, state.volume);
    if (state.muted) player.mute(audioId);
    else player.unmute(audioId);
    previousVolumes[audioId] = state.volume;
    if (state.solo) soloAudioId = audioId;
  });
  if (soloAudioId) player.toggleSolo(soloAudioId);
}

function setTempoStatus(chantId, message) {
  const status = document.getElementById(`tempo-status-${chantId}`);
  if (!status) return;
  status.textContent = message || '';
  status.classList.toggle('d-none', !message);
}

function setTempoPlayDisabled(chantId, disabled) {
  const playBtn = document.getElementById(`play-pause-btn-${chantId}`);
  if (!playBtn) return;
  playBtn.disabled = !!disabled;
  playBtn.setAttribute('aria-disabled', disabled ? 'true' : 'false');
}

// ============================================
// Voice Controls (Volume/Solo)
// ============================================

/**
 * Sync UI for all voices in a chant (sliders and buttons)
 */
function syncChantUI(chantId) {
  chantId = String(chantId);
  if (USE_WEB_AUDIO) {
    const player = WebAudioPlayerManager.getPlayer(chantId);
    if (!player) return;
    const soloTrack = player.getSoloTrack();

    document.querySelectorAll(`#voice-controls-${chantId} [data-audio-id]`).forEach(ctrl => {
      const id = ctrl.dataset.audioId;
      const isSoloed = (soloTrack === id);
      const isMuted = player.isMuted(id);
      const effectivelyMuted = isMuted || (soloTrack !== null && !isSoloed);
      const volume = player.getVolume(id);

      AudioUI.updateSoloButtonState(id, isSoloed);
      AudioUI.updateMuteButtonState(id, effectivelyMuted);
      
      const slider = document.getElementById('volume-slider-' + id);
      if (slider) {
        slider.value = effectivelyMuted ? 0 : Math.sqrt(volume) * 100;
        slider.style.opacity = effectivelyMuted ? '0.6' : '1';
      }
    });
  } else {
    const container = document.getElementById('audio-container-' + chantId);
    if (!container) return;
    container.querySelectorAll('audio').forEach(a => {
      const id = a.id.replace('audio-', '');
      syncVoiceUI(id);
    });
  }
}

function updateVolume(audioId, value) {
  audioId = String(audioId);
  if (!USE_WEB_AUDIO) return;
  const chantId = getChantIdForAudio(audioId);
  const volume = Math.pow(value / 100, 2);
  const slider = document.getElementById('volume-slider-' + audioId);
  if (slider) {
    slider.setAttribute('aria-valuenow', String(value));
    slider.setAttribute('aria-valuetext', value == 0 ? 'Muet' : `${value} pour cent`);
  }

  if (USE_WEB_AUDIO) {
    const player = WebAudioPlayerManager.getPlayer(chantId);
    if (!player) return;

    if (value == 0) {
      player.mute(audioId);
    } else {
      // Break solo if unmuting a different track
      const soloTrack = player.getSoloTrack();
      if (soloTrack && soloTrack !== audioId) {
        player.tracks.forEach((t, id) => {
          if (id !== soloTrack && id !== audioId) player.mute(id);
        });
        player.toggleSolo(soloTrack); // Turn off solo mode
      }
      
      player.unmute(audioId);
      player.setVolume(audioId, volume);
      previousVolumes[audioId] = volume;
    }
  } else {
    const audio = document.getElementById('audio-' + audioId);
    if (!audio) return;
    if (value == 0) {
      audio.muted = true;
      manualMutes[audioId] = true;
    } else {
      // Break solo legacy
      if (currentSoloTrack && currentSoloTrack !== audioId) {
        const oldSolo = currentSoloTrack;
        currentSoloTrack = null;
        document.querySelectorAll(`#audio-container-${chantId} audio`).forEach(a => {
           const id = a.id.replace('audio-', '');
           if (id !== oldSolo && id !== audioId) {
               a.muted = true;
               manualMutes[id] = true;
           } else {
               a.muted = false;
           }
        });
      }
      audio.muted = false;
      audio.volume = volume;
      previousVolumes[audioId] = volume;
      manualMutes[audioId] = false;
    }
  }
  syncChantUI(chantId);
}

function toggleMuteVolume(audioId) {
  audioId = String(audioId);
  if (!USE_WEB_AUDIO) return;
  const chantId = getChantIdForAudio(audioId);
  
  if (USE_WEB_AUDIO) {
    const player = WebAudioPlayerManager.getPlayer(chantId);
    const soloTrack = player.getSoloTrack();
    const isActuallyMuted = player.isMuted(audioId);
    const isEffectivelyMuted = isActuallyMuted || (soloTrack && soloTrack !== audioId);

    if (isEffectivelyMuted) {
      // UNMUTING
      if (soloTrack && soloTrack !== audioId) {
        player.tracks.forEach((t, id) => {
          if (id !== soloTrack && id !== audioId) player.mute(id);
        });
        player.toggleSolo(soloTrack); // Disable solo
      }
      player.unmute(audioId);
      player.setVolume(audioId, previousVolumes[audioId] || 1);
    } else {
      // MUTING
      previousVolumes[audioId] = player.getVolume(audioId);
      player.mute(audioId);
    }
  } else {
    const audio = document.getElementById('audio-' + audioId);
    const currentlyMuted = audio.muted;
    const effectivelyMuted = currentlyMuted || (currentSoloTrack && currentSoloTrack !== audioId);

    if (effectivelyMuted) {
      // UNMUTING (Break solo)
      if (currentSoloTrack && currentSoloTrack !== audioId) {
        const oldSolo = currentSoloTrack;
        currentSoloTrack = null;
        document.querySelectorAll(`#audio-container-${chantId} audio`).forEach(a => {
           const id = a.id.replace('audio-', '');
           if (id !== oldSolo && id !== audioId) {
               a.muted = true;
               manualMutes[id] = true;
           } else {
               a.muted = false;
               a.volume = previousVolumes[id] || 1;
           }
        });
      } else {
        audio.muted = false;
        manualMutes[audioId] = false;
      }
    } else {
      // MUTING
      audio.muted = true;
      manualMutes[audioId] = true;
    }
  }
  syncChantUI(chantId);
}

function toggleSolo(audioId) {
  audioId = String(audioId);
  if (!USE_WEB_AUDIO) return;
  if (USE_WEB_AUDIO) {
    toggleSoloWebAudio(audioId);
  } else {
    toggleSoloLegacy(audioId);
  }
}

function toggleSoloWebAudio(audioId) {
  const chantId = getChantIdForAudio(audioId);
  const player = WebAudioPlayerManager.getPlayer(chantId);
  player.toggleSolo(audioId);
  syncChantUI(chantId);
}

function toggleSoloLegacy(audioId) {
  const chantId = getChantIdForAudio(audioId);
  const audios = document.querySelectorAll(`#audio-container-${chantId} audio`);
  
  if (currentSoloTrack === audioId) {
    currentSoloTrack = null;
    audios.forEach(a => {
      const id = a.id.replace('audio-', '');
      if (!manualMutes[id]) {
        a.muted = false;
        a.volume = previousVolumes[id] || 1;
      }
    });
  } else {
    currentSoloTrack = audioId;
    audios.forEach(a => {
      const id = a.id.replace('audio-', '');
      if (id !== audioId) {
        a.muted = true;
      } else {
        a.muted = false;
        a.volume = previousVolumes[id] || 1;
      }
    });
  }
  syncChantUI(chantId);
}

// ============================================
// Polling Integration
// ============================================

function startAudioPolling(chantId) {
  AudioPolling.startPolling(chantId, {
    onUpdate: (data) => {
      updateProgressIndicator(chantId, data.progress);
      updateAudioPlayer(chantId, data.voices);
    },
    onComplete: (data) => {
      hideLoadingSpinner(chantId);
    }
  });
}

function updateProgressIndicator(chantId, progress) {
  const indicator = document.getElementById(`progress-indicator-${chantId}`);
  if (indicator && progress && progress.label) indicator.textContent = progress.label;
  if (progress && typeof progress.current === 'number' && typeof progress.total === 'number' && progress.total > 0) {
    const percentage = (progress.current / progress.total) * 100;
    updateProgressIndicatorState(chantId, percentage);
  }
}

function hideLoadingSpinner(chantId) {
  AudioUI.setPlayerSectionVisibility(chantId, 'loading', false);
  const spinner = document.getElementById(`loading-spinner-${chantId}`);
  if (spinner) spinner.style.display = 'none';
}

function updateAudioPlayer(chantId, voices) {
  if (!voices || !voices.length) return;
  AudioUI.setPlayerSectionVisibility(chantId, 'audio-player', true);
  const wrapper = document.querySelector(`.audio-player-wrapper[data-partition-id="${chantId}"]`);
  const isMixOnly = wrapper?.dataset.mixOnly === 'true';
  voices.forEach(v => {
    if (getVoiceType(v) === 'M' && !isMixOnly) {
      addVoiceToPlayer(chantId, v);
      return;
    }

    if (!document.getElementById(`audio-${v.id}`)) {
      addVoiceToPlayer(chantId, v);
    }
  });
}

function addVoiceToPlayer(chantId, voice) {
  const voiceType = getVoiceType(voice);
  if (voiceType === 'M') {
    const wrapper = document.querySelector(`.audio-player-wrapper[data-partition-id="${chantId}"]`);
    const isMixOnly = wrapper?.dataset.mixOnly === 'true';
    if (!isMixOnly) {
      AudioUI.addMixDownloadButton(chantId, voice);
      return;
    }
  }

  // Create hidden registry element
  const container = document.getElementById(`audio-container-${chantId}`);
  if (container) {
    const div = document.createElement('div');
    div.id = `audio-${voice.id}`;
    div.dataset.src = voice.url;
    div.dataset.voiceType = voiceType;
    div.dataset.voiceLabel = voice.label || '';
    container.appendChild(div);
  }

  if (USE_WEB_AUDIO) {
    const player = WebAudioPlayerManager.getPlayer(chantId);
    player.addTrack(voice.id, voice.url, voiceType);
    // Explicitly prefetch the buffer so it's ready when user clicks play
    if (typeof player.prefetchTrack === 'function') {
        player.prefetchTrack(voice.id);
    }
  }

  // Add UI
  const controls = document.getElementById(`voice-controls-${chantId}`);
  if (controls) {
    const el = AudioUI.createVoiceControlElement(voice);
    el.classList.add('opacity-0', 'transition-fade');
    controls.appendChild(el);
    requestAnimationFrame(() => el.classList.remove('opacity-0'));
  }
  
  previousVolumes[voice.id] = 1;
}

// ============================================
// Utilities & Global Exports
// ============================================

function getChantIdForAudio(audioId) {
  const el = document.querySelector(`[data-audio-id="${audioId}"]`);
  const controls = el ? el.closest('[id^="voice-controls-"]') : null;
  return controls ? controls.id.replace('voice-controls-', '') : undefined;
}

function stopAllAudio() {
  activeTempoVariantPollers.forEach(timeoutId => clearTimeout(timeoutId));
  activeTempoVariantPollers.clear();
  pendingAppleTempoStates.clear();
  if (USE_WEB_AUDIO) WebAudioPlayerManager.stopAll();
  else document.querySelectorAll('audio').forEach(a => { a.pause(); a.currentTime = 0; });
}

function handleAudioInput(target) {
  const action = target.dataset.audioAction;
  if (!action) return;

  if (action === 'seek') {
    const value = target.value;
    target.setAttribute('aria-valuenow', value);
    target.setAttribute('aria-valuetext', `${value} pour cent`);
    seekTo(target.dataset.chantId, value);
  } else if (action === 'volume') {
    updateVolume(target.dataset.audioId, target.value);
  } else if (action === 'speed') {
    const chantId = target.dataset.chantId;
    updatePlaybackSpeedDisplay(chantId, target.value);
    setPlaybackSpeed(chantId, target.value);
  }
}

function handleAudioClick(target) {
  const control = target.closest('[data-audio-action]');
  if (!control) return;
  const action = control.dataset.audioAction;

  if (action === 'play-pause') {
    togglePlayPause(control.dataset.chantId);
  } else if (action === 'advanced-toggle') {
    toggleAdvancedAudio(control.dataset.chantId);
  } else if (action === 'solo') {
    toggleSolo(control.dataset.audioId);
  } else if (action === 'mute') {
    toggleMuteVolume(control.dataset.audioId);
  } else if (action === 'speed') {
    setPlaybackSpeed(control.dataset.chantId, control.dataset.speedValue || control.value || control.textContent);
  }
}

window.stopAllAudio = stopAllAudio;
window.formatTime = AudioUI.formatTime; // For compatibility

// Legacy compatibility aliases
function playAll(id) { togglePlayPause(id); }
function pauseAll(id) { togglePlayPause(id); }
function toggleMute(id) { toggleMuteVolume(id); }
function setVolume(id, v) { updateVolume(id, v * 100); }

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('audio[id^="audio-"]').forEach(a => {
    const id = a.id.replace('audio-', '');
    previousVolumes[id] = 1;
    AudioUI.updateMuteButtonState(id, false);
  });
});

document.addEventListener('input', (event) => {
  if (event.target instanceof HTMLElement && event.target.dataset.audioAction) {
    handleAudioInput(event.target);
  }
});

document.addEventListener('click', (event) => {
  if (event.target instanceof Element) {
    handleAudioClick(event.target);
  }
});

document.addEventListener('htmx:beforeRequest', () => {
  // Stop all playing audios when navigating away via HTMX (e.g. changing the day)
  if (typeof stopAllAudio === 'function') {
      stopAllAudio();
  }
  if (typeof AudioPolling !== 'undefined' && AudioPolling.stopAll) {
    AudioPolling.stopAll();
  }
});
