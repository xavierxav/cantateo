/**
 * Audio Polling System
 * Handles checking for generated audio files via the API.
 */

const AudioPolling = (function() {
  const activePollers = new Map();
  const MAX_ERRORS = 10;
  const POLL_INTERVAL = 3000;

  /**
   * Start polling for a specific partition
   */
  async function startPolling(partitionId, callbacks) {
    if (activePollers.has(partitionId)) return;

    const state = {
      errorCount: 0,
      isActive: true,
      callbacks: callbacks || {},
      timeoutId: null
    };

    activePollers.set(partitionId, state);
    return poll(partitionId);
  }

  /**
   * Recursive poll function
   */
  async function poll(partitionId) {
    const state = activePollers.get(partitionId);
    if (!state || !state.isActive) return;

    try {
      const response = await fetch(`/api/audio-status/${partitionId}/`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      state.errorCount = 0;

      // Notify through callbacks
      if (state.callbacks.onUpdate) {
        state.callbacks.onUpdate(data);
      }

      if (data.generation_complete || ['succeeded', 'failed', 'complete'].includes(data.status)) {
        stopPolling(partitionId);
        if (state.callbacks.onComplete) {
          state.callbacks.onComplete(data);
        }
        return;
      }
    } catch (error) {
      console.error(`Polling error for partition ${partitionId}:`, error);
      state.errorCount++;
      
      if (state.errorCount >= MAX_ERRORS) {
        stopPolling(partitionId);
        if (state.callbacks.onError) {
          state.callbacks.onError(error);
        }
        return;
      }
    }

    if (!state.isActive) return;
    state.timeoutId = window.setTimeout(() => {
      poll(partitionId);
    }, POLL_INTERVAL);
  }

  /**
   * Stop polling for a partition
   */
  function stopPolling(partitionId) {
    const state = activePollers.get(partitionId);
    if (state) {
      state.isActive = false;
      if (state.timeoutId) {
        clearTimeout(state.timeoutId);
      }
      activePollers.delete(partitionId);
    }
  }

  function stopAll() {
    Array.from(activePollers.keys()).forEach(stopPolling);
  }

  return {
    startPolling,
    stopPolling,
    stopAll
  };
})();

// Export
window.AudioPolling = AudioPolling;
