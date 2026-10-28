<script>
  // Stacked (or single) columns on one baseline with a hover tooltip per column.
  // data: [{ label, tip?, values: { key: number } }], series: [{ key, label, color }]
  import { niceTicks, topRounded, short, full } from './scale.js';

  let { data = [], series = [], height = 220, format = full, axisFormat = short, unit = '' } = $props();
  let width = $state(600);
  let hover = $state(null);

  const M = { top: 8, right: 8, bottom: 26, left: 44 };
  const plotW = $derived(Math.max(10, width - M.left - M.right));
  const plotH = $derived(height - M.top - M.bottom);
  const totals = $derived(data.map((d) => series.reduce((s, x) => s + (d.values[x.key] || 0), 0)));
  const scale = $derived(niceTicks(Math.max(0, ...totals)));
  const band = $derived(plotW / Math.max(1, data.length));
  const barW = $derived(Math.min(24, band * 0.6));
  const y = (v) => plotH - (v / scale.max) * plotH;

  // Segments bottom-up with a 2px surface gap between touching fills; only the top one is rounded.
  const columns = $derived(
    data.map((d, i) => {
      let acc = 0;
      const parts = series
        .map((s) => ({ s, v: d.values[s.key] || 0 }))
        .filter((p) => p.v > 0)
        .map((p) => {
          const y0 = y(acc);
          acc += p.v;
          const y1 = y(acc);
          return { ...p, y: y1, h: Math.max(0, y0 - y1) };
        });
      const top = parts.length - 1;
      const x = i * band + (band - barW) / 2;
      return {
        d,
        i,
        x,
        total: totals[i],
        parts: parts.map((p, j) => ({
          ...p,
          // lower segments give up their top 2px: the surface gap under the next one
          path: j === top ? topRounded(x, p.y, barW, p.h) : `M${x},${p.y + 2}H${x + barW}V${p.y + p.h}H${x}Z`,
        })),
      };
    }),
  );
  const labelEvery = $derived(Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 54)))));
</script>

<div class="wrap" bind:clientWidth={width} role="img" aria-label="กราฟแท่ง {data.length} ช่วง">
  <svg {width} {height} viewBox="0 0 {width} {height}">
    <g transform="translate({M.left},{M.top})">
      {#each scale.ticks as t (t)}
        <line x1="0" x2={plotW} y1={y(t)} y2={y(t)} class="grid" />
        <text x="-8" y={y(t)} dy="0.32em" text-anchor="end" class="axis">{axisFormat(t)}</text>
      {/each}
      {#each columns as c (c.i)}
        <g class:dim={hover !== null && hover !== c.i}>
          {#each c.parts as p (p.s.key)}<path d={p.path} fill={p.s.color} />{/each}
        </g>
        {#if c.i % labelEvery === 0}
          <text x={c.x + barW / 2} y={plotH + 17} text-anchor="middle" class="axis">{c.d.label}</text>
        {/if}
        <rect
          x={c.i * band}
          y="0"
          width={band}
          height={plotH}
          fill="transparent"
          role="presentation"
          onpointerenter={() => (hover = c.i)}
          onpointerleave={() => (hover = null)}
        />
      {/each}
    </g>
  </svg>
  {#if hover !== null}
    {@const c = columns[hover]}
    <div class="tip" style="left:{Math.min(Math.max(M.left + c.x + barW / 2, 80), width - 80)}px">
      <b>{c.d.tip || c.d.label}</b>
      {#each series as s (s.key)}
        {#if series.length > 1 || c.d.values[s.key]}
          <span><i style="background:{s.color}"></i>{s.label}<em>{format(c.d.values[s.key] || 0)}{unit}</em></span>
        {/if}
      {/each}
      {#if series.length > 1}<span class="tot">รวม<em>{format(c.total)}{unit}</em></span>{/if}
    </div>
  {/if}
</div>

<style>
  .wrap { position: relative; width: 100%; }
  svg { display: block; overflow: visible; }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .axis { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  g.dim { opacity: 0.45; transition: opacity var(--t-fast); }
  .tip {
    position: absolute; top: 0; transform: translateX(-50%); pointer-events: none; z-index: 2;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow);
    padding: 8px 10px; font-size: 12.5px; display: flex; flex-direction: column; gap: 2px; min-width: 150px;
  }
  .tip span { display: flex; align-items: center; gap: 6px; color: var(--muted); }
  .tip i { width: 8px; height: 8px; border-radius: 2px; flex: none; }
  .tip em { margin-left: auto; font-style: normal; color: var(--text); font-variant-numeric: tabular-nums; padding-left: 12px; }
  .tip .tot { border-top: 1px solid var(--border); margin-top: 2px; padding-top: 3px; color: var(--text); }
</style>
