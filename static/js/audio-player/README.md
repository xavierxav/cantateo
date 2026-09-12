# audio-player — Playback UI and polling

`controls.js` binds DOM events to the engine (play/seek/speed, Apple tempo
fallback), `ui.js` renders progress/state, `polling.js` handles async audio
generation status, `initializer.js` boots players from `data-partition-id`.

Engine internals: `../audio-engine/`. Architecture: [`docs/STATIC.md`](../../../docs/STATIC.md).
