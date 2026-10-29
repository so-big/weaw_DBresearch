<script>
  // Lines over time (one axis), with a soft area under a single series and a crosshair tooltip.
  // data: [{ label, tip?, values: { key: number } }], series: [{ key, label, color }]
  import { niceTicks, short, full } from './scale.js';

  let { data = [], series = [], height = 200, format = full, area = true } = $props();
  let width = $state(600);
  let hover = $state(null);

  const M = { top: 10, right: 12, bottom: 26, left: 36 };
  const plotW = $derived(Math.max(10, width - M.left - M.right));
  const plotH = $derived(height - M.top - M.bottom);
  const max = $derived(Math.max(0, ...data.flatMap((d) => series.map((s) => d.values[s.key] || 0))));
  const scale = $derived(niceTicks(max));
  const x = (i) => (data.length < 2 ? plotW / 2 : (i / (data.length - 1)) * plotW);
  const y = (v) => plotH - (v / scale.max) * plotH;
  const lines = $derived(
    series.map((s) => {
      const pts = data.map((d, i) => [x(i), y(d.values[s.key] || 0)]);
      const line = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px},${py}`).join('');
      return { s, pts, line, fill: `${line}L${x(data.length - 1)},${plotH}L${x(0)},${plotH}Z` };
    }),
  );
  const labelEvery = $derived(Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 62)))));

  function move(e) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - box.left - M.left;
    hover = Math.max(0, Math.min(data.length - 1, Math.round((px / plotW) * (data.length - 1))));
  }
</script>

<div class="wrap" bind:clientWidth={width} role="img" aria-label="กราฟเส้น {data.length} จุด">
  <svg {width} {height} viewBox="0 0 {width} {height}" onpointermove={move} onpointerleave={() => (hover = null)} role="presentation">
    <g transform="translate({M.left},{M.top})">
      {#each scale.ticks as t (t)}
        <line x1="0" x2={plotW} y1={y(t)} y2={y(t)} class="grid" />
        <text x="-8" y={y(t)} dy="0.32em" text-anchor="end" class="axis">{short(t)}</text>
      {/each}
      {#each data as d, i (i)}
        {#if i === data.length - 1 || (i % labelEvery === 0 && data.length - 1 - i >= labelEvery * 0.75)}
          <text x={x(i)} y={plotH + 17} text-anchor={i === data.length - 1 ? 'end' : i === 0 ? 'start' : 'middle'} class="axis">{d.label}</text>
        {/if}
      {/each}
      {#if area && series.length === 1}<path d={lines[0].fill} fill="var(--c-area)" />{/if}
      {#each lines as l (l.s.key)}
        <path d={l.line} fill="none" stroke={l.s.color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        {@const last = l.pts[l.pts.length - 1]}
        {#if last && hover === null}<circle cx={last[0]} cy={last[1]} r="4" fill={l.s.color} stroke="var(--surface)" stroke-width="2" />{/if}
      {/each}
      {#if hover !== null}
        <line x1={x(hover)} x2={x(hover)} y1="0" y2={plotH} class="cross" />
        {#each lines as l (l.s.key)}
          <circle cx={l.pts[hover][0]} cy={l.pts[hover][1]} r="4.5" fill={l.s.color} stroke="var(--surface)" stroke-width="2" />
        {/each}
      {/if}
    </g>
  </svg>
  {#if hover !== null}
    {@const d = data[hover]}
    <div class="tip" style="left:{Math.min(Math.max(M.left + x(hover), 80), width - 80)}px">
      <b>{d.tip || d.label}</b>
      {#each series as s (s.key)}
        <span><i style="background:{s.color}"></i>{s.label}<em>{format(d.values[s.key] || 0)}</em></span>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap { position: relative; width: 100%; touch-action: pan-y; }
  svg { display: block; overflow: visible; }
  .grid { stroke: var(--grid); stroke-width: 1; }
  .cross { stroke: var(--border-strong); stroke-width: 1; }
  .axis { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .tip {
    position: absolute; top: 0; transform: translateX(-50%); pointer-events: none; z-index: 2;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow);
    padding: 8px 10px; font-size: 12.5px; display: flex; flex-direction: column; gap: 2px; min-width: 140px;
  }
  .tip span { display: flex; align-items: center; gap: 6px; color: var(--muted); }
  .tip i { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .tip em { margin-left: auto; font-style: normal; color: var(--text); font-variant-numeric: tabular-nums; padding-left: 12px; }
</style>
