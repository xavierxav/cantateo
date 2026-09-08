/**
 * Draggable implementation for UI elements
 */
const Draggable = (function () {
    let sessionPos = null; // Stays during HTMX swaps but resets on page refresh

    function init(elementId, handleSelector) {
        const el = document.getElementById(elementId);
        if (!el) return;

        // Don't init draggability on mobile (where it's not fixed)
        if (window.innerWidth <= 991) return;

        const handle = handleSelector ? el.querySelector(handleSelector) : el;
        if (!handle) return;

        let posX = 0, posY = 0, mouseX = 0, mouseY = 0;

        // Apply saved session position if available
        if (sessionPos) {
            el.style.top = sessionPos.top;
            el.style.left = sessionPos.left;
            el.style.right = 'auto'; // Disable initial right placement
            
            // Constrain immediately in case container size changed
            requestAnimationFrame(() => {
                const parent = document.body;
                if (parent) {
                    const maxTop = Math.max(140, parent.scrollHeight - el.offsetHeight);
                    const maxLeft = Math.max(0, parent.clientWidth - el.offsetWidth);
                    const currentTop = parseInt(el.style.top) || el.offsetTop;
                    const currentLeft = parseInt(el.style.left) || el.offsetLeft;
                    
                    if (currentTop < 145) el.style.top = '145px';
                    else if (currentTop > maxTop) el.style.top = maxTop + 'px';
                    
                    if (currentLeft < 0) el.style.left = '0px';
                    else if (currentLeft > maxLeft) el.style.left = maxLeft + 'px';
                }
            });
        }

        handle.onmousedown = dragMouseDown;

        function dragMouseDown(e) {
            // Don't drag if clicking buttons, links, or inputs
            const interactiveElement = e.target.closest('button, a, input, select, textarea, [role="button"]');
            if (interactiveElement) return;

            e.preventDefault();
            // Get the mouse cursor position at startup
            mouseX = e.clientX;
            mouseY = e.clientY;
            document.onmouseup = closeDragElement;
            document.onmousemove = elementDrag;

            handle.style.cursor = 'grabbing';
            el.style.transition = 'none'; // Disable smooth transitions while dragging
        }

        function elementDrag(e) {
            e.preventDefault();
            // Calculate the new cursor position
            posX = mouseX - e.clientX;
            posY = mouseY - e.clientY;
            mouseX = e.clientX;
            mouseY = e.clientY;

            // Set the element's new position with boundary checks
            let nextTop = el.offsetTop - posY;
            let nextLeft = el.offsetLeft - posX;

            // Use document.body as reference for full-screen boundaries
            const parent = document.body;
            const maxLeft = parent.clientWidth - el.offsetWidth;
            const maxTop = parent.scrollHeight - el.offsetHeight;
            
            // Enforce boundaries
            // Top limit: 145px to stay below Navbar + Liturgical Header
            if (nextTop < 145) nextTop = 145;
            if (nextTop > maxTop) nextTop = maxTop;
            
            // Side limits: Exactly to the edge (0 and maxLeft)
            if (nextLeft < 0) nextLeft = 0;
            if (nextLeft > maxLeft) nextLeft = maxLeft;
            
            el.style.top = nextTop + "px";
            el.style.left = nextLeft + "px";
            el.style.right = 'auto';
        }

        function closeDragElement() {
            // Stop moving when mouse button is released
            document.onmouseup = null;
            document.onmousemove = null;
            handle.style.cursor = 'grab';
            el.style.transition = 'box-shadow 0.3s ease';

            // Save for session
            sessionPos = {
                top: el.style.top,
                left: el.style.left
            };
        }
    }

    return { init };
})();

// Init all draggable players in the DOM
function initDraggablePlayers() {
    const players = document.querySelectorAll('[id^="draggable-player-"]');
    players.forEach(player => {
        Draggable.init(player.id);
    });
}

// Auto-init on page load
document.addEventListener('DOMContentLoaded', initDraggablePlayers);

// Re-init after HTMX swaps new content (e.g. date change)
document.addEventListener('htmx:afterSettle', initDraggablePlayers);
