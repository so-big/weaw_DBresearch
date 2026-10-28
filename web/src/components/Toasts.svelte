<script>
  import { fly } from 'svelte/transition';
  import { toasts, screen, ms } from '../lib/state.svelte.js';
</script>

<div class="toasts" class:phone={!screen.wide} aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast {t.kind}" in:fly={{ y: 16, duration: ms(220) }} out:fly={{ y: 8, duration: ms(150) }}>{t.text}</div>
  {/each}
</div>

<style>
  .toasts { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 60; display: flex; flex-direction: column; gap: 8px; align-items: center; pointer-events: none; width: max-content; max-width: calc(100vw - 32px); }
  .toasts.phone { bottom: calc(var(--bottom-h) + env(safe-area-inset-bottom) + 14px); }
  .toast { background: var(--text); color: var(--bg); padding: 10px 16px; border-radius: 10px; font-size: 14px; box-shadow: var(--shadow); }
  .toast.bad { background: var(--bad); color: #fff; }
</style>
