/**
 * Audio UI Manager
 * Handles all DOM manipulation and visual updates for the audio player.
 */

const AudioUI = (function() {
  /**
   * Format seconds to MM:SS
   */
  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins + ':' + (secs < 10 ? '0' : '') + secs;
  }

  /**
   * Update progress bar and time labels
   */
  function updateProgressUI(partitionId, currentTime, duration) {
    const progressBar = document.getElementById('progress-bar-' + partitionId);
    const currentTimeEl = document.getElementById('current-time-' + partitionId);
    const durationEl = document.getElementById('duration-' + partitionId);

    if (currentTimeEl) {
      currentTimeEl.textContent = formatTime(currentTime);
    }
    
    if (durationEl && duration > 0) {
      durationEl.textContent = formatTime(duration);
    }

    if (progressBar && duration > 0) {
      progressBar.value = (currentTime / duration) * 100;
      progressBar.setAttribute('aria-valuenow', String(Math.round((currentTime / duration) * 100)));
      progressBar.setAttribute('aria-valuetext', formatTime(currentTime));
    }
  }

  /**
   * Update mute button appearance
   */
  function updateMuteButtonState(audioId, isMuted) {
    const muteBtn = document.getElementById('mute-btn-' + audioId);
    const volumeIcon = document.getElementById('volume-icon-' + audioId);
    const slider = document.getElementById('volume-slider-' + audioId);
    const wrapper = document.querySelector(`[data-audio-id="${audioId}"]`);
    const label = wrapper ? wrapper.dataset.voiceLabel : 'la piste';

    if (!muteBtn || !volumeIcon) return;

    muteBtn.setAttribute('aria-pressed', isMuted ? 'true' : 'false');
    muteBtn.setAttribute('aria-label', isMuted ? `Rétablir le son de ${label}` : `Couper le son de ${label}`);

    if (isMuted) {
      muteBtn.classList.remove('btn-outline-secondary');
      muteBtn.classList.add('btn-secondary');
      if (slider) slider.style.opacity = '0.5';
      if (slider) {
        slider.setAttribute('aria-valuenow', '0');
        slider.setAttribute('aria-valuetext', 'Muet');
      }
      volumeIcon.querySelector('path').setAttribute('d',
        'M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z'
      );
    } else {
      muteBtn.classList.remove('btn-secondary');
      muteBtn.classList.add('btn-outline-secondary');
      if (slider) slider.style.opacity = '1';
      if (slider) {
        slider.setAttribute('aria-valuenow', slider.value || '100');
        slider.setAttribute('aria-valuetext', `${slider.value || 100} pour cent`);
      }
      volumeIcon.querySelector('path').setAttribute('d',
        'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z'
      );
    }
  }

  /**
   * Update Solo button state
   */
  function updateSoloButtonState(audioId, isSoloed) {
    const btn = document.getElementById('solo-btn-' + audioId);
    const wrapper = document.querySelector(`[data-audio-id="${audioId}"]`);
    const label = wrapper ? wrapper.dataset.voiceLabel : 'la piste';
    if (!btn) return;

    btn.setAttribute('aria-pressed', isSoloed ? 'true' : 'false');
    btn.setAttribute('aria-label', isSoloed ? `Désactiver le solo de ${label}` : `Mettre en solo ${label}`);
    
    if (isSoloed) {
      btn.classList.remove('btn-outline-warning');
      btn.classList.add('btn-warning');
    } else {
      btn.classList.remove('btn-warning');
      btn.classList.add('btn-outline-warning');
    }
  }

  function createSvg(width, height, pathData) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', String(width));
    svg.setAttribute('height', String(height));
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'currentColor');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', pathData);
    svg.appendChild(path);
    return svg;
  }

  /**
   * Create a voice control node without interpolating untrusted strings as HTML.
   */
  function createVoiceControlElement(voice) {
    const voiceType = voice.voice_type || voice.type_voix || '';
    const label = voice.label || '';
    const wrapper = document.createElement('div');
    wrapper.className = 'col-6 voice-control-wrapper';
    wrapper.dataset.voiceType = voiceType;
    wrapper.dataset.audioId = voice.id;
    wrapper.dataset.voiceLabel = label;

    const column = document.createElement('div');
    column.className = 'd-flex flex-column';
    wrapper.appendChild(column);

    const header = document.createElement('div');
    header.className = 'd-flex align-items-center justify-content-between mb-1 px-1';
    column.appendChild(header);

    const text = document.createElement('small');
    text.className = 'text-muted fw-bold';
    text.style.fontSize = '0.75rem';
    text.textContent = label;
    if (voice.est_synthetique) {
      const synth = document.createElement('span');
      synth.className = 'synth-label';
      synth.style.fontSize = '0.6rem';
      synth.style.opacity = '0.7';
      synth.textContent = ' (synth.)';
      text.appendChild(synth);
    }
    header.appendChild(text);

    const download = document.createElement('a');
    download.href = voice.download_url || '#';
    download.download = '';
    download.className = 'text-muted';
    download.title = `Télécharger ${label}`;
    download.setAttribute('aria-label', `Télécharger ${label}`);
    download.appendChild(createSvg(12, 12, 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z'));
    header.appendChild(download);

    const controls = document.createElement('div');
    controls.className = 'd-flex align-items-center gap-1';
    column.appendChild(controls);

    const solo = document.createElement('button');
    solo.type = 'button';
    solo.className = 'btn btn-sm btn-outline-warning border-0 p-0 solo-btn';
    solo.id = `solo-btn-${voice.id}`;
    solo.title = 'Solo';
    solo.dataset.audioAction = 'solo';
    solo.dataset.audioId = voice.id;
    solo.setAttribute('aria-pressed', 'false');
    solo.setAttribute('aria-label', `Mettre en solo ${label}`);
    solo.textContent = 'S';
    controls.appendChild(solo);

    const volumeGroup = document.createElement('div');
    volumeGroup.className = 'volume-control-group flex-grow-1';
    controls.appendChild(volumeGroup);

    const mute = document.createElement('button');
    mute.type = 'button';
    mute.className = 'btn btn-sm btn-outline-secondary border-0 p-0 mute-btn';
    mute.id = `mute-btn-${voice.id}`;
    mute.title = 'Mute';
    mute.dataset.audioAction = 'mute';
    mute.dataset.audioId = voice.id;
    mute.setAttribute('aria-pressed', 'false');
    mute.setAttribute('aria-label', `Couper le son de ${label}`);
    const volumeIcon = createSvg(
      14,
      14,
      'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z'
    );
    volumeIcon.id = `volume-icon-${voice.id}`;
    mute.appendChild(volumeIcon);
    volumeGroup.appendChild(mute);

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'form-range volume-slider';
    slider.min = '0';
    slider.max = '100';
    slider.value = '100';
    slider.id = `volume-slider-${voice.id}`;
    slider.dataset.audioAction = 'volume';
    slider.dataset.audioId = voice.id;
    slider.setAttribute('aria-label', `Volume de ${label}`);
    volumeGroup.appendChild(slider);

    return wrapper;
  }

  /**
   * Show/hide player specific sections
   */
  function setPlayerSectionVisibility(partitionId, section, visible) {
    const el = document.getElementById(`${section}-section-${partitionId}`);
    if (el) el.style.display = visible ? 'block' : 'none';
  }

  /**
   * Add a download button for the mix
   */
  function addMixDownloadButton(partitionId, voice) {
    if (document.getElementById(`mix-download-btn-${partitionId}`)) return;

    const btn = document.createElement('a');
    btn.id = `mix-download-btn-${partitionId}`;
    btn.href = voice.download_url;
    btn.download = '';
    btn.className = 'btn btn-sm btn-primary p-2 shadow-sm d-flex align-items-center justify-content-center';
    btn.setAttribute('aria-label', 'Télécharger le mix');
    btn.title = 'Télécharger MP3';
    btn.appendChild(createSvg(20, 20, 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z'));

    const topActions = document.querySelector(`#draggable-player-${partitionId} .audio-top-actions`);
    if (topActions) {
      topActions.appendChild(btn);
      return;
    }

    const audioSection = document.getElementById(`audio-player-section-${partitionId}`);
    if (!audioSection || !audioSection.parentNode) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'mb-3 d-flex justify-content-start';
    wrapper.appendChild(btn);
    audioSection.parentNode.insertBefore(wrapper, audioSection);
  }

  function updatePlayPauseIcons(partitionId, isPlaying) {
    const playIcon = document.getElementById('play-icon-' + partitionId);
    const pauseIcon = document.getElementById('pause-icon-' + partitionId);
    const spinner = document.getElementById('play-spinner-' + partitionId);
    const playBtn = document.getElementById('play-pause-btn-' + partitionId);

    if (spinner) spinner.style.display = 'none';

    if (playIcon && pauseIcon) {
      playIcon.style.display = isPlaying ? 'none' : 'block';
      pauseIcon.style.display = isPlaying ? 'block' : 'none';
    }

    if (playBtn) {
      playBtn.setAttribute('aria-pressed', isPlaying ? 'true' : 'false');
      playBtn.setAttribute('aria-label', isPlaying ? "Mettre en pause l'audio" : "Lire l'audio");
    }
  }

  function updateSpeedDisplay(partitionId, value) {
    const display = document.getElementById('speed-display-' + partitionId);
    const slider = document.getElementById('speed-slider-' + partitionId);
    const appleControls = document.getElementById(`apple-speed-controls-${partitionId}`);
    const numeric = parseFloat(value);
    const normalized = Number.isFinite(numeric) ? numeric.toFixed(1) : '1.0';
    const label = `${normalized}x`;
    const ariaText = `${normalized.replace('.', ',')} fois`;

    if (display) display.innerText = label;
    if (slider) {
      slider.setAttribute('aria-valuenow', String(Number.isFinite(numeric) ? numeric : 1));
      slider.setAttribute('aria-valuetext', ariaText);
    }
    if (appleControls) {
      appleControls.querySelectorAll('[data-speed-value]').forEach(btn => {
        const isActive = btn.dataset.speedValue === normalized;
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        btn.classList.toggle('btn-primary', isActive);
        btn.classList.toggle('btn-outline-primary', !isActive);
      });
    }
  }

  return {
    formatTime,
    updateProgressUI,
    updateMuteButtonState,
    updateSoloButtonState,
    createVoiceControlElement,
    setPlayerSectionVisibility,
    addMixDownloadButton,
    updatePlayPauseIcons,
    updateSpeedDisplay
  };
})();

// Export
window.AudioUI = AudioUI;
