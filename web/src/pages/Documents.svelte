<script>
  // Search + filters. A maroon masthead holds the search box and quick figures; below it the
  // PC gets a filter column, phones get quick chips + a filter sheet.
  // `section`: 'contracts' (สัญญาทุนวิจัย) or 'proposals' (ทุนพัฒนาข้อเสนอ, DESIGN §11). In
  // proposals, `?view=other` lists the programme papers (calls, yearly approvals).
  import { onMount, tick, untrack } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { SvelteMap } from 'svelte/reactivity';
  import { get, errorText, fileUrl, zipUrl, exportUrl, downloadUrl } from '../lib/api.js';
  import { route, setQuery } from '../lib/router.svelte.js';
  import { screen, ui, ms, session, isAdmin, toast } from '../lib/state.svelte.js';
  import { trashDocs } from '../lib/trash.js';
  import Modal from '../components/Modal.svelte';
  import { openUpload } from '../lib/uploads.svelte.js';
  import { categoryGroups } from '../lib/catalog.js';
  import { STATUS, KIND, FUNDING, FUNDING_SOURCE, PROJECT_STATE, BE, thDate, money, snippetHtml } from '../lib/format.js';
  import { highlightSegments } from '../lib/highlight.js';
  import FilterPanel from '../components/FilterPanel.svelte';
  import { sheet as sheetGesture } from '../lib/sheet.js';
  import Icon from '../components/Icon.svelte';

  let { section = 'contracts' } = $props();
  const grants = $derived(section === 'proposals');
  const base = $derived(grants ? '/proposals' : '/documents');

  /** The inline viewer opened at the page the search snippet came from. */
  function hitUrl(d) {
    const { kind, version_no } = d.snippet_file;
    return `${fileUrl(d.id, { inline: true, [kind === 'main' ? 'version' : kind]: version_no })}#page=${d.snippet_page}`;
  }
  const other = $derived(grants && route.query.get('view') === 'other');
  const apiSection = $derived(other ? 'other' : section);

  const PAGE = 20;
  // '' = the default order: relevance when searching, otherwise latest first.
  const sortsFor = (q) => [
    ...(q ? [['', 'เกี่ยวข้องที่สุด'], ['newest', 'อัปเดตล่าสุด']] : [['', 'อัปเดตล่าสุด']]),
    ['oldest', 'เก่าที่สุด'],
    ...(grants ? [] : [['reference', 'เลขที่สัญญา']]),
    ['title', 'ชื่อเรื่อง ก–ฮ'],
  ];
  const LIST_KEYS = $derived(
    grants
      ? ['fiscal_year', 'funding_source', 'status', 'department', 'research_area']
      : ['fiscal_year', 'funding_type', 'funding_source', 'status', 'kind', 'category'],
  );

  function readFilters(q) {
    // project: '' = active projects (default), 'closed' = the archive, 'all' = both.
    // Proposal grants also have 'overdue' and 'cancelled'.
    const f = { q: q.get('q') || '', person: q.get('person') || '', mine: q.get('mine') === 'true', sort: q.get('sort') || '', project: q.get('project') || '', view: q.get('view') || '' };
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

  // Proposal grants: the radio picks a state ('' = still running, overdue included).
  const stateParam = (p) => (p === 'all' ? undefined : p ? [p] : ['active']);
  function apiParams(f, extra = {}) {
    const archive = apiSection === 'contracts'
      ? { project: f.project === 'all' ? undefined : f.project === 'closed' ? 'closed' : 'open' }
      : apiSection === 'proposals'
        ? { state: stateParam(f.project) }
        : {};
    return {
      section: apiSection,
      q: f.q || undefined,
      person: f.person || undefined,
      mine: f.mine || undefined,
      ...archive,
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

  // Masthead figures: the whole library, not the current filter.
  const now = new Date();
  const thisFY = now.getMonth() >= 9 ? now.getFullYear() + 1 : now.getFullYear(); // Oct–Sep
  let stats = $state(null);
  onMount(() => {
    get('/documents', { section, page_size: 1, with_facets: true })
      .then((r) => {
        const by = (list, v) => list?.find((f) => String(f.value) === String(v))?.count || 0;
        stats = {
          total: r.total,
          review: by(r.facets?.status, 'needs_review') + by(r.facets?.status, 'failed'),
          year: by(r.facets?.fiscal_year, thisFY),
          overdue: by(r.facets?.state, 'overdue'),
        };
      })
      .catch(() => {});
  });
  const firstName = $derived((session.user?.display_name || '').split(' ')[0]);
  function onlyFilter(key, value) {
    const on = filters[key].length === 1 && filters[key][0] === String(value);
    update({ ...filters, [key]: on ? [] : [String(value)] });
  }
  function submitQ(e) {
    e.preventDefault();
    clearTimeout(qTimer);
    update({ ...filters, q: phoneQ.trim() });
    qInput?.blur();
  }
  function clearQ() {
    phoneQ = '';
    clearTimeout(qTimer);
    update({ ...filters, q: '' });
    qInput?.focus();
  }

  function update(next) {
    setQuery({ ...next, mine: next.mine ? 'true' : '' });
  }
  function clearAll() {
    update({ q: filters.q, sort: filters.sort, project: '', view: filters.view });
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
    for (const v of filters.funding_type || []) out.push({ k: 'funding_type', v, label: FUNDING[v] || v });
    for (const v of filters.funding_source) out.push({ k: 'funding_source', v, label: FUNDING_SOURCE[v] || v });
    for (const v of filters.department || []) out.push({ k: 'department', v, label: v });
    for (const v of filters.research_area || []) out.push({ k: 'research_area', v, label: v });
    for (const v of filters.status) out.push({ k: 'status', v, label: STATUS[v] || v });
    for (const v of filters.kind || []) out.push({ k: 'kind', v, label: KIND[v] || v });
    for (const v of filters.category || []) out.push({ k: 'category', v, label: names.get(v) || 'หมวดหมู่' });
    if (filters.person) out.push({ k: 'person', label: `นักวิจัย: ${filters.person}` });
    if (filters.mine) out.push({ k: 'mine', label: 'ที่ฉันอัปโหลด' });
    if (filters.project && grants) out.push({ k: 'project', label: filters.project === 'all' ? 'ทุกสถานะ' : PROJECT_STATE[filters.project] || filters.project });
    else if (filters.project) out.push({ k: 'project', label: filters.project === 'closed' ? 'โครงการที่ปิดแล้ว' : 'รวมโครงการที่ปิดแล้ว' });
    return out;
  });
  function removeChip(c) {
    if (c.k === 'person') update({ ...filters, person: '' });
    else if (c.k === 'mine') update({ ...filters, mine: false });
    else if (c.k === 'project') update({ ...filters, project: '' });
    else update({ ...filters, [c.k]: filters[c.k].filter((x) => x !== c.v) });
  }

  // Phone quick chips: the two latest fiscal years, funding type, needs review.
  const quick = $derived.by(() => {
    const years = (facets?.fiscal_year || []).map((f) => String(f.value)).sort((a, b) => b - a).slice(0, 2);
    if (grants)
      return [
        ...years.map((y) => ({ k: 'fiscal_year', v: y, label: `ปีงบ ${Number(y) + BE}` })),
        { k: 'project', v: 'overdue', label: 'เกินกำหนด' },
        { k: 'project', v: 'closed', label: 'ปิดทุนแล้ว' },
        { k: 'project', v: 'cancelled', label: 'ยกเลิก' },
        { k: 'status', v: 'needs_review', label: 'รอตรวจสอบ' },
      ];
    return [
      ...years.map((y) => ({ k: 'fiscal_year', v: y, label: `ปีงบ ${Number(y) + BE}` })),
      { k: 'funding_type', v: 'internal', label: 'ทุนภายใน' },
      { k: 'funding_type', v: 'external', label: 'ทุนภายนอก' },
      { k: 'status', v: 'needs_review', label: 'รอตรวจสอบ' },
      { k: 'project', v: 'closed', label: 'ปิดโครงการแล้ว' },
    ];
  });
  // Matches hidden in the archive (counted without the project filter).
  const archived = $derived.by(() => {
    if (filters.project || other) return 0;
    const count = (list, v) => (list || []).find((f) => f.value === v)?.count || 0;
    return grants ? count(facets?.state, 'closed') + count(facets?.state, 'cancelled') : count(facets?.project, 'closed');
  });
  const quickOn = (c) => (c.k === 'project' ? filters.project === c.v : filters[c.k].includes(c.v));
  function toggleQuick(c) {
    if (c.k === 'project') return update({ ...filters, project: filters.project === c.v ? '' : c.v });
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

  // ───── Select mode: pick documents (across searches) to zip-download or trash together ─────
  const MAX_PICK = 100; // the server's limit for one zip / one trash request
  let selecting = $state(false);
  const picked = new SvelteMap(); // id → the summary row, so picks survive a new search
  let confirmTrash = $state(false);
  let trashing = $state(false);
  const editable = (d) => isAdmin() || d.uploaded_by === session.user?.id;
  const pickedList = $derived([...picked.values()]);
  const deletable = $derived(pickedList.filter(editable));
  const allShown = $derived(items.length > 0 && items.every((d) => picked.has(d.id)));

  function startSelect() {
    selecting = true;
  }
  function stopSelect() {
    selecting = false;
    picked.clear();
  }
  function toggle(d) {
    if (picked.has(d.id)) picked.delete(d.id);
    else if (picked.size >= MAX_PICK) toast(`เลือกได้ครั้งละไม่เกิน ${MAX_PICK} รายการ`, 'bad');
    else picked.set(d.id, d);
  }
  function toggleAll() {
    if (allShown) {
      for (const d of items) picked.delete(d.id);
      return;
    }
    for (const d of items) {
      if (picked.size >= MAX_PICK) {
        toast(`เลือกได้ครั้งละไม่เกิน ${MAX_PICK} รายการ`, 'bad');
        break;
      }
      picked.set(d.id, d);
    }
  }
  // Spreadsheet of every match of the current filters (the server caps it).
  const EXPORT_MAX = 5000;
  const exportable = $derived(!loading && total > 0 && total <= EXPORT_MAX);
  const exportHint = $derived(
    loading ? '' : total === 0 ? 'ไม่มีรายการให้ส่งออก' : total > EXPORT_MAX ? `ส่งออกได้ไม่เกิน ${EXPORT_MAX.toLocaleString('th-TH')} รายการ กรุณากรองให้แคบลง` : 'ส่งออกรายการที่พบทั้งหมดเป็นไฟล์ตาราง'
  );
  function exportList(format) {
    downloadUrl(exportUrl('/documents/export', apiParams(filters), format));
  }
  function downloadPicked() {
    const ids = [...picked.keys()];
    if (ids.length === 1) {
      downloadUrl(fileUrl(ids[0]));
      return;
    }
    downloadUrl(zipUrl(ids));
    toast(`กำลังรวม ${ids.length.toLocaleString('th-TH')} ไฟล์เป็น .zip ให้ดาวน์โหลด…`, 'ok', 4000);
  }
  async function trashPicked() {
    const ids = deletable.map((d) => d.id);
    trashing = true;
    try {
      await trashDocs(ids, () => load(filters));
      for (const id of ids) picked.delete(id);
      confirmTrash = false;
      if (!picked.size) selecting = false;
      load(filters);
    } catch (err) {
      toast(errorText(err), 'bad', 5000);
    } finally {
      trashing = false;
    }
  }

  // The phone's bottom bar gives way to the action bar; toasts move above it on PC.
  $effect(() => {
    ui.bar = selecting;
    return () => (ui.bar = false);
  });
  function onKey(e) {
    // Esc leaves select mode, unless it is closing a dialog or sheet first.
    if (e.key === 'Escape' && selecting && !document.querySelector('[aria-modal="true"]')) stopSelect();
  }
</script>

<svelte:window onkeydown={onKey} />

<header class="mast" class:wide={screen.wide}>
  <div class="mast-in">
    {#if screen.wide}<p class="hello">สวัสดี {firstName}</p>{/if}
    <h1>{other ? 'เอกสารประกอบโครงการทุนพัฒนาข้อเสนอ' : grants ? 'ทุนพัฒนาข้อเสนอโครงการวิจัย' : 'ค้นหาสัญญาและเอกสารทุนวิจัย'}</h1>
    <div class="mrow">
      <form class="msearch" role="search" onsubmit={submitQ}>
        <Icon name="search" size={20} />
        <input
          bind:this={qInput}
          value={phoneQ}
          oninput={typeQ}
          type="search"
          placeholder={screen.wide ? (grants ? 'ชื่อเรื่อง ชื่อนักวิจัย หรือข้อความในบันทึก' : 'ชื่อเรื่อง เลขที่สัญญา หรือข้อความในเอกสาร') : 'ค้นหาเอกสาร'}
          aria-label="ค้นหาเอกสาร"
          enterkeyhint="search"
        />
        {#if phoneQ}<button type="button" class="clear" onclick={clearQ} aria-label="ล้างคำค้น"><Icon name="x" size={16} /></button>{/if}
      </form>
      {#if !screen.wide}
        <button class="fbtn" onclick={openSheet} aria-label="ตัวกรอง">
          <Icon name="filter" size={20} />
          {#if activeCount}<span class="n">{activeCount}</span>{/if}
        </button>
      {/if}
    </div>
    {#if stats && screen.wide}
      <div class="figs">
        <span class="fig">{grants ? 'โครงการทั้งหมด' : 'เอกสารทั้งหมด'} <b class="num">{stats.total.toLocaleString('th-TH')}</b></span>
        <button class="fig" aria-pressed={filters.status.includes('needs_review')} onclick={() => onlyFilter('status', 'needs_review')}>
          รอตรวจสอบ <b class="num">{stats.review.toLocaleString('th-TH')}</b>
        </button>
        <button class="fig" aria-pressed={filters.fiscal_year.includes(String(thisFY))} onclick={() => onlyFilter('fiscal_year', thisFY)}>
          ปีงบ {thisFY + BE} <b class="num">{stats.year.toLocaleString('th-TH')}</b>
        </button>
        {#if grants && stats.overdue}
          <button class="fig" aria-pressed={filters.project === 'overdue'} onclick={() => update({ ...filters, project: filters.project === 'overdue' ? '' : 'overdue' })}>
            เกินกำหนด <b class="num">{stats.overdue.toLocaleString('th-TH')}</b>
          </button>
        {/if}
      </div>
    {/if}
    {#if grants}
      <a class="viewlink" href={other ? '/proposals' : '/proposals?view=other'}>
        {other ? '← กลับไปที่รายการโครงการ' : screen.wide ? 'เอกสารประกอบโครงการ (ประกาศรับทุน อนุมัติโครงการรวม) →' : 'เอกสารประกอบโครงการ →'}
      </a>
    {/if}
  </div>
</header>

<div class="layout" class:wide={screen.wide}>
  {#if screen.wide}
    <aside class="side card">
      <div class="side-head">
        <h3>ตัวกรอง</h3>
        <button class="link-btn" onclick={clearAll} disabled={!hasFilters}>ล้างทั้งหมด</button>
      </div>
      <FilterPanel value={filters} {facets} {groups} section={apiSection} onchange={update} idp="pc" />
    </aside>
  {:else}
    <div class="phone-head">
      <div class="quick">
        {#each quick as c (c.k + c.v)}
          <button class="chip" aria-pressed={quickOn(c)} onclick={() => toggleQuick(c)}>{c.label}</button>
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
      {#if items.length}
        <button class="btn small ghost pick-btn" aria-pressed={selecting} onclick={() => (selecting ? stopSelect() : startSelect())}>
          <Icon name="select" size={16} />{selecting ? 'เลิกเลือก' : 'เลือก'}
        </button>
      {/if}
      <span class="export">
        <button class="btn small ghost" disabled={!exportable} title={exportHint} onclick={() => exportList('xlsx')}>
          <Icon name="download" size={16} />ส่งออก Excel
        </button>
        <button class="link-btn" disabled={!exportable} title={exportHint} onclick={() => exportList('csv')}>CSV</button>
      </span>
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
          <div class="item skeleton"><div class="skel" style="width:42px;height:50px;border-radius:4px 12px 4px 4px"></div><div class="grow"><div class="skel" style="width:75%;height:14px"></div><div class="skel" style="width:45%;margin-top:8px"></div></div></div>
        {/each}
      </div>
    {:else if !items.length}
      <div class="empty card">
        {#if hasFilters || filters.q}
          <Icon name="search" size={30} />
          <p>ไม่พบเอกสารที่ตรงกับการค้นหา{archived ? ` ในโครงการที่ยังดำเนินการอยู่` : ''}</p>
          {#if archived}<button class="btn" onclick={() => update({ ...filters, project: 'all' })}>{grants ? 'ดูในโครงการที่ปิดทุนหรือยกเลิกแล้ว' : 'ดูในโครงการที่ปิดแล้ว'} ({archived.toLocaleString('th-TH')})</button>{/if}
          {#if hasFilters}<button class="btn ghost" onclick={clearAll}>ล้างตัวกรองทั้งหมด</button>{/if}
        {:else}
          <Icon name="doc" size={30} />
          <p>ยังไม่มีเอกสารในระบบ</p>
          <button class="btn" onclick={() => openUpload(grants ? 'proposal_dev' : '')}><Icon name="upload" size={17} />อัปโหลดไฟล์แรก</button>
        {/if}
      </div>
    {:else}
      <div class="list card" class:dim={refreshing} class:selecting>
        {#each items as d (d.id)}
          {@const on = picked.has(d.id)}
          <div class="item" class:on>
            {#if selecting}
              <button class="cover" aria-pressed={on} aria-label="เลือก {d.title}" onclick={() => toggle(d)}></button>
            {:else}
              <a class="cover" href="{base}/{d.id}" aria-label={d.title}></a>
            {/if}
            <span class="tilebox">
              <span class="ftile f-{d.funding_type || 'unset'}" title={d.funding_type ? FUNDING[d.funding_type] : 'ยังไม่ระบุประเภทเงินทุน'} aria-hidden="true">
                <small>ปีงบ</small>{d.fiscal_year_be ? String(d.fiscal_year_be).slice(2) : '–'}
              </span>
              {#if selecting}
                <span class="tick" class:on aria-hidden="true" transition:fade={{ duration: ms(150) }}><Icon name="check-only" size={14} stroke={3} /></span>
              {/if}
            </span>
            <div class="grow">
              <div class="topline">
                {#if grants}
                  {#if d.department}<span class="kind">{d.department}</span>{/if}
                  {#if d.funding_source}<span class="kind">{FUNDING_SOURCE[d.funding_source]}</span>{/if}
                {:else}
                  {#if d.reference_no}<span class="cno">{d.reference_no}</span>{:else}<span class="noref">ไม่มีเลขที่</span>{/if}
                  {#if d.kind}<span class="kind">{KIND[d.kind]}</span>{/if}
                {/if}
              </div>
              <div class="t">{#each highlightSegments(d.title, filters.q) as s}{#if s.hit}<mark>{s.text}</mark>{:else}{s.text}{/if}{/each}</div>
              {#if d.snippet}<div class="snip">{@html snippetHtml(d.snippet)}</div>{/if}
              {#if d.snippet && d.snippet_page && d.snippet_file && !selecting}
                <a class="hit" href={hitUrl(d)} target="_blank" rel="noopener">หน้า {d.snippet_page}{#if d.snippet_file.kind !== 'main'} · {d.snippet_file.kind === 'closure' ? 'เอกสารปิดโครงการ' : 'เอกสารแนบ'}{/if}</a>
              {/if}
              <div class="meta">
                {#if d.owners?.length}<span>{d.owners.join(', ')}</span>{/if}
                {#if d.fiscal_year_be}<span>ปีงบ {d.fiscal_year_be}</span>{/if}
                {#if grants && d.budget_total}<span>{money(d.budget_total)}</span>{/if}
                {#if d.received_no}<span>เลขรับ {d.received_no}</span>{/if}
                {#if d.request_ref}<span>ที่ {d.request_ref}</span>{/if}
                {#if grants && d.kpi_due && (d.state === 'active' || d.state === 'overdue')}<span>ส่งผลงานภายใน {thDate(d.kpi_due)}</span>{/if}
                {#if !grants && d.funding_type}<span>{FUNDING[d.funding_type]}</span>{/if}
              </div>
            </div>
            <div class="side-meta">
              {#if d.status !== 'ready'}<span class="badge {d.status}">{STATUS[d.status]}</span>
              {:else if d.state}<span class="badge st-{d.state}">{PROJECT_STATE[d.state]}</span>
              {:else if d.closed_at}<span class="badge closed">ปิดโครงการแล้ว</span>
              {:else}<span class="badge {d.status}">{STATUS[d.status]}</span>{/if}
              <span class="muted date">{thDate(d.updated_at)}</span>
              {#if !screen.wide && !selecting}
                <a class="btn small dl" href={fileUrl(d.id)} aria-label="ดาวน์โหลด {d.title}"><Icon name="download" size={15} /></a>
              {/if}
            </div>
            {#if screen.wide}
              <!-- reserved column, so rows don't shift when select mode hides the button -->
              <span class="dl-cell">
                {#if !selecting}
                  <a class="dl-pc" href={fileUrl(d.id)} title="ดาวน์โหลด PDF" aria-label="ดาวน์โหลด {d.title}"><Icon name="download" size={18} /></a>
                {/if}
              </span>
            {/if}
          </div>
        {/each}
      </div>
      {#if items.length < total}
        <button class="btn ghost more" onclick={() => load(filters, true)}>แสดงเพิ่ม ({(total - items.length).toLocaleString('th-TH')} รายการ)</button>
      {/if}
      {#if archived && items.length >= total}
        <p class="archived muted">มีอีก {archived.toLocaleString('th-TH')} รายการใน{grants ? 'โครงการที่ปิดทุนหรือยกเลิกแล้ว' : 'โครงการที่ปิดแล้ว'} <button class="link-btn" onclick={() => update({ ...filters, project: 'all' })}>แสดงด้วย</button></p>
      {/if}
    {/if}
    {#if selecting}<div class="bar-room" aria-hidden="true"></div>{/if}
  </section>
</div>

{#if selecting}
  <div
    class="selbar"
    class:phone={!screen.wide}
    role="toolbar"
    aria-label="จัดการรายการที่เลือก"
    transition:fly={{ y: 90, duration: ms(220), easing: cubicOut, opacity: 1 }}
  >
    <button class="icon-btn close" onclick={stopSelect} aria-label="เลิกเลือก"><Icon name="x" size={19} /></button>
    <div class="count" aria-live="polite">
      <b class="num">{picked.size.toLocaleString('th-TH')}</b>
      <span>{screen.wide ? 'รายการที่เลือก' : 'เลือกแล้ว'}</span>
    </div>
    <button class="link-btn all" onclick={toggleAll} disabled={!items.length}>{allShown ? 'ไม่เลือกที่แสดง' : `เลือกที่แสดง (${items.length})`}</button>
    <span class="spacer"></span>
    <button class="act" onclick={downloadPicked} disabled={!picked.size} title={picked.size > 1 ? 'ดาวน์โหลดรวมเป็นไฟล์ .zip' : 'ดาวน์โหลด'}>
      <Icon name={picked.size > 1 ? 'archive' : 'download'} size={19} /><span>{picked.size > 1 ? 'ดาวน์โหลด .zip' : 'ดาวน์โหลด'}</span>
    </button>
    <button
      class="act bad"
      onclick={() => (confirmTrash = true)}
      disabled={!deletable.length}
      title={picked.size && !deletable.length ? 'ลบได้เฉพาะเอกสารที่คุณอัปโหลด' : 'ย้ายไปถังขยะ'}
    >
      <Icon name="trash" size={19} /><span>ลบ</span>
    </button>
  </div>
{/if}

{#if confirmTrash}
  <Modal title="ย้าย {deletable.length.toLocaleString('th-TH')} รายการไปถังขยะ?" onclose={() => (confirmTrash = false)}>
    <ul class="picklist">
      {#each deletable.slice(0, 8) as d (d.id)}
        <li>{#if d.reference_no}<span class="cno">{d.reference_no}</span>{/if}<span>{d.title}</span></li>
      {/each}
    </ul>
    {#if deletable.length > 8}<p class="muted">และอีก {(deletable.length - 8).toLocaleString('th-TH')} รายการ</p>{/if}
    {#if deletable.length < picked.size}
      <div class="notice warn">{(picked.size - deletable.length).toLocaleString('th-TH')} รายการที่คุณไม่ได้อัปโหลดจะไม่ถูกลบ (ลบได้เฉพาะผู้อัปโหลดหรือผู้ดูแลระบบ)</div>
    {/if}
    <p class="muted">เอกสารจะหายจากการค้นหา และลิงก์แชร์ของเอกสารเหล่านี้จะใช้ไม่ได้ทันที กู้คืนได้จาก <a href="/trash">ถังขยะของฉัน</a></p>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (confirmTrash = false)}>ยกเลิก</button>
      <button class="btn danger" onclick={trashPicked} disabled={trashing || !deletable.length}>ย้ายไปถังขยะ</button>
    {/snippet}
  </Modal>
{/if}

{#if sheet}
  <div class="scrim" transition:fade={{ duration: ms(200) }} onclick={() => (sheet = false)} role="presentation"></div>
  <div
    class="sheet"
    role="dialog"
    aria-modal="true"
    aria-label="ตัวกรอง"
    transition:fly={{ y: 500, duration: ms(240), easing: cubicOut, opacity: 1 }}
    use:sheetGesture={{ enabled: true, onclose: () => (sheet = false), scroller: '.sheet-body' }}
  >
    <div class="sheet-grab" data-sheet-handle aria-hidden="true"></div>
    <div class="sheet-head" data-sheet-handle>
      <h3>ตัวกรอง</h3>
      <select id="sheet-sort" value={draft.sort} onchange={(e) => changeDraft({ ...draft, sort: e.currentTarget.value })} aria-label="เรียงตาม">
        {#each sortsFor(draft.q) as [v, l] (v)}<option value={v}>{l}</option>{/each}
      </select>
    </div>
    <div class="sheet-body">
      <FilterPanel value={draft} facets={draftFacets} {groups} section={apiSection} onchange={changeDraft} idp="ph" />
    </div>
    <div class="sheet-foot">
      <button class="btn ghost" onclick={() => changeDraft({ q: draft.q, sort: draft.sort, person: '', mine: false, project: '', ...Object.fromEntries(LIST_KEYS.map((k) => [k, []])) })}>ล้าง</button>
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
  .export { display: inline-flex; align-items: center; gap: 2px; }
  .sort { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .sort select, .sheet-head select { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 5px 8px; font-size: 14px; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .archived { text-align: center; font-size: 14px; margin: 4px 0 0; }
  .chips .chip { padding-right: 5px; }

  .list { overflow: hidden; transition: opacity 120ms; }
  .list.dim { opacity: 0.55; }
  .item { position: relative; display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; gap: 14px; padding: 13px 16px; border-top: 1px solid var(--border); color: inherit; text-decoration: none; transition: background var(--t-fast); }
  .item:first-child { border-top: 0; }
  .layout.wide .item { grid-template-columns: 42px minmax(0, 1fr) auto 40px; }
  .dl-cell { width: 40px; height: 40px; align-self: center; }
  .dl-pc {
    position: relative; z-index: 2; width: 40px; height: 40px; display: grid; place-items: center;
    border: 0; border-radius: 10px; background: var(--primary); color: var(--on-primary);
    transition: background var(--t-fast), transform var(--t-fast) var(--ease-out);
  }
  .dl-pc:hover { background: var(--primary-hover); }
  .dl-pc:active { transform: scale(0.94); }
  .item:hover { background: var(--subtle); }
  .cover { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .cover:focus-visible { outline-offset: -3px; }
  button.cover { border: 0; margin: 0; padding: 0; background: none; cursor: pointer; }
  .topline { display: flex; gap: 10px; align-items: baseline; font-size: 12px; }
  .kind { color: var(--muted); }
  .grow { min-width: 0; flex: 1; }
  .t { font-weight: 500; font-size: 15px; line-height: 1.45; overflow-wrap: anywhere; }
  .hit { position: relative; z-index: 2; display: inline-block; margin-top: 2px; font-size: 12.5px; color: var(--primary); text-decoration: none; }
  .hit:hover { text-decoration: underline; }
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
  /* ── masthead: the page's one bold element, echoing the faculty site's maroon hero ── */
  .mast {
    position: relative; overflow: hidden; color: #fff; border-radius: 18px; margin-bottom: 18px;
    background:
      radial-gradient(circle at 92% -20%, rgba(255, 255, 255, 0.12) 0 150px, transparent 151px),
      radial-gradient(circle at 4% 130%, rgba(255, 255, 255, 0.08) 0 120px, transparent 121px),
      linear-gradient(118deg, var(--band-1), var(--band-2) 60%, var(--band-3));
  }
  .mast-in { position: relative; padding: 26px 28px 22px; display: flex; flex-direction: column; gap: 12px; max-width: 860px; }
  .hello { font-size: 14px; opacity: 0.85; }
  .mast h1 { font-size: 30px; font-weight: 600; color: #fff; line-height: 1.25; margin-top: -6px; }
  .mrow { display: flex; gap: 8px; }
  .msearch {
    flex: 1; display: flex; align-items: center; gap: 10px; min-width: 0; height: 52px; padding: 0 8px 0 16px;
    background: var(--surface); color: var(--muted); border-radius: 14px; box-shadow: 0 10px 26px -14px rgba(0, 0, 0, 0.55);
  }
  .msearch:focus-within { outline: 3px solid var(--accent); outline-offset: 2px; }
  .msearch input { flex: 1; min-width: 0; border: 0; background: none; outline: none; font-size: 16.5px; color: var(--text); }
  .msearch input::-webkit-search-cancel-button { display: none; }
  .clear { border: 0; background: var(--subtle); color: var(--muted); width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; flex: none; }
  .figs { display: flex; flex-wrap: wrap; gap: 8px; }
  .fig {
    display: inline-flex; align-items: baseline; gap: 8px; padding: 5px 14px; border-radius: 999px; font-size: 13.5px; color: #fff;
    background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.2);
    transition: background var(--t-fast), color var(--t-fast);
  }
  .fig b { font-family: var(--f-display); font-weight: 500; font-size: 16px; }
  button.fig:hover { background: rgba(255, 255, 255, 0.22); }
  button.fig[aria-pressed='true'] { background: #fff; color: var(--m-600); border-color: #fff; }
  .viewlink { align-self: flex-start; color: #fff; opacity: 0.88; font-size: 13.5px; text-decoration: underline; text-underline-offset: 3px; }
  .viewlink:hover { opacity: 1; }
  .fbtn { position: relative; flex: none; width: 52px; display: grid; place-items: center; border: 0; border-radius: 14px; background: rgba(255, 255, 255, 0.16); color: #fff; }
  .fbtn .n { position: absolute; top: -6px; right: -6px; min-width: 20px; height: 20px; border-radius: 999px; background: var(--accent); color: #2b1d00; font-size: 11px; font-weight: 700; display: grid; place-items: center; padding: 0 5px; }
  .mast:not(.wide) { margin: -14px -12px 12px; border-radius: 0 0 20px 20px; }
  .mast:not(.wide) .mast-in { padding: 16px 14px 18px; gap: 10px; }
  .mast:not(.wide) h1 { font-size: 19px; margin: 0; }
  .mast:not(.wide) .msearch { height: 48px; }
  .quick { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -12px; padding: 0 12px 2px; }
  .quick::-webkit-scrollbar { display: none; }
  .quick .chip { flex: none; }
  .noref { font-size: 12px; color: var(--faint); }
  /* phone card: text on top, then status · date · download on one row */
  .layout:not(.wide) .item { grid-template-columns: 42px minmax(0, 1fr); padding: 12px; gap: 8px 12px; }
  .layout:not(.wide) .side-meta { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 10px; }
  .layout:not(.wide) .side-meta .dl { margin: 0 0 0 auto; }
  .layout:not(.wide) .t { font-size: 14.5px; }
  .dl { position: relative; z-index: 2; min-height: 34px; padding: 4px 10px; margin-top: 4px; }

  /* ── select mode ── */
  .pick-btn[aria-pressed='true'] { background: var(--primary-soft); border-color: var(--primary-soft); color: var(--primary-text); }
  .tilebox { position: relative; display: block; width: 42px; }
  .tick {
    position: absolute; top: -6px; left: -6px; width: 22px; height: 22px; border-radius: 50%;
    display: grid; place-items: center; background: var(--surface); color: transparent;
    box-shadow: inset 0 0 0 2px var(--border-strong); z-index: 2; pointer-events: none;
  }
  .tick.on { background: var(--primary); color: var(--on-primary); box-shadow: 0 0 0 2px var(--surface); animation: tick-pop 220ms var(--ease-out); }
  @keyframes tick-pop { 0% { transform: scale(0.6); } 60% { transform: scale(1.12); } 100% { transform: scale(1); } }
  .selecting .item { cursor: pointer; }
  .item.on, .item.on:hover { background: var(--primary-soft); }
  .item.on::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--primary); }
  .bar-room { height: 64px; }
  .selbar {
    position: fixed; z-index: 30; left: 50%; bottom: 20px; translate: -50% 0; width: min(680px, calc(100vw - 40px));
    display: flex; align-items: center; gap: 10px; padding: 8px 10px 8px 8px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow);
  }
  .selbar .count { display: flex; align-items: baseline; gap: 6px; font-size: 13.5px; color: var(--muted); white-space: nowrap; }
  .selbar .count b { font-family: var(--f-display); font-weight: 600; font-size: 20px; color: var(--primary-text); }
  .selbar .all { font-size: 13.5px; white-space: nowrap; }
  .act {
    display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 6px 14px; border-radius: 10px;
    border: 1px solid var(--border); background: var(--surface); color: var(--text); font-size: 14px; font-weight: 500; white-space: nowrap;
    transition: background var(--t-fast), transform var(--t-fast) var(--ease-out);
  }
  .act:hover:not([disabled]) { background: var(--subtle); }
  .act:active:not([disabled]) { transform: scale(0.97); }
  .act.bad { color: var(--bad); }
  .act[disabled] { opacity: 0.45; cursor: default; }
  /* phone: the bar takes the bottom nav's place */
  .selbar.phone {
    left: 0; right: 0; bottom: 0; translate: none; width: auto; border-radius: 0; border-width: 1px 0 0;
    min-height: calc(var(--bottom-h) + env(safe-area-inset-bottom)); gap: 6px;
    padding: 6px max(8px, env(safe-area-inset-right)) calc(6px + env(safe-area-inset-bottom)) max(6px, env(safe-area-inset-left));
  }
  .selbar.phone .count { flex-direction: column; gap: 0; line-height: 1.1; font-size: 11px; align-items: flex-start; }
  .selbar.phone .count b { font-size: 18px; }
  .selbar.phone .all { font-size: 12.5px; white-space: normal; max-width: 92px; text-align: left; line-height: 1.25; }
  .selbar.phone .act { flex-direction: column; gap: 1px; min-height: 48px; padding: 4px 10px; border: 0; font-size: 11px; }
  .picklist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
  .picklist li { display: flex; gap: 8px; align-items: baseline; overflow-wrap: anywhere; }
  .picklist .cno { flex: none; }

  .scrim { position: fixed; inset: 0; background: var(--scrim); z-index: 40; }
  .sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 41; max-height: 88vh; background: var(--surface); border-radius: 20px 20px 0 0; display: flex; flex-direction: column; box-shadow: var(--shadow); }
  .sheet-head { display: flex; justify-content: space-between; align-items: center; padding: 2px 16px 8px; }
  .sheet-body { overflow: auto; padding: 0 10px; flex: 1; overscroll-behavior: contain; }
  .sheet-foot { display: flex; gap: 8px; padding: 10px 16px calc(12px + env(safe-area-inset-bottom)); border-top: 1px solid var(--border); }
  .sheet-foot .btn { min-height: 46px; }
  .sheet-foot .grow { flex: 1; }
</style>
