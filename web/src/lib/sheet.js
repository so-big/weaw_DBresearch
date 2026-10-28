// Bottom-sheet gestures for phones (Svelte action).
//   drag the handle/header (or pull down from the top of the content):
//     down past ~30% or a quick flick  → close (or back to normal size if expanded)
//     up past 60px or a quick flick     → expand to full screen
//   tap the handle                      → toggle full screen
// Only transform moves while dragging; the expand/shrink is one height animation.
//
// <div use:sheet={{ enabled, onclose, scroller: '.body' }}> with [data-sheet-handle] inside.

const EASE = 'cubic-bezier(0.2, 0.8, 0.2, 1)';
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const INTERACTIVE = 'button, a, input, select, textarea, label';

export function sheet(node, options) {
  let opts = options;
  let startY = 0;
  let startT = 0;
  let dy = 0;
  let dragging = false;
  let moved = false;
  let expanded = false;
  let normalHeight = 0;

  const anim = (ms) => (reduced() ? '0ms' : `${ms}ms`);
  const setY = (y) => (node.style.transform = y ? `translate3d(0, ${y}px, 0)` : '');

  function begin(y) {
    dragging = true;
    moved = false;
    startY = y;
    startT = performance.now();
    dy = 0;
    node.style.transition = 'none';
  }
  function move(y) {
    dy = y - startY;
    if (Math.abs(dy) > 4) moved = true;
    setY(dy > 0 ? dy : dy * 0.3); // pulling up resists: the sheet grows on release instead
  }
  function settle() {
    node.style.transition = `transform ${anim(220)} ${EASE}, height ${anim(240)} ${EASE}`;
  }
  function end() {
    if (!dragging) return;
    dragging = false;
    const speed = dy / Math.max(1, performance.now() - startT); // px per ms, + is down
    const h = node.offsetHeight;
    settle();
    if (!moved) {
      setY(0);
      return 'tap';
    }
    if (dy > Math.min(160, h * 0.3) || speed > 0.65) {
      if (expanded && dy < h * 0.55 && speed < 1.4) {
        shrink();
        setY(0);
      } else {
        node.style.transition = 'none';
        opts.onclose?.(); // the sheet's own out-transition continues from where the finger left it
      }
    } else if (dy < -60 || speed < -0.65) {
      grow();
      setY(0);
    } else {
      setY(0);
    }
  }

  function grow() {
    if (expanded) return;
    expanded = true;
    normalHeight = node.offsetHeight;
    node.style.height = `${normalHeight}px`;
    node.style.maxHeight = 'none';
    node.offsetHeight; // apply the start height before animating
    settle();
    node.style.height = 'calc(100dvh - 10px - env(safe-area-inset-top, 0px))';
    node.dataset.expanded = 'true';
  }
  function shrink() {
    if (!expanded) return;
    expanded = false;
    node.style.height = `${node.offsetHeight}px`;
    node.offsetHeight;
    settle();
    node.style.height = `${normalHeight}px`;
    delete node.dataset.expanded;
    const done = () => {
      node.style.height = '';
      node.style.maxHeight = '';
      node.removeEventListener('transitionend', done);
    };
    node.addEventListener('transitionend', done);
  }

  // Handle + header: pointer events (mouse, pen, touch).
  function down(e) {
    if (!opts.enabled || e.button > 0) return;
    const handle = e.target.closest('[data-sheet-handle]');
    if (!handle || (e.target.closest(INTERACTIVE) && !e.target.closest('.sheet-grab'))) return;
    handle.setPointerCapture?.(e.pointerId);
    begin(e.clientY);
    const onMove = (ev) => dragging && move(ev.clientY);
    const onUp = () => {
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
      if (end() === 'tap' && e.target.closest('.sheet-grab')) (expanded ? shrink : grow)();
    };
    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  }

  // Content: pulling down while already scrolled to the top moves the sheet instead.
  let touchY = null;
  let scroller = null;
  function touchStart(e) {
    if (!opts.enabled || !opts.scroller) return;
    scroller = e.target.closest(opts.scroller);
    touchY = scroller && scroller.scrollTop <= 0 ? e.touches[0].clientY : null;
  }
  function touchMove(e) {
    if (touchY === null) return;
    const y = e.touches[0].clientY;
    if (!dragging) {
      if (y - touchY > 8 && scroller.scrollTop <= 0) begin(touchY);
      else if (touchY - y > 4) touchY = null; // scrolling up the content: leave it alone
      else return;
    }
    if (dragging) {
      e.preventDefault();
      move(y);
    }
  }
  function touchEnd() {
    touchY = null;
    if (dragging) end();
  }

  node.addEventListener('pointerdown', down);
  node.addEventListener('touchstart', touchStart, { passive: true });
  node.addEventListener('touchmove', touchMove, { passive: false });
  node.addEventListener('touchend', touchEnd);
  node.addEventListener('touchcancel', touchEnd);

  return {
    update(next) {
      opts = next;
      if (!opts.enabled && expanded) {
        expanded = false;
        node.style.height = node.style.maxHeight = '';
        delete node.dataset.expanded;
      }
    },
    destroy() {
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('touchstart', touchStart);
      node.removeEventListener('touchmove', touchMove);
      node.removeEventListener('touchend', touchEnd);
      node.removeEventListener('touchcancel', touchEnd);
    },
  };
}
