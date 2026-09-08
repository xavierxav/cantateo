/**
 * PlayerManager - Manages multiple SyncedTrackPlayers
 */
const WebAudioPlayerManager = (function() {
  const players = new Map(); // partitionId -> SyncedTrackPlayer

  function getPlayer(partitionId) {
    partitionId = String(partitionId);
    if (!players.has(partitionId)) {
      players.set(partitionId, new SyncedTrackPlayer(partitionId));
    }
    return players.get(partitionId);
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
