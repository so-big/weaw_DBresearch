<script>
  import { FACULTY } from '../../lib/format.js';
  // Contract-number coverage: one small tile per running number (R{year}{series}{001…}).
  // Filled = a file is stored; outlined = missing. A row per year + series.
  let { rows = [] } = $props(); // [{ year_be, series, highest, stored, missing: ['R2568E004', …] }]
  const FIRST = 12;
  let open = $state({}); // row key → show every missing number

  // The series letter is the faculty that issued the number (E = engineering), not the funding type.
  const SERIES = Object.fromEntries(Object.entries(FACULTY).map(([k, v]) => [k, { label: v, color: 'var(--c-internal)' }]));
  const tiles = (r) => {
    const missing = new Set(r.missing);
    return Array.from({ length: r.highest }, (_, i) => {
      const no = `R${r.year_be}${r.series}${String(i + 1).padStart(3, '0')}`;
      return { no, n: i + 1, have: !missing.has(no) };
    });
  };
</script>

<div class="rows">
  {#each rows as r (r.year_be + r.series)}
    {@const s = SERIES[r.series] || { label: `คณะรหัส ${r.series}`, color: 'var(--c-unset)' }}
    <div class="series">
      <div class="head">
        <b class="num">{r.year_be}</b>
        <span class="tag" style="--c:{s.color}">{r.series} · {s.label}</span>
        <span class="muted count">มี {r.stored} จาก {r.highest}{r.missing.length ? ` · ขาด ${r.missing.length}` : ' · ครบ'}</span>
      </div>
      <div class="tiles">
        {#each tiles(r) as t (t.n)}
          {#if t.have}
            <a class="tile have" style="--c:{s.color}" href="/documents?q={t.no}" title="{t.no} · มีในระบบ" aria-label="{t.no} มีในระบบ"></a>
          {:else}
            <span class="tile miss" title="{t.no} · ยังไม่มีไฟล์ในระบบ" aria-label="{t.no} ยังไม่มีไฟล์"></span>
          {/if}
        {/each}
      </div>
      {#if r.missing.length}
        {@const key = `${r.year_be}${r.series}`}
        <div class="list">
          <span class="muted">เลขที่ขาด</span>
          <ul>
            {#each open[key] ? r.missing : r.missing.slice(0, FIRST) as no (no)}<li class="cno">{no}</li>{/each}
          </ul>
          {#if r.missing.length > FIRST}
            <button class="link-btn" onclick={() => (open[key] = !open[key])}>{open[key] ? 'ย่อ' : `แสดงทั้งหมด (${r.missing.length})`}</button>
          {/if}
        </div>
      {/if}
    </div>
  {:else}
    <p class="muted">ยังไม่มีเอกสารที่มีเลขที่สัญญา</p>
  {/each}
</div>

<style>
  .rows { display: flex; flex-direction: column; gap: 16px; }
  .series { display: flex; flex-direction: column; align-items: flex-start; gap: 7px; }
  .head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; font-size: 13.5px; }
  .head b { font-family: var(--f-display); font-weight: 500; font-size: 17px; }
  .tag { font-size: 12px; font-weight: 600; padding: 0 8px; border-radius: 999px; color: var(--text); background: color-mix(in srgb, var(--c) 16%, transparent); }
  .count { font-size: 12.5px; }
  .tiles { display: flex; flex-wrap: wrap; gap: 3px; }
  .tile { width: 14px; height: 14px; border-radius: 3px; display: block; }
  .tile.have { background: var(--c); transition: transform var(--t-fast); }
  .tile.have:hover { transform: scale(1.25); }
  .tile.miss { border: 1.5px dashed var(--warn); background: var(--warn-soft); }
  .list { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; font-size: 12.5px; min-width: 0; }
  .list ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px; }
  .list .cno { font-size: 11.5px; color: var(--warn); background: var(--warn-soft); border-radius: 6px; padding: 1px 6px; }
  .list .link-btn { padding: 2px 0; font-size: 12.5px; }
  @media (max-width: 767px) { .tile { width: 16px; height: 16px; } .tiles { gap: 4px; } }
</style>
