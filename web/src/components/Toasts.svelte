<script>
  import { fly } from 'svelte/transition';
  import { toasts, dismissToast, screen, ms, ui } from '../lib/state.svelte.js';

  function act(t) {
    dismissToast(t.id);
    t.action.run();
  }
</script>

<div class="toasts" class:phone={!screen.wide} class:bar={ui.bar} aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast {t.kind}" class:has-action={t.action} in:fly={{ y: 16, duration: ms(220) }} out:fly={{ y: 8, duration: ms(150) }}>
      <span>{t.text}</span>
      {#if t.action}<button onclick={() => act(t)}>{t.action.label}</button>{/if}
    </div>
  {/each}
</div>

<style>
  .toasts { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 60; display: flex; flex-direction: column; gap: 8px; align-items: center; pointer-events: none; width: max-content; max-width: calc(100vw - 32px); transition: transform var(--t-med) var(--ease-out); }
  .toasts.phone { bottom: calc(var(--bottom-h) + env(safe-area-inset-bottom) + 14px); }
  .toasts.bar { transform: translate(-50%, -76px); }
  .toast { background: var(--text); color: var(--bg); padding: 10px 16px; border-radius: 10px; font-size: 14px; box-shadow: var(--shadow); display: flex; align-items: center; gap: 14px; }
  .toast.has-action { pointer-events: auto; padding-right: 8px; }
  .toast.bad { background: var(--bad); color: #fff; }
  .toast button { border: 0; background: none; color: var(--accent); font-weight: 600; font-size: 14px; padding: 4px 8px; border-radius: 6px; white-space: nowrap; }
  .toast button:hover { background: rgba(255, 255, 255, 0.12); }
</style>
