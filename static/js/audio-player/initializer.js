/**
 * Audio Player Initializer
 * Handles the logic for detecting players in the DOM and initializing them
 */
(function () {
    function initPlayers(root) {
        const scope = root && root.querySelectorAll ? root : document;
        const players = scope.querySelectorAll('.audio-player-wrapper[data-partition-id]');

        players.forEach(player => {
            if (player.dataset.playerInitialized === 'true') {
                return;
            }

            const partitionId = player.dataset.partitionId;
            const hasMxl = player.dataset.hasMxl === 'true';
            const hasNonSynthetic = player.dataset.hasNonSynthetic === 'true';
            const audioCount = parseInt(player.dataset.audioCount || '0');

            player.dataset.playerInitialized = 'true';

            if (typeof initializePlayer === 'function' && audioCount > 0) {
                initializePlayer(partitionId);
            }

            if (hasMxl && !hasNonSynthetic && typeof startAudioPolling === 'function') {
                startAudioPolling(partitionId);
            }
        });
    }

    // Global toggle for advanced audio
    window.toggleAdvancedAudio = window.toggleAdvancedAudio || function (id) {
        const adv = document.getElementById('advanced-audio-' + id);
        const btn = document.getElementById('advanced-toggle-' + id);

        if (!adv || !btn) {
            console.warn('Advanced audio elements not found for ID:', id);
            return;
        }

        if (adv.style.display === 'none') {
            adv.style.display = 'block';
            btn.textContent = 'Masquer options avancées ▴';
            btn.setAttribute('aria-expanded', 'true');
            btn.setAttribute('aria-label', 'Masquer les options avancées');
        } else {
            adv.style.display = 'none';
            btn.textContent = 'Options avancées vitesse et voix ▾';
            btn.setAttribute('aria-expanded', 'false');
            btn.setAttribute('aria-label', 'Afficher les options avancées');
        }
    };

    window.updatePlaybackSpeedDisplay = window.updatePlaybackSpeedDisplay || function (partitionId, value) {
        if (typeof AudioUI !== 'undefined' && AudioUI.updateSpeedDisplay) {
            AudioUI.updateSpeedDisplay(partitionId, value);
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPlayers);
    } else {
        setTimeout(initPlayers, 100);
    }

    // Stop audio before swapping the main content
    document.addEventListener('htmx:beforeSwap', function (evt) {
        if (evt.detail.target && (
            evt.detail.target.id === 'psaume-details' ||
            evt.detail.target.id === 'psaume-main' ||
            evt.detail.target.querySelector?.('.audio-player-wrapper')
        )) {
            if (typeof window.stopAllAudio === 'function') {
                window.stopAllAudio();
            }
            if (typeof AudioPolling !== 'undefined' && AudioPolling.stopAll) {
                AudioPolling.stopAll();
            }
            if (typeof WebAudioPlayerManager !== 'undefined' && WebAudioPlayerManager.destroyAll) {
                WebAudioPlayerManager.destroyAll();
            }
        }
    });

    // HTMX support: re-init on swap
    document.addEventListener('htmx:afterSwap', function (evt) {
        initPlayers(evt.detail.target || document);
    });
})();
