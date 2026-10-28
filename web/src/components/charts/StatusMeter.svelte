<script>
  // One bar split by document status; every part is labelled (status colours never stand alone).
  let { parts = [] } = $props(); // [{ key, label, count, color, href? }]
  const total = $derived(parts.reduce((s, p) => s + p.count, 0));
</script>

<div class="meter" role="img" aria-label={parts.map((p) => `${p.label} ${p.count}`).join(', ')}>
  {#each parts.filter((p) => p.count) as p (p.key)}
    <span style="flex-grow:{p.count};background:{p.color}" title="{p.label} {p.count}"></span>
  {:else}
    <span class="empty"></span>
  {/each}
</div>
<ul class="keys">
  {#each parts as p (p.key)}
    <li>
      <span class="dot" style="background:{p.color}"></span>
      {#if p.href}<a href={p.href}>{p.label}</a>{:else}{p.label}{/if}
      <b class="num">{p.count.toLocaleString('th-TH')}</b>
      <small class="muted">{total ? Math.round((p.count / total) * 100) : 0}%</small>
    </li>
  {/each}
</ul>

<style>
  .meter { display: flex; gap: 2px; height: 12px; border-radius: 6px; overflow: hidden; background: var(--subtle); }
  .meter span { min-width: 4px; }
  .meter .empty { flex: 1; }
  .keys { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; }
  .keys li { display: inline-flex; align-items: center; gap: 6px; }
  .keys a { color: var(--text); }
  .dot { width: 9px; height: 9px; border-radius: 50%; }
  b { font-weight: 600; }
</style>
