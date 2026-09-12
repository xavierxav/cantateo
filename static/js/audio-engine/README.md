# audio-engine — Web Audio multitrack playback

`manager.js` owns one `SyncedTrackPlayer` (`player-core.js`) per partition:
5 synchronized sources (S/A/T/B + instrumental), drift correction, and
Safari/iOS fallback branches (tempo served as pre-rendered variants).

UI wiring lives in `../audio-player/`. Architecture details: [`docs/STATIC.md`](../../../docs/STATIC.md).
