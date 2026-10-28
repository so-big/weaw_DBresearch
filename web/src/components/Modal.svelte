<script>
  // Dialog on PC, bottom sheet on phones. Content and footer come in as snippets.
  import { fade, fly, scale } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import Icon from './Icon.svelte';
  import { screen, ms } from '../lib/state.svelte.js';
  import { sheet } from '../lib/sheet.js';

  let { title, onclose, children, footer, width = 480 } = $props();
  const uid = `m${Math.random().toString(36).slice(2, 8)}`;

  function panelIn(node) {
    return screen.wide
      ? scale(node, { start: 0.96, duration: ms(220), easing: cubicOut })
      : fly(node, { y: 400, duration: ms(240), easing: cubicOut, opacity: 1 });
  }
  function panelOut(node) {
    return screen.wide
      ? scale(node, { start: 0.97, duration: ms(140), easing: cubicOut })
      : fly(node, { y: 400, duration: ms(200), easing: cubicOut, opacity: 1 });
  }
  function focusFirst(node) {
    const el = node.querySelector('input:not([type=hidden]), select, textarea, button.primary-focus');
    setTimeout(() => (screen.wide ? el?.focus() : null), ms(230));
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose?.()} />

<div class="scrim" transition:fade={{ duration: ms(200) }} onclick={onclose} role="presentation"></div>
<div
  class="panel"
  class:sheet={!screen.wide}
  style="--w:{width}px"
  role="dialog"
  aria-modal="true"
  aria-labelledby={uid}
  in:panelIn
  out:panelOut
  use:focusFirst
  use:sheet={{ enabled: !screen.wide, onclose, scroller: '.body' }}
>
  {#if !screen.wide}<div class="sheet-grab" data-sheet-handle aria-hidden="true"></div>{/if}
  <div class="head" data-sheet-handle={!screen.wide ? '' : undefined}>
    <h2 id={uid}>{title}</h2>
    <button class="icon-btn" onclick={onclose} aria-label="ปิด"><Icon name="x" /></button>
  </div>
  <div class="body">{@render children()}</div>
  {#if footer}<div class="foot">{@render footer()}</div>{/if}
</div>

<style>
  .scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 50; }
  .panel {
    position: fixed; z-index: 51; left: 50%; top: 50%; translate: -50% -50%;
    width: min(var(--w), calc(100vw - 32px)); max-height: calc(100vh - 48px);
    background: var(--surface); border-radius: 16px; box-shadow: var(--shadow);
    display: flex; flex-direction: column;
  }
  .panel.sheet { left: 0; right: 0; top: auto; bottom: 0; translate: none; width: auto; max-height: 90vh; border-radius: 20px 20px 0 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 16px 18px 6px; }
  .sheet .head { padding-top: 0; }
  .body { flex: 1 1 auto; min-height: 0; padding: 8px 18px 16px; overflow: auto; overscroll-behavior: contain; display: flex; flex-direction: column; gap: 14px; }
  .foot { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 18px; border-top: 1px solid var(--border); }
  .sheet .foot { padding-bottom: calc(12px + env(safe-area-inset-bottom)); }
  .sheet .foot :global(.btn) { flex: 1; min-height: 46px; }
</style>
