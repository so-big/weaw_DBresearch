<script>
  // Horizontal bars, largest first, each labelled with its value (no axis needed).
  let { items = [], color = 'var(--c-internal)', limit = 8 } = $props(); // [{ name, count, href? }]
  const shown = $derived(items.slice(0, limit));
  const max = $derived(Math.max(1, ...shown.map((i) => i.count)));
</script>

<ol class="rank">
  {#each shown as it (it.name)}
    <li>
      <span class="name">{#if it.href}<a href={it.href}>{it.name}</a>{:else}{it.name}{/if}</span>
      <span class="track"><i style="transform:scaleX({it.count / max});background:{color}"></i></span>
      <b class="num">{it.count.toLocaleString('th-TH')}</b>
    </li>
  {:else}
    <li class="muted none">ยังไม่มีเอกสารที่ติดหมวดหมู่นี้</li>
  {/each}
</ol>
{#if items.length > limit}<p class="more muted">และอีก {items.length - limit} รายการ</p>{/if}

<style>
  .rank { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }
  li { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(60px, 1fr) 3ch; gap: 10px; align-items: center; font-size: 13.5px; }
  .name { overflow-wrap: anywhere; line-height: 1.35; }
  .name a { color: var(--text); text-decoration: none; }
  .name a:hover { color: var(--primary-text); text-decoration: underline; }
  .track { height: 10px; background: var(--subtle); border-radius: 0 5px 5px 0; overflow: hidden; }
  .track i { display: block; height: 100%; border-radius: 0 5px 5px 0; transform-origin: left; transition: transform 400ms var(--ease-out); }
  b { text-align: right; font-weight: 600; }
  .none { display: block; }
  .more { font-size: 12.5px; margin-top: 8px; }
</style>
