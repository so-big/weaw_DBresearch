<script>
  // Search + filters. PC: filter column beside the results. Phone: quick chips + filter sheet.
  import { onMount, tick, untrack } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { get, errorText, fileUrl } from '../lib/api.js';
  import { route, setQuery } from '../lib/router.svelte.js';
  import { screen, ui, ms } from '../lib/state.svelte.js';
  import { openUpload } from '../lib/uploads.svelte.js';
  import { categoryGroups } from '../lib/catalog.js';
  import { STATUS, KIND, FUNDING, BE, thDate, snippetHtml } from '../lib/format.js';
  import FilterPanel from '../components/FilterPanel.svelte';
  import Icon from '../components/Icon.svelte';

  const PAGE = 20;
  // '' = the default order: relevance when searching, otherwise latest first.
  const sortsFor = (q) => [
    ...(q ? [['', 'เกี่ยวข้องที่สุด'], ['newest', 'อัปเดตล่าสุด']] : [['', 'อัปเดตล่าสุด']]),
    ['oldest', 'เก่าที่สุด'],
    ['reference', 'เลขที่สัญญา'],
    ['title', 'ชื่อเรื่อง ก–ฮ'],
  ];
  const LIST_KEYS = ['fiscal_year', 'funding_type', 'status', 'kind', 'category'];

  function readFilters(q) {
    const f = { q: q.get('q') || '', person: q.get('person') || '', mine: q.get('mine') === 'true', sort: q.get('sort') || '' };
    for (const k of LIST_KEYS) f[k] = q.getAll(k);
    return f;
  }
  const filters = $derived(readFilters(route.query));

  let items = $state([]);
  let total = $state(0);
  let facets = $state(null);
  let page = $state(1);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let groups = $state([]);
  let phoneQ = $state(''); // synced from the address by the load effect
  let qInput = $state();
  let seq = 0;

  onMount(() => {
    categoryGroups().then((g) => (groups = g)).catch(() => {});
  });

  function apiParams(f, extra = {}) {
    return {
      q: f.q || undefined,
      person: f.person || undefined,
      mine: f.mine || undefined,
      sort: f.sort || (f.q ? 'relevance' : 'newest'),
      ...Object.fromEntries(LIST_KEYS.map((k) => [k, f[k]])),
      ...extra,
    };
  }

  async function load(f, more = false) {
    const mine = ++seq;
    if (more) page += 1;
    else {
      page = 1;
      if (items.length) refreshing = true;
      else loading = true;
    }
    try {
      const res = await get('/documents', apiParams(f, { page, page_size: PAGE, with_facets: !more }));
      if (mine !== seq) return; // a newer search replaced this one
      items = more ? [...items, ...res.items] : res.items;
      total = res.total;
      if (res.facets) facets = res.facets;
      error = '';
    } catch (err) {
      if (mine === seq) error = errorText(err);
    } finally {
      if (mine === seq) loading = refreshing = false;
    }
  }

  // Reload whenever the address (filters) changes.
  $effect(() => {
    const f = filters;
    untrack(() => {
      load(f);
      phoneQ = f.q;
    });
  });

  // Phone: the bottom bar's search button focuses this box.
  let lastFocus = ui.searchFocus;
  $effect(() => {
    if (ui.searchFocus !== lastFocus) {
      lastFocus = ui.searchFocus;
      window.scrollTo({ top: 0, behavior: 'instant' });
      tick().then(() => qInput?.focus());
    }
  });
  onMount(() => {
    if (!screen.wide && ui.searchFocus) tick().then(() => qInput?.focus());
  });

  function update(next) {
    setQuery({ ...next, mine: next.mine ? 'true' : '' });
  }
  function clearAll() {
    update({ q: filters.q, sort: filters.sort });
  }

  let qTimer;
  function typeQ(e) {
    phoneQ = e.currentTarget.value;
    clearTimeout(qTimer);
    qTimer = setTimeout(() => update({ ...filters, q: phoneQ.trim() }), 300);
  }

  // Active filters as removable chips
  const chips = $derived.by(() => {
    const out = [];
    const names = new Map(groups.flatMap((g) => g.options.map((o) => [o.id, o.name_th])));
    for (const y of filters.fiscal_year) out.push({ k: 'fiscal_year', v: y, label: `ปีงบ ${Number(y) + BE}` });
    for (const v of filters.funding_type) out.push({ k: 'funding_type', v, label: FUNDING[v] || v });
    for (const v of filters.status) out.push({ k: 'status', v, label: STATUS[v] || v });
    for (const v of filters.kind) out.push({ k: 'kind', v, label: KIND[v] || v });
    for (const v of filters.category) out.push({ k: 'category', v, label: names.get(v) || 'หมวดหมู่' });
    if (filters.person) out.push({ k: 'person', label: `นักวิจัย: ${filters.person}` });
    if (filters.mine) out.push({ k: 'mine', label: 'ที่ฉันอัปโหลด' });
    return out;
  });
  function removeChip(c) {
    if (c.k === 'person') update({ ...filters, person: '' });
    else if (c.k === 'mine') update({ ...filters, mine: false });
    else update({ ...filters, [c.k]: filters[c.k].filter((x) => x !== c.v) });
  }

  // Phone quick chips: the two latest fiscal years, funding type, needs review.
  const quick = $derived.by(() => {
    const years = (facets?.fiscal_year || []).map((f) => String(f.value)).sort((a, b) => b - a).slice(0, 2);
    return [
      ...years.map((y) => ({ k: 'fiscal_year', v: y, label: `ปีงบ ${Number(y) + BE}` })),
      { k: 'funding_type', v: 'internal', label: 'ทุนภายใน' },
      { k: 'funding_type', v: 'external', label: 'ทุนภายนอก' },
      { k: 'status', v: 'needs_review', label: 'รอตรวจสอบ' },
    ];
  });
  function toggleQuick(c) {
    const on = filters[c.k].includes(c.v);
    update({ ...filters, [c.k]: on ? filters[c.k].filter((x) => x !== c.v) : [...filters[c.k], c.v] });
  }

  // ───── Phone filter sheet: edits a draft, shows the live count before applying ─────
  let sheet = $state(false);
  let draft = $state(null);
  let draftTotal = $state(null);
  let draftFacets = $state(null);
  let draftTimer;
  function openSheet() {
    draft = $state.snapshot(filters);
    draftTotal = total;
    draftFacets = facets;
    sheet = true;
  }
  function changeDraft(next) {
    draft = next;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(async () => {
      try {
        const res = await get('/documents', apiParams(next, { page_size: 1, with_facets: true }));
        draftTotal = res.total;
        draftFacets = res.facets;
      } catch {
        /* keep the last count */
      }
    }, 250);
  }
  function applySheet() {
    update(draft);
    sheet = false;
  }
  const activeCount = $derived(chips.length);
  const hasFilters = $derived(chips.length > 0);
</script>

<div class="layout" class:wide={screen.wide}>
  {#if screen.wide}
    <aside class="side card">
      <div class="side-head">
        <h3>ตัวกรอง</h3>
        <button class="link-btn" onclick={clearAll} disabled={!hasFilters}>ล้างทั้งหมด</button>
      </div>
      <FilterPanel value={filters} {facets} {groups} onchange={update} idp="pc" />
    </aside>
  {:else}
    <div class="phone-head">
      <div class="phone-search">
        <label class="psearch">
          <Icon name="search" size={18} />
          <input bind:this={qInput} value={phoneQ} oninput={typeQ} type="search" placeholder="ค้นหาเอกสาร" aria-label="ค้นหาเอกสาร" enterkeyhint="search" />
        </label>
        <button class="fbtn" onclick={openSheet}>
          <Icon name="filter" size={18} />ตัวกรอง
          {#if activeCount}<span class="n">{activeCount}</span>{/if}
        </button>
      </div>
      <div class="quick">
        {#each quick as c (c.k + c.v)}
          <button class="chip" aria-pressed={filters[c.k].includes(c.v)} onclick={() => toggleQuick(c)}>{c.label}</button>
        {/each}
      </div>
    </div>
  {/if}

  <section class="results">
    <div class="toolbar">
      <span class="total" aria-live="polite">
        {#if loading}กำลังค้นหา…{:else}พบ <b class="num">{total.toLocaleString('th-TH')}</b> รายการ{/if}
        {#if filters.q}<span class="muted"> สำหรับ “{filters.q}”</span>{/if}
      </span>
      <span class="spacer"></span>
      <label class="sort">
        <span class="muted">เรียงตาม</span>
        <select id="sort" value={filters.sort} onchange={(e) => update({ ...filters, sort: e.currentTarget.value })}>
          {#each sortsFor(filters.q) as [v, l] (v)}<option value={v}>{l}</option>{/each}
        </select>
      </label>
    </div>

    {#if screen.wide && chips.length}
      <div class="chips">
        {#each chips as c (c.k + (c.v ?? ''))}
          <span class="chip on enter">{c.label}<button class="x" onclick={() => removeChip(c)} aria-label="เอาตัวกรอง {c.label} ออก">✕</button></span>
        {/each}
        <button class="link-btn" onclick={clearAll}>ล้างทั้งหมด</button>
      </div>
    {/if}

    {#if error}
      <div class="notice bad">{error} <button class="link-btn" onclick={() => load(filters)}>ลองใหม่</button></div>
    {/if}

    {#if loading}
      <div class="list card">
        {#each Array(6) as _, i (i)}
          <div class="item skeleton"><div class="skel" style="width:90px"></div><div class="grow"><div class="skel" style="width:75%;height:14px"></div><div class="skel" style="width:45%;margin-top:8px"></div></div></div>
        {/each}
      </div>
    {:else if !items.length}
      <div class="empty card">
        {#if hasFilters || filters.q}
          <Icon name="search" size={30} />
          <p>ไม่พบเอกสารที่ตรงกับการค้นหา</p>
          {#if hasFilters}<button class="btn ghost" onclick={clearAll}>ล้างตัวกรองทั้งหมด</button>{/if}
        {:else}
          <Icon name="doc" size={30} />
          <p>ยังไม่มีเอกสารในระบบ</p>
          <button class="btn" onclick={openUpload}><Icon name="upload" size={17} />อัปโหลดไฟล์แรก</button>
        {/if}
      </div>
    {:else}
      <div class="list card" class:dim={refreshing}>
        {#each items as d (d.id)}
          <div class="item">
            <a class="cover" href="/documents/{d.id}" aria-label={d.title}></a>
            {#if screen.wide}
              <span class="cno">{d.reference_no || '—'}</span>
            {/if}
            <div class="grow">
              <div class="t">{@html snippetHtml(filters.q && d.title.includes(filters.q) ? d.title.replaceAll(filters.q, `[[${filters.q}]]`) : d.title)}</div>
              {#if d.snippet}<div class="snip">{@html snippetHtml(d.snippet)}</div>{/if}
              <div class="meta">
                {#if !screen.wide && d.reference_no}<span class="cno">{d.reference_no}</span>{/if}
                {#if d.owners?.length}<span>{d.owners.join(', ')}</span>{/if}
                {#if d.fiscal_year_be}<span>ปีงบ {d.fiscal_year_be}</span>{/if}
                {#if d.funding_type}<span>{FUNDING[d.funding_type]}</span>{/if}
              </div>
            </div>
            <div class="side-meta">
              <span class="badge {d.status}">{STATUS[d.status]}</span>
              <span class="muted date">{thDate(d.updated_at)}</span>
              {#if !screen.wide}
                <a class="btn small dl" href={fileUrl(d.id)} aria-label="ดาวน์โหลด {d.title}"><Icon name="download" size={15} /></a>
              {/if}
            </div>
          </div>
        {/each}
      </div>
      {#if items.length < total}
        <button class="btn ghost more" onclick={() => load(filters, true)}>แสดงเพิ่ม ({(total - items.length).toLocaleString('th-TH')} รายการ)</button>
      {/if}
    {/if}
  </section>
</div>

{#if sheet}
  <div class="scrim" transition:fade={{ duration: ms(200) }} onclick={() => (sheet = false)} role="presentation"></div>
  <div class="sheet" role="dialog" aria-modal="true" aria-label="ตัวกรอง" transition:fly={{ y: 500, duration: ms(240), easing: cubicOut, opacity: 1 }}>
    <div class="grab"></div>
    <div class="sheet-head">
      <h3>ตัวกรอง</h3>
      <select id="sheet-sort" value={draft.sort} onchange={(e) => changeDraft({ ...draft, sort: e.currentTarget.value })} aria-label="เรียงตาม">
        {#each sortsFor(draft.q) as [v, l] (v)}<option value={v}>{l}</option>{/each}
      </select>
    </div>
    <div class="sheet-body">
      <FilterPanel value={draft} facets={draftFacets} {groups} onchange={changeDraft} idp="ph" />
    </div>
    <div class="sheet-foot">
      <button class="btn ghost" onclick={() => changeDraft({ q: draft.q, sort: draft.sort, person: '', mine: false, ...Object.fromEntries(LIST_KEYS.map((k) => [k, []])) })}>ล้าง</button>
      <button class="btn grow" onclick={applySheet}>แสดง {draftTotal === null ? '' : draftTotal.toLocaleString('th-TH')} รายการ</button>
    </div>
  </div>
{/if}

<style>
  .layout { display: flex; flex-direction: column; gap: 12px; }
  .layout.wide { display: grid; grid-template-columns: 256px minmax(0, 1fr); gap: 20px; align-items: start; }
  .side { position: sticky; top: calc(var(--header-h) + 20px); max-height: calc(100vh - var(--header-h) - 40px); overflow: auto; padding: 12px 10px; }
  .side-head { display: flex; justify-content: space-between; align-items: center; padding: 2px 6px 8px; }
  .results { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .total { font-size: 14px; }
  .sort { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .sort select, .sheet-head select { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 5px 8px; font-size: 14px; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .chips .chip { padding-right: 5px; }

  .list { overflow: hidden; transition: opacity 120ms; }
  .list.dim { opacity: 0.55; }
  .item { position: relative; display: grid; grid-template-columns: 104px minmax(0, 1fr) auto; gap: 14px; padding: 13px 16px; border-top: 1px solid var(--border); color: inherit; text-decoration: none; transition: background var(--t-fast); }
  .item:first-child { border-top: 0; }
  .item:hover { background: var(--subtle); }
  .cover { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .cover:focus-visible { outline-offset: -3px; }
  .item .cno { padding-top: 2px; }
  .grow { min-width: 0; flex: 1; }
  .t { font-weight: 500; font-size: 15px; line-height: 1.45; overflow-wrap: anywhere; }
  .snip { font-size: 13px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; color: var(--muted); margin-top: 4px; }
  .side-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; font-size: 12px; }
  .date { white-space: nowrap; }
  .skeleton { pointer-events: none; }
  .empty { padding: 40px 16px; display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; color: var(--muted); }
  .empty p { color: var(--text); }
  .more { align-self: center; }

  /* phone */
  .phone-head { display: flex; flex-direction: column; gap: 10px; }
  .phone-search { display: flex; gap: 8px; }
  .psearch { flex: 1; display: flex; align-items: center; gap: 8px; background: var(--surface); border: 1px solid var(--border-strong); border-radius: 12px; padding: 0 12px; color: var(--muted); transition: border-color var(--t-fast); }
  .psearch:focus-within { border-color: var(--primary); }
  .psearch input { border: 0; background: none; outline: none; min-width: 0; width: 100%; padding: 10px 0; font-size: 16px; color: var(--text); }
  .fbtn { position: relative; display: flex; align-items: center; gap: 6px; border: 1px solid var(--border-strong); background: var(--surface); border-radius: 12px; padding: 0 12px; font-size: 14px; font-weight: 500; }
  .fbtn .n { position: absolute; top: -7px; right: -7px; min-width: 19px; height: 19px; border-radius: 999px; background: var(--primary); color: var(--on-primary); font-size: 11px; font-weight: 600; display: grid; place-items: center; padding: 0 5px; }
  .quick { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -12px; padding: 0 12px 2px; }
  .quick::-webkit-scrollbar { display: none; }
  .quick .chip { flex: none; }
  .layout:not(.wide) .item { grid-template-columns: minmax(0, 1fr) auto; padding: 12px; gap: 10px; }
  .layout:not(.wide) .t { font-size: 14.5px; }
  .dl { position: relative; z-index: 2; min-height: 34px; padding: 4px 10px; margin-top: 4px; }

  .scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 40; }
  .sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 41; max-height: 88vh; background: var(--surface); border-radius: 20px 20px 0 0; display: flex; flex-direction: column; box-shadow: var(--shadow); }
  .grab { width: 38px; height: 4px; border-radius: 2px; background: var(--border-strong); margin: 8px auto 4px; }
  .sheet-head { display: flex; justify-content: space-between; align-items: center; padding: 2px 16px 8px; }
  .sheet-body { overflow: auto; padding: 0 10px; flex: 1; overscroll-behavior: contain; }
  .sheet-foot { display: flex; gap: 8px; padding: 10px 16px calc(12px + env(safe-area-inset-bottom)); border-top: 1px solid var(--border); }
  .sheet-foot .btn { min-height: 46px; }
  .sheet-foot .grow { flex: 1; }
</style>
