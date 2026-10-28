<script>
  // Filter groups with live counts. Ticks within a group = "any of these"; groups combine with AND.
  // `value` is a plain filters object; every change calls onchange with a new object.
  import { STATUS, KIND, FUNDING, BE } from '../lib/format.js';

  let { value, facets, groups = [], onchange, idp = 'f' } = $props();

  const SHOW = 5;
  let expanded = $state({});
  let person = $state(''); // synced from `value` below
  let personTimer;

  $effect(() => {
    person = value.person || '';
  });

  const countMap = (list) => new Map((list || []).map((f) => [String(f.value), f.count]));
  const years = $derived.by(() => {
    const counts = countMap(facets?.fiscal_year);
    const all = new Set([...counts.keys(), ...(value.fiscal_year || [])].map(String));
    return [...all]
      .map(Number)
      .sort((a, b) => b - a)
      .map((y) => ({ v: String(y), label: `พ.ศ. ${y + BE}`, n: counts.get(String(y)) ?? 0 }));
  });
  const fromLabels = (labels, list) => {
    const counts = countMap(list);
    return Object.entries(labels).map(([v, label]) => ({ v, label, n: counts.get(v) ?? 0 }));
  };
  const catCounts = $derived(countMap(facets?.categories));

  const sections = $derived([
    { key: 'fiscal_year', label: 'ปีงบประมาณ', open: true, options: years },
    { key: 'funding_type', label: 'ประเภทเงินทุน', open: true, options: fromLabels(FUNDING, facets?.funding_type) },
    { key: 'status', label: 'สถานะ', open: true, options: fromLabels(STATUS, facets?.status) },
    { key: 'kind', label: 'ประเภทเอกสาร', open: false, options: fromLabels(KIND, facets?.kind) },
    ...groups.map((g) => ({
      key: 'category',
      id: g.id,
      label: g.name_th,
      open: false,
      options: g.options
        .filter((o) => o.active || (value.category || []).includes(o.id))
        .map((o) => ({ v: o.id, label: o.name_th, n: catCounts.get(o.id) ?? 0 })),
    })),
  ]);

  function toggle(key, v, on) {
    const current = new Set((value[key] || []).map(String));
    if (on) current.add(v);
    else current.delete(v);
    onchange({ ...value, [key]: [...current] });
  }
  const selectedIn = (s) => s.options.filter((o) => (value[s.key] || []).map(String).includes(o.v)).length;

  function typePerson(e) {
    person = e.currentTarget.value;
    clearTimeout(personTimer);
    personTimer = setTimeout(() => onchange({ ...value, person: person.trim() }), 300);
  }
</script>

<div class="panel">
  {#each sections as s (s.id || s.key)}
    {#if s.options.length}
      <details open={s.open || selectedIn(s) > 0}>
        <summary>
          {s.label}
          {#if selectedIn(s)}<span class="n">{selectedIn(s)}</span>{/if}
        </summary>
        <div class="opts">
          {#each s.options as o, i (o.v)}
            {@const on = (value[s.key] || []).map(String).includes(o.v)}
            {#if i < SHOW || expanded[s.id || s.key] || on}
              <label class="opt" class:zero={!o.n && !on}>
                <input
                  id="{idp}-{s.key}-{o.v}"
                  type="checkbox"
                  checked={on}
                  disabled={!o.n && !on}
                  onchange={(e) => toggle(s.key, o.v, e.currentTarget.checked)}
                />
                <span class="l">{o.label}</span>
                <span class="c num">{o.n}</span>
              </label>
            {/if}
          {/each}
          {#if s.options.length > SHOW && !expanded[s.id || s.key]}
            <button class="link-btn more" type="button" onclick={() => (expanded[s.id || s.key] = true)}>ดูเพิ่มอีก {s.options.length - SHOW} รายการ</button>
          {/if}
        </div>
      </details>
    {/if}
  {/each}

  <details open={!!value.person}>
    <summary>ชื่อนักวิจัย {#if value.person}<span class="n">1</span>{/if}</summary>
    <div class="opts">
      <input id="{idp}-person" class="input" value={person} oninput={typePerson} placeholder="พิมพ์บางส่วนของชื่อ" autocomplete="off" />
    </div>
  </details>

  <label class="switch">
    <span>เฉพาะที่ฉันอัปโหลด</span>
    <input id="{idp}-mine" type="checkbox" role="switch" checked={!!value.mine} onchange={(e) => onchange({ ...value, mine: e.currentTarget.checked })} />
  </label>
</div>

<style>
  .panel { display: flex; flex-direction: column; }
  details { border-top: 1px solid var(--border); }
  details:first-child { border-top: 0; }
  summary { list-style: none; display: flex; align-items: center; gap: 6px; padding: 10px 6px; font-size: 14px; font-weight: 600; cursor: pointer; border-radius: 6px; }
  summary::-webkit-details-marker { display: none; }
  summary::after { content: ''; margin-left: auto; width: 7px; height: 7px; border-right: 1.6px solid var(--muted); border-bottom: 1.6px solid var(--muted); transform: rotate(45deg) translateY(-2px); transition: transform var(--t-fast) var(--ease-out); }
  details[open] summary::after { transform: rotate(-135deg) translateY(-1px); }
  .n { font-size: 11px; font-weight: 600; background: var(--accent-soft); color: var(--accent-text); border-radius: 999px; padding: 0 7px; }
  .opts { display: flex; flex-direction: column; padding: 0 2px 10px; }
  .opt { display: flex; align-items: center; gap: 10px; padding: 6px; border-radius: 7px; font-size: 14px; cursor: pointer; transition: background var(--t-fast); }
  .opt:hover { background: var(--subtle); }
  .opt input { accent-color: var(--primary); width: 17px; height: 17px; margin: 0; flex: none; }
  .l { flex: 1; min-width: 0; line-height: 1.35; }
  .c { font-size: 12px; color: var(--muted); }
  .zero { color: var(--faint); cursor: default; }
  .zero .c { color: var(--faint); }
  .more { align-self: flex-start; font-size: 13px; padding: 4px 6px; }
  .switch { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px 6px; border-top: 1px solid var(--border); font-size: 14px; font-weight: 600; cursor: pointer; }
  .switch input { appearance: none; width: 38px; height: 22px; border-radius: 999px; background: var(--border-strong); position: relative; cursor: pointer; margin: 0; flex: none; transition: background var(--t-fast); }
  .switch input::after { content: ''; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: var(--surface); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25); transition: transform var(--t-fast) var(--ease-out); }
  .switch input:checked { background: var(--primary); }
  .switch input:checked::after { transform: translateX(16px); }
</style>
