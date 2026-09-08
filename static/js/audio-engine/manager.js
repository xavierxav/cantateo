/**
 * PlayerManager - Manages multiple SyncedTrackPlayers
 */
const WebAudioPlayerManager = (function() {
  const players = new Map(); // chantId -> SyncedTrackPlayer

  function getPlayer(chantId) {
    chantId = String(chantId);
    if (!players.has(chantId)) {
      players.set(chantId, new SyncedTrackPlayer(chantId));
    }
    return players.get(chantId);
  }

  return {
    getPlayer,
    hasPlayer: (id) => players.has(String(id)),
    destroyPlayer: (id) => {
      const p = players.get(String(id));
      if (p) { p.destroy(); players.delete(String(id)); }
    },
    destroyAll: () => { players.forEach(p => p.destroy()); players.clear(); },
    stopAll: () => players.forEach(p => p.stop()),
    isSupported: () => AudioContextManager.isSupported()
  };
})();

window.WebAudioPlayerManager = WebAudioPlayerManager;
