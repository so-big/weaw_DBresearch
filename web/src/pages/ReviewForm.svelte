<script>
  // Review / edit metadata. First review: the form is pre-filled from auto-fill suggestions.
  // Later edits: the saved values, with the system's readings shown as hints to pick from.
  import { onDestroy, tick } from 'svelte';
  import { get, put, post, errorText, fileUrl } from '../lib/api.js';
  import { navigate, setLeaveGuard } from '../lib/router.svelte.js';
  import { createDraft } from '../lib/draft.js';
  import { toast, screen, session, bumpReviewCount, isAdmin } from '../lib/state.svelte.js';
  import { categoryGroups, resetCatalog } from '../lib/catalog.js';
  import { KIND, FUNDING, FUNDING_SOURCE, ROLE, FIELD, BE, thDate, money, toThaiInput, parseThaiDate, docPath } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';

  let { id } = $props();

  let doc = $state(null);
  let sug = $state(null); // extracted_fields payload
  let groups = $state([]);
  let form = $state(null);
  let errors = $state({});
  let saveError = $state(null);
  let saving = $state(false);
  let loadError = $state('');
  let waiting = $state(false); // OCR still running
  let skipWait = $state(false);
  let showPdf = $state(true);
  let pdfPage = $state(null);
  let tagInput = $state('');
  let timer;

  const fields = $derived(sug?.fields || {});
  const fresh = $derived(doc && doc.status !== 'ready');

  async function load() {
    clearTimeout(timer);
    try {
      const [d, a, g] = await Promise.all([get(`/documents/${id}`), get(`/documents/${id}/autofill`), categoryGroups()]);
      if (d.kind === 'proposal_dev') return navigate(`/proposals/${id}/review`, { replace: true });
      doc = d;
      sug = a.suggestions || {};
      groups = g;
      waiting = d.status === 'processing' && !skipWait;
      if (waiting) timer = setTimeout(load, 4000);
      else if (!form) openForm(d);
    } catch (err) {
      loadError = errorText(err);
    }
  }
  load();
  onDestroy(() => clearTimeout(timer));

  function startManual() {
    skipWait = true;
    waiting = false;
    clearTimeout(timer);
    openForm(doc);
  }

  // ───────── Draft and leave guard (lib/draft.js) ─────────
  let draft = null;
  let draftOffer = $state(null); // a stored, different draft waiting for restore / discard
  // Only what the user typed: the suggestion lists come from OCR and are rebuilt from the server.
  const snapshot = (f) => {
    const { suggestedCats, suggestedTags, suggestedOptions, ...typed } = f;
    return JSON.stringify(typed);
  };
  function openForm(d) {
    form = buildForm(d, sug);
    draft = createDraft(session.user.id, id, d.updated_at);
    draftOffer = draft.init(snapshot(form));
  }
  function restoreDraft() {
    form = { ...form, ...JSON.parse(draftOffer) };
    draft.resolve(draftOffer);
    draftOffer = null;
  }
  function discardDraft() {
    draft.resolve(null);
    draftOffer = null;
  }
  $effect(() => {
    if (form && draft) draft.update(snapshot(form)); // reads the whole form, so any edit re-runs it
  });
  const dirty = () => !!form && !!draft?.isDirty(snapshot(form));
  const offLeave = setLeaveGuard(() => !dirty() || confirm('มีการแก้ไขที่ยังไม่ได้บันทึก ออกจากหน้านี้หรือไม่'));
  onDestroy(() => {
    offLeave();
    draft?.flush();
  });
  function warnUnload(e) {
    draft?.flush(); // the tab may close before the debounce fires
    if (dirty()) e.preventDefault();
  }

  function buildForm(d, s) {
    const F = s.fields || {};
    const inf = s.inferred || {};
    const first = d.status !== 'ready';
    const pick = (name, current) => (first && F[name]?.value != null ? F[name].value : current);
    const fy = d.fiscal_year || (first ? inf.fiscal_year || F.fiscal_year?.value : null);

    // Categories: saved ones, plus (first review) every confident checkbox / header suggestion.
    const cats = new Map(d.categories.map((c) => [c.id, c.source]));
    const suggestedCats = new Set();
    for (const c of [...(s.checks || []), ...(s.hints || [])]) {
      if (c.suggest === 'category' && c.category_id) {
        suggestedCats.add(c.category_id);
        if (first && !cats.has(c.category_id)) cats.set(c.category_id, 'auto');
      }
    }
    const tags = d.tags.map((t) => ({ name: t.name, source: t.source }));
    const tagNames = new Set(tags.map((t) => t.name.toLowerCase()));
    // A ticked box that matched no option: inside a known group it is offered as a new option
    // of that group; without a group it stays a suggested free tag.
    const unmatched = [...(s.checks || []), ...(s.hints || [])].filter((c) => c.suggest === 'tag' && c.label?.trim());
    const suggestedOptions = {};
    if (first) {
      for (const c of unmatched.filter((c) => c.group_key)) {
        const list = (suggestedOptions[c.group_key] ||= []);
        if (!list.includes(c.label.trim())) list.push(c.label.trim());
      }
    }
    const suggestedTags = [...new Set(unmatched.filter((c) => !c.group_key).map((c) => c.label.trim()))].filter(
      (l) => !tagNames.has(l.toLowerCase()),
    );

    const people = d.people.length
      ? d.people.map((p) => ({ prefix_th: p.prefix_th || '', name_th: p.name_th || '', name_en: p.name_en || '', role: p.role, share_pct: p.share_pct ?? '', unit: p.unit || '' }))
      : first
        ? (s.people || []).map((p) => ({ prefix_th: p.prefix_th || '', name_th: p.name || '', name_en: p.name_en || '', role: p.role || 'co_investigator', share_pct: p.share_pct ?? '', unit: p.unit || '', auto: true }))
        : [];

    return {
      title: (first && F.title?.value) || d.title || '',
      title_en: pick('title_en', d.title_en) || '',
      kind: d.kind || (first ? inf.kind : '') || '',
      funding_type: d.funding_type || (first ? inf.funding_type : '') || '',
      funding_source: d.funding_source || '',
      funder_name: d.funder_name || '',
      reference_no: pick('reference_no', d.reference_no) || '',
      document_date: toThaiInput(pick('document_date', d.document_date)),
      effective_from: toThaiInput(pick('effective_from', d.effective_from)),
      effective_to: toThaiInput(pick('effective_to', d.effective_to)),
      fiscal_year_be: fy ? String(fy + BE) : '',
      budget_total: pick('budget_total', d.budget_total) ?? '',
      categories: Object.fromEntries(cats),
      suggestedCats: [...suggestedCats],
      tags,
      suggestedTags,
      suggestedOptions,
      people,
      budget_lines: d.budget_lines.map((b) => ({ ...b, amount: b.amount ?? '', percent: b.percent ?? '', due_date: toThaiInput(b.due_date) })),
    };
  }

  function pickType(v) {
    form.funding_type = v;
    const internal = INTERNAL_SOURCES.includes(form.funding_source);
    if (form.funding_source && internal !== (v === 'internal')) form.funding_source = ''; // no longer matches
  }
  // Funding source → internal / external (FF counts as internal; the server checks it too).
  const INTERNAL_SOURCES = ['ff', 'nu_income', 'faculty_income'];
  function pickSource(v) {
    if (form.funding_source === v) return (form.funding_source = '');
    form.funding_source = v;
    form.funding_type = INTERNAL_SOURCES.includes(v) ? 'internal' : 'external';
  }

  // ───────── Suggestion hints under each field ─────────
  function showValue(name, v) {
    if (v == null || v === '') return '';
    if (/date|effective/.test(name)) return thDate(v);
    if (name === 'budget_total') return money(v);
    if (name === 'fiscal_year') return `พ.ศ. ${Number(v) + BE}`;
    return String(v);
  }
  function formValue(name, v) {
    if (/date|effective/.test(name)) return toThaiInput(v);
    if (name === 'fiscal_year') return String(Number(v) + BE);
    return String(v);
  }
  const formKey = (name) => (name === 'fiscal_year' ? 'fiscal_year_be' : name);
  function hintsFor(name) {
    const f = fields[name];
    if (!f || !form) return [];
    const current = String(form[formKey(name)] ?? '').replace(/\s/g, '');
    return [f.value, ...(f.alternatives || [])]
      .filter((v) => v != null && v !== '' && formValue(name, v).replace(/\s/g, '') !== current)
      .slice(0, 3);
  }
  const lowConfidence = (name) => fields[name] && fields[name].confidence < 0.7;

  // ───────── Warnings (never block saving) ─────────
  const groupName = (key) => groups.find((g) => g.key === key)?.name_th || key;
  function warningText(w) {
    switch (w.code) {
      case 'missing_field': return `ไม่พบ${FIELD[w.field] || w.field}ในเอกสาร กรุณากรอกเอง`;
      case 'amount_words_mismatch': return `จำนวนเงินตัวเลข (${money(w.digits)}) ไม่ตรงกับตัวอักษร (${money(w.words)})`;
      case 'multiple_contract_numbers': return `พบเลขที่สัญญาหลายเลขในไฟล์เดียว: ${w.values.join(', ')} อาจอัปโหลดผิดไฟล์`;
      case 'team_share_not_100': return `สัดส่วนงานของทีมวิจัยรวมได้ ${w.total}% (ควรเป็น 100%)`;
      case 'single_choice_violation': return `กลุ่ม “${groupName(w.group)}” เลือกได้ข้อเดียว แต่พบช่องที่ติ๊กไว้ ${w.count} ช่อง`;
      case 'funding_mismatch': return 'ประเภททุนจากเลขที่สัญญาไม่ตรงกับหัวเอกสาร';
      case 'fiscal_year_mismatch': return `ปีงบประมาณในหัวเอกสาร (${w.header_be}) ไม่ตรงกับปีในเลขที่สัญญา (${w.contract_no_be})`;
      case 'ocr_failed': return 'ระบบอ่านไฟล์นี้ไม่สำเร็จ กรุณากรอกข้อมูลเอง';
      default: return w.code;
    }
  }
  const warnings = $derived(fresh ? (sug?.warnings || []) : []);

  // ───────── Categories and tags ─────────
  // Any user may add an option to a group while reviewing (no admin approval).
  let adding = $state(null); // group id whose "add option" box is open
  let newOption = $state('');
  let optionBusy = $state(false);
  const squash = (t) => (t || '').replace(/\s+/g, '').toLowerCase();
  const same = (a, b) => squash(a) === squash(b);
  async function openAdd(g) {
    adding = g.id;
    newOption = '';
    await tick();
    document.getElementById(`f-opt-${g.key}`)?.focus();
  }
  function optionKey(e, g) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addOption(g, newOption);
    } else if (e.key === 'Escape') adding = null;
  }
  async function addOption(g, name, source = 'manual') {
    const label = name.trim();
    if (!label || optionBusy) return;
    optionBusy = true;
    try {
      const option = await post('/categories', { group_id: g.id, name_th: label });
      if (!g.options.some((o) => o.id === option.id)) g.options.push(option);
      resetCatalog();
      if (!(option.id in form.categories)) {
        if (!g.multi) for (const o of g.options) delete form.categories[o.id];
        form.categories[option.id] = source;
      }
      if (source === 'auto') form.suggestedCats.push(option.id);
      adding = null;
      newOption = '';
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      optionBusy = false;
    }
  }
  function toggleCat(group, optionId) {
    const on = optionId in form.categories;
    if (!group.multi) for (const o of group.options) delete form.categories[o.id];
    if (on) delete form.categories[optionId];
    else form.categories[optionId] = form.suggestedCats.includes(optionId) ? 'auto' : 'manual';
  }
  function addTag(name, source = 'manual') {
    const n = name.trim();
    if (!n || form.tags.some((t) => t.name.toLowerCase() === n.toLowerCase())) return;
    form.tags.push({ name: n, source });
    form.suggestedTags = form.suggestedTags.filter((t) => t.toLowerCase() !== n.toLowerCase());
  }
  function tagKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag(tagInput);
      tagInput = '';
    }
  }

  // ───────── People and budget lines ─────────
  function addPerson() {
    form.people.push({ prefix_th: '', name_th: '', name_en: '', role: form.people.length ? 'co_investigator' : 'owner', share_pct: '', unit: '' });
  }
  const numOrNull = (v) => {
    const n = Number(num(v));
    return v === '' || v == null || isNaN(n) ? null : n;
  };
  const shareTotal = $derived.by(() => {
    const vals = form?.people.map((p) => numOrNull(p.share_pct)).filter((v) => v !== null) || [];
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) * 100) / 100 : null;
  });
  const budgetNum = $derived(form ? numOrNull(form.budget_total) : null);
  function lineSum(type) {
    const vals = form.budget_lines.filter((b) => b.line_type === type).map((b) => numOrNull(b.amount)).filter((v) => v !== null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
  }
  function addLine(type) {
    const n = form.budget_lines.filter((b) => b.line_type === type).length + 1;
    form.budget_lines.push({ line_type: type, group_label: '', label: type === 'installment' ? `งวดที่ ${n}` : '', amount: '', percent: '', due_date: '', condition: '' });
  }
  // Installment %: fill it from the amount when the total is known and the box is still empty.
  function fillPercent(b) {
    const amount = numOrNull(b.amount);
    if (b.percent === '' && amount !== null && budgetNum) b.percent = String(Math.round((amount / budgetNum) * 10000) / 100);
  }
  const budgetSugg = $derived(sug?.budget_lines || []);
  function useBudgetSugg() {
    form.budget_lines = budgetSugg.map((b) => ({
      line_type: b.line_type,
      group_label: b.group_label || '',
      label: b.label,
      amount: b.amount ?? '',
      percent: b.percent ?? '',
      due_date: toThaiInput(b.due_date),
      condition: b.condition || '',
    }));
  }

  // ───────── Save ─────────
  const num = (v) => (v === '' || v == null ? null : String(v).replace(/[,\s]/g, ''));
  function validate() {
    const e = {};
    if (!form.title.trim()) e.title = 'กรุณากรอกชื่อเรื่อง';
    if (!form.kind) e.kind = 'เลือกประเภทเอกสาร';
    if (!form.funding_type) e.funding_type = 'เลือกประเภทเงินทุน';
    for (const k of ['document_date', 'effective_from', 'effective_to']) {
      if (parseThaiDate(form[k]) === null) e[k] = 'รูปแบบวันที่ไม่ถูกต้อง ใช้ วว/ดด/ปปปป เช่น 1/10/2568';
    }
    const fy = form.fiscal_year_be.trim();
    if (fy && !/^\d{4}$/.test(fy)) e.fiscal_year_be = 'ใส่ปี พ.ศ. 4 หลัก เช่น 2568';
    if (form.budget_total !== '' && isNaN(Number(num(form.budget_total)))) e.budget_total = 'ใส่ตัวเลขเท่านั้น';
    form.budget_lines.forEach((b, i) => {
      if (parseThaiDate(b.due_date) === null) e[`bl${i}`] = 'วันที่ไม่ถูกต้อง';
      if (b.label.trim() && isNaN(Number(num(b.amount)))) e[`bl${i}`] = 'จำนวนเงินไม่ถูกต้อง';
    });
    return e;
  }

  async function save(next = false) {
    errors = validate();
    saveError = null;
    if (Object.keys(errors).length) {
      await tick();
      document.querySelector('.invalid')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const body = {
      title: form.title.trim(),
      title_en: form.title_en.trim() || null,
      kind: form.kind,
      funding_type: form.funding_type,
      funding_source: form.funding_source || null,
      funder_name: form.funding_source === 'external' ? form.funder_name.trim() || null : null,
      reference_no: form.reference_no.trim() || null,
      document_date: parseThaiDate(form.document_date) || null,
      effective_from: parseThaiDate(form.effective_from) || null,
      effective_to: parseThaiDate(form.effective_to) || null,
      fiscal_year: form.fiscal_year_be.trim() ? Number(form.fiscal_year_be) - BE : null,
      budget_total: num(form.budget_total),
      categories: Object.entries(form.categories).map(([category_id, source]) => ({ category_id, source })),
      tags: form.tags.map((t) => ({ name: t.name, source: t.source })),
      people: form.people
        .filter((p) => p.name_th.trim() || p.name_en.trim())
        .map((p) => ({
          prefix_th: p.prefix_th.trim() || null,
          name_th: p.name_th.trim() || null,
          name_en: p.name_en.trim() || null,
          role: p.role,
          share_pct: num(p.share_pct),
          unit: p.unit.trim() || null,
        })),
      budget_lines: form.budget_lines
        .filter((b) => b.label.trim())
        .map((b) => ({
          line_type: b.line_type,
          group_label: b.group_label?.trim() || null,
          label: b.label.trim(),
          amount: num(b.amount) ?? '0',
          percent: num(b.percent),
          due_date: parseThaiDate(b.due_date) || null,
          condition: b.condition?.trim() || null,
        })),
    };
    saving = true;
    try {
      await put(`/documents/${id}/metadata`, body);
      draft.finish();
      bumpReviewCount();
      toast('บันทึกข้อมูลแล้ว');
      if (next) {
        const queue = await get('/documents', { section: 'all', status: ['needs_review', 'failed'], mine: isAdmin() ? undefined : true, sort: 'oldest', page_size: 5 });
        const following = queue.items.find((d) => d.id !== id);
        navigate(following ? `${docPath(following)}/review` : '/review');
      } else navigate(`/documents/${id}`);
    } catch (err) {
      saveError = err.status === 409 ? { dup: err.data?.document_id } : { text: errorText(err) };
    } finally {
      saving = false;
    }
  }

  async function reprocess() {
    try {
      await post(`/documents/${id}/reprocess`);
      toast('ส่งให้ระบบอ่านเอกสารใหม่แล้ว');
      form = null;
      skipWait = false;
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }

  const pageOf = (name) => fields[name]?.page;
  function gotoPage(p) {
    if (!p) return;
    pdfPage = p;
    showPdf = true;
  }
  const pdfSrc = $derived(`${fileUrl(id, { inline: true })}${pdfPage ? `#page=${pdfPage}` : ''}`);
  const sidePdf = $derived(screen.wide && innerWidth >= 1180);
  let innerWidth = $state(window.innerWidth);
</script>

<svelte:window bind:innerWidth onbeforeunload={warnUnload} />

{#snippet hint(name)}
  {#if fresh || hintsFor(name).length}
    <div class="hints">
      {#if pageOf(name)}<button type="button" class="pg" onclick={() => gotoPage(pageOf(name))}>หน้า {pageOf(name)}</button>{/if}
      {#each hintsFor(name) as v (String(v))}
        <button type="button" class="sugg" onclick={() => (form[formKey(name)] = formValue(name, v))} title="ใช้ค่านี้">ระบบอ่านได้: {showValue(name, v)}</button>
      {/each}
      {#if lowConfidence(name)}<span class="unsure">ระบบไม่แน่ใจ ตรวจกับไฟล์อีกครั้ง</span>{/if}
    </div>
  {/if}
{/snippet}

{#if loadError}
  <div class="notice bad">{loadError}</div>
{:else if !doc}
  <div class="card pad stack"><div class="skel" style="width:30%"></div><div class="skel" style="width:70%;height:20px"></div><div class="skel" style="width:90%"></div></div>
{:else if !doc.can_edit}
  <div class="notice warn">เฉพาะผู้อัปโหลดหรือผู้ดูแลระบบเท่านั้นที่แก้ไขข้อมูลเอกสารนี้ได้</div>
  <a href="/documents/{id}">← กลับไปหน้าเอกสาร</a>
{:else if waiting}
  <div class="card waiting enter">
    <span class="spin big"></span>
    <h2>ระบบกำลังอ่านเอกสาร</h2>
    <p class="muted">ใช้เวลาประมาณ 1–2 นาทีต่อไฟล์ เมื่อเสร็จ ฟอร์มจะเติมข้อมูลให้อัตโนมัติ ระหว่างนี้ไปทำอย่างอื่นก่อนได้</p>
    <div class="row">
      <a class="btn ghost" href="/review">กลับไปรายการรอตรวจสอบ</a>
      <button class="btn ghost" onclick={startManual}>กรอกเองเลย</button>
    </div>
  </div>
{:else if form}
  <div class="review" class:split={sidePdf && showPdf}>
    <div class="form-col">
      <div class="crumbs"><a href="/documents/{id}"><Icon name="back" size={16} />กลับไปหน้าเอกสาร</a></div>
      <div class="titlebar">
        <div>
          <h1>{doc.status === 'ready' ? 'แก้ไขข้อมูลเอกสาร' : 'ตรวจสอบข้อมูลเอกสาร'}</h1>
          <p class="muted">{doc.versions[0]?.original_filename}</p>
        </div>
        <div class="row">
          {#if sidePdf}
            <button class="btn ghost small" onclick={() => (showPdf = !showPdf)}><Icon name="eye" size={15} />{showPdf ? 'ซ่อนไฟล์' : 'แสดงไฟล์'}</button>
          {:else}
            <a class="btn ghost small" href={fileUrl(id, { inline: true })} target="_blank" rel="noopener"><Icon name="eye" size={15} />เปิดไฟล์ PDF</a>
          {/if}
          <button class="btn ghost small" onclick={reprocess} title="ให้ระบบอ่านไฟล์และเติมข้อมูลใหม่"><Icon name="refresh" size={15} />อ่านใหม่</button>
        </div>
      </div>

      {#if draftOffer}
        <div class="notice warn" role="alert">
          <Icon name="warn" size={18} /><span>พบแบบร่างที่ยังไม่ได้บันทึก</span><span class="spacer"></span>
          <button class="btn small" onclick={restoreDraft}>กู้คืน</button>
          <button class="btn ghost small" onclick={discardDraft}>ทิ้ง</button>
        </div>
      {/if}
      {#if fresh}
        <div class="notice info"><Icon name="info" size={18} /><span>ระบบเติมข้อมูลจากไฟล์สแกนให้แล้ว ตรวจและแก้ให้ถูกต้องก่อนบันทึก ค่าที่ระบบอ่านได้จะแสดงใต้ช่อง กดเพื่อใช้ค่านั้น</span></div>
      {/if}
      {#each warnings as w, i (i)}
        <div class="notice warn"><Icon name="warn" size={18} /><span>{warningText(w)}</span></div>
      {/each}

      <section class="card pad stack">
        <h3>ข้อมูลหลัก</h3>
        <label class="field" class:invalid={errors.title}>
          <span>ชื่อเรื่อง *</span>
          <textarea id="f-title" rows="2" bind:value={form.title}></textarea>
          {#if errors.title}<small class="err">{errors.title}</small>{/if}
          {@render hint('title')}
        </label>
        <label class="field">
          <span>ชื่อเรื่อง (ภาษาอังกฤษ)</span>
          <textarea id="f-title-en" rows="2" bind:value={form.title_en}></textarea>
          {@render hint('title_en')}
        </label>
        <div class="two">
          <div class="field" class:invalid={errors.kind}>
            <span>ประเภทเอกสาร *</span>
            <div class="seg">{#each Object.entries(KIND).filter(([v]) => v === 'contract' || v === 'grant') as [v, l] (v)}<button type="button" aria-pressed={form.kind === v} onclick={() => (form.kind = v)}>{l}</button>{/each}</div>
            {#if errors.kind}<small class="err">{errors.kind}</small>{/if}
          </div>
          <div class="field" class:invalid={errors.funding_type}>
            <span>ประเภทเงินทุน *</span>
            <div class="seg">{#each Object.entries(FUNDING) as [v, l] (v)}<button type="button" aria-pressed={form.funding_type === v} onclick={() => pickType(v)}>{l}</button>{/each}</div>
            {#if errors.funding_type}<small class="err">{errors.funding_type}</small>{:else}<small>ดูจากหัวสัญญา: “ระหว่าง …กับ…” = ทุนภายนอก, “จากงบประมาณ…” ของหน่วยงานเดียว = ทุนภายใน</small>{/if}
          </div>
        </div>
        <div class="field">
          <span>แหล่งเงินทุน</span>
          <div class="seg wrap">
            {#each Object.entries(FUNDING_SOURCE) as [v, l] (v)}
              <button type="button" aria-pressed={form.funding_source === v} onclick={() => pickSource(v)}>{l}</button>
            {/each}
          </div>
          <small>ไม่บังคับ · เลือกแล้วประเภทเงินทุนจะตั้งให้ตามแหล่งเงิน (งบประมาณ FF นับเป็นทุนภายใน)</small>
        </div>
        {#if form.funding_source === 'external'}
          <label class="field"><span>ชื่อแหล่งทุนภายนอก</span><input id="f-funder" bind:value={form.funder_name} /></label>
        {/if}
        <div class="two">
          <label class="field">
            <span>เลขที่สัญญา</span>
            <input id="f-ref" class="mono" bind:value={form.reference_no} placeholder="R2568E001" autocapitalize="characters" />
            {@render hint('reference_no')}
          </label>
          <label class="field" class:invalid={errors.fiscal_year_be}>
            <span>ปีงบประมาณ (พ.ศ.)</span>
            <input id="f-fy" bind:value={form.fiscal_year_be} inputmode="numeric" maxlength="4" placeholder="ว่างไว้ = คำนวณจากวันที่เอกสาร" />
            {#if errors.fiscal_year_be}<small class="err">{errors.fiscal_year_be}</small>{/if}
            {@render hint('fiscal_year')}
          </label>
        </div>
        <div class="three">
          {#each [['document_date', 'วันที่เอกสาร'], ['effective_from', 'วันเริ่มสัญญา'], ['effective_to', 'วันสิ้นสุดสัญญา']] as [k, l] (k)}
            <label class="field" class:invalid={errors[k]}>
              <span>{l}</span>
              <input id="f-{k}" bind:value={form[k]} placeholder="วว/ดด/ปปปป (พ.ศ.)" inputmode="numeric" />
              {#if errors[k]}<small class="err">{errors[k]}</small>{:else if parseThaiDate(form[k])}<small>{thDate(parseThaiDate(form[k]))}</small>{/if}
              {@render hint(k)}
            </label>
          {/each}
        </div>
        <label class="field" class:invalid={errors.budget_total}>
          <span>งบประมาณรวม (บาท)</span>
          <input id="f-budget" bind:value={form.budget_total} inputmode="decimal" placeholder="เช่น 290000" />
          {#if errors.budget_total}<small class="err">{errors.budget_total}</small>{:else if form.budget_total !== '' && !isNaN(Number(num(form.budget_total)))}<small>{money(num(form.budget_total))}</small>{/if}
          {@render hint('budget_total')}
        </label>
      </section>

      <section class="card pad stack">
        <h3>หมวดหมู่</h3>
        <p class="hint">ช่องที่ติ๊กในแบบฟอร์มถูกเลือกให้แล้ว (มีจุดสีทอง) แก้ได้ตามต้องการ</p>
        {#each groups as g (g.id)}
          {@const opts = g.options.filter((o) => o.active || o.id in form.categories)}
          {@const sugg = (form.suggestedOptions[g.key] || []).filter((l) => !g.options.some((o) => same(o.name_th, l)))}
          <div class="cat-group">
            <span class="label">{g.name_th}{g.multi ? '' : ' (เลือกได้ 1 ข้อ)'}</span>
            <div class="chips">
              {#each opts as o (o.id)}
                <button type="button" class="chip" aria-pressed={o.id in form.categories} onclick={() => toggleCat(g, o.id)}>
                  {#if form.suggestedCats.includes(o.id)}<span class="dot" title="ระบบแนะนำจากเอกสาร"></span>{/if}{o.name_th}
                </button>
              {/each}
              {#each sugg as label (label)}
                <button type="button" class="chip new" onclick={() => addOption(g, label, 'auto')} disabled={optionBusy} title="ติ๊กไว้ในเอกสารแต่ยังไม่มีในรายการ กดเพื่อเพิ่มและเลือก">
                  <span class="dot"></span>+ {label}
                </button>
              {/each}
              {#if adding === g.id}
                <input
                  id="f-opt-{g.key}"
                  class="input tag-in"
                  bind:value={newOption}
                  onkeydown={(e) => optionKey(e, g)}
                  onblur={() => (newOption.trim() ? addOption(g, newOption) : (adding = null))}
                  placeholder="ชื่อตัวเลือกใหม่ แล้วกด Enter"
                  disabled={optionBusy}
                />
              {:else}
                <button type="button" class="chip add" onclick={() => openAdd(g)}>+ เพิ่ม</button>
              {/if}
            </div>
          </div>
        {/each}
        <div class="cat-group">
          <span class="label">แท็ก</span>
          <div class="chips">
            {#each form.tags as t, i (t.name)}
              <span class="chip on">{t.name}<button type="button" class="x" onclick={() => form.tags.splice(i, 1)} aria-label="เอาแท็ก {t.name} ออก">✕</button></span>
            {/each}
            <input id="f-tag" class="input tag-in" bind:value={tagInput} onkeydown={tagKey} onblur={() => (addTag(tagInput), (tagInput = ''))} placeholder="พิมพ์แล้วกด Enter" />
          </div>
          {#if form.suggestedTags.length}
            <div class="chips sugg-tags">
              <small class="muted">แท็กที่แนะนำ (ไม่ตรงกับหมวดหมู่ที่มี):</small>
              {#each form.suggestedTags as t (t)}<button type="button" class="chip" onclick={() => addTag(t, 'auto')}>+ {t}</button>{/each}
            </div>
          {/if}
        </div>
      </section>

      <section class="card pad stack">
        <div class="row"><h3>ผู้เกี่ยวข้อง</h3><span class="spacer"></span>
          <button type="button" class="btn small ghost" onclick={addPerson}><Icon name="plus" size={15} />เพิ่มคน</button>
        </div>
        {#if form.people.length}
          <div class="rows">
            <div class="rhead person" aria-hidden="true"><span>คำนำหน้า</span><span>ชื่อ-สกุล</span><span>บทบาท</span><span>สัดส่วน %</span><span>หน่วยงาน</span><span></span></div>
            {#each form.people as p, i (i)}
              <div class="rline person">
                <label class="field pfx"><span>คำนำหน้า</span><input id="p{i}-prefix" bind:value={p.prefix_th} placeholder="ผศ.ดร." /></label>
                <label class="field nm"><span>ชื่อ-สกุล</span><input id="p{i}-name" bind:value={p.name_th} />{#if p.name_en}<small>{p.name_en}</small>{/if}</label>
                <label class="field rl"><span>บทบาท</span>
                  <select id="p{i}-role" bind:value={p.role}>{#each Object.entries(ROLE) as [v, l] (v)}<option value={v}>{l}</option>{/each}</select>
                </label>
                <label class="field pc"><span>สัดส่วน %</span><input id="p{i}-share" bind:value={p.share_pct} inputmode="decimal" /></label>
                <label class="field un"><span>หน่วยงาน</span><input id="p{i}-unit" bind:value={p.unit} /></label>
                <button type="button" class="icon-btn rm" onclick={() => form.people.splice(i, 1)} aria-label="ลบ {p.name_th || 'แถวนี้'}"><Icon name="trash" size={17} /></button>
              </div>
            {/each}
          </div>
          {#if shareTotal !== null}
            <small class="total" class:off={Math.abs(shareTotal - 100) > 0.5}>สัดส่วนรวม {shareTotal}%{Math.abs(shareTotal - 100) > 0.5 ? ' (ควรเป็น 100%)' : ''}</small>
          {/if}
        {:else}
          <p class="muted">ยังไม่มีรายชื่อ</p>
        {/if}
      </section>

      <section class="card pad stack">
        <h3>รายการงบประมาณและงวดเงิน</h3>
        {#if budgetSugg.length && !form.budget_lines.length}
          <div class="notice info"><Icon name="info" size={18} /><span>ระบบอ่านงวดเงินได้ {budgetSugg.length} งวด{budgetSugg.some((b) => b.computed) ? ' (บางงวดคำนวณจำนวนเงินจากร้อยละ ตรวจกับไฟล์อีกครั้ง)' : ''} <button type="button" class="link-btn" onclick={useBudgetSugg}>ใช้ค่าที่ระบบอ่านได้</button></span></div>
        {/if}
        {#each [['installment', 'งวดเงิน', 'เพิ่มงวด'], ['item', 'รายการค่าใช้จ่าย', 'เพิ่มรายการ']] as [type, title, addLabel] (type)}
          {@const lines = form.budget_lines.map((b, i) => [b, i]).filter(([b]) => b.line_type === type)}
          {@const sum = lineSum(type)}
          <div class="bgroup">
            <div class="row"><span class="label">{title}</span><span class="spacer"></span>
              <button type="button" class="btn small ghost" onclick={() => addLine(type)}><Icon name="plus" size={15} />{addLabel}</button>
            </div>
            {#if lines.length}
              <div class="rows">
                {#if type === 'installment'}
                  <div class="rhead inst" aria-hidden="true"><span>งวด</span><span>จำนวนเงิน (บาท)</span><span>%</span><span>กำหนดส่ง</span><span>เงื่อนไข</span><span></span></div>
                {:else}
                  <div class="rhead item" aria-hidden="true"><span>หมวด</span><span>รายการ</span><span>จำนวนเงิน (บาท)</span><span></span></div>
                {/if}
                {#each lines as [b, i] (i)}
                  <div class="rline {type === 'installment' ? 'inst' : 'item'}" class:invalid={errors[`bl${i}`]}>
                    {#if type === 'installment'}
                      <label class="field lb"><span>งวด</span><input id="b{i}-label" bind:value={b.label} /></label>
                      <label class="field am"><span>จำนวนเงิน (บาท)</span><input id="b{i}-amount" bind:value={b.amount} inputmode="decimal" onblur={() => fillPercent(b)} /></label>
                      <label class="field pc"><span>%</span><input id="b{i}-pct" bind:value={b.percent} inputmode="decimal" /></label>
                      <label class="field due"><span>กำหนดส่ง</span><input id="b{i}-due" bind:value={b.due_date} placeholder="วว/ดด/ปปปป" /></label>
                      <label class="field cond"><span>เงื่อนไข</span><input id="b{i}-cond" bind:value={b.condition} placeholder="เช่น เมื่อส่งรายงานความก้าวหน้า" /></label>
                    {:else}
                      <label class="field grp"><span>หมวด</span><input id="b{i}-group" bind:value={b.group_label} placeholder="เช่น หมวดค่าตอบแทน" /></label>
                      <label class="field lb"><span>รายการ</span><input id="b{i}-label" bind:value={b.label} /></label>
                      <label class="field am"><span>จำนวนเงิน (บาท)</span><input id="b{i}-amount" bind:value={b.amount} inputmode="decimal" /></label>
                    {/if}
                    <button type="button" class="icon-btn rm" onclick={() => form.budget_lines.splice(i, 1)} aria-label="ลบ {b.label || 'แถวนี้'}"><Icon name="trash" size={17} /></button>
                    {#if errors[`bl${i}`]}<small class="err full">{errors[`bl${i}`]}</small>{/if}
                  </div>
                {/each}
              </div>
              {#if sum !== null}
                <small class="total" class:off={budgetNum !== null && Math.abs(sum - budgetNum) > 0.005}>
                  รวม {money(sum)}{#if budgetNum !== null}{Math.abs(sum - budgetNum) > 0.005 ? ` · ไม่ตรงกับงบประมาณรวม (${money(budgetNum)})` : ' · ตรงกับงบประมาณรวม'}{/if}
                </small>
              {/if}
            {/if}
          </div>
        {/each}
      </section>

      {#if saveError}
        <div class="notice bad" role="alert">
          {#if saveError.dup}
            <span>เลขที่สัญญานี้มีอยู่แล้วในเอกสารอื่น ถ้าเป็นไฟล์ฉบับแก้ไขของสัญญาเดิม ให้ <a href="/documents/{saveError.dup}">เปิดเอกสารเดิม</a> แล้วอัปโหลดเป็นฉบับใหม่แทน</span>
          {:else}{saveError.text}{/if}
        </div>
      {/if}

      <div class="savebar">
        <a class="btn ghost" href="/documents/{id}">ยกเลิก</a>
        <span class="spacer"></span>
        {#if doc.status !== 'ready'}
          <button class="btn ghost" onclick={() => save(true)} disabled={saving}>บันทึก แล้วตรวจฉบับถัดไป</button>
        {/if}
        <button class="btn" onclick={() => save(false)} disabled={saving}>{saving ? 'กำลังบันทึก…' : 'บันทึก'}</button>
      </div>
    </div>

    {#if sidePdf && showPdf}
      <aside class="pdf card">
        {#key pdfSrc}<iframe title="ไฟล์ PDF" src={pdfSrc}></iframe>{/key}
      </aside>
    {/if}
  </div>
{/if}

<style>
  .review { max-width: 900px; margin: 0 auto; }
  .review.split { max-width: none; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; align-items: start; }
  .form-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .crumbs a { display: inline-flex; align-items: center; gap: 4px; font-size: 14px; text-decoration: none; }
  .titlebar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
  .titlebar p { font-size: 13px; overflow-wrap: anywhere; }
  .pdf { position: sticky; top: calc(var(--header-h) + 20px); height: calc(100vh - var(--header-h) - 40px); overflow: hidden; }
  .pdf iframe { width: 100%; height: 100%; border: 0; display: block; }
  textarea { resize: vertical; line-height: 1.5; }
  .seg.wrap { flex-wrap: wrap; }
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
  .three { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
  .err { color: var(--bad) !important; }
  .hints { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .sugg, .pg { border: 1px dashed var(--accent); background: var(--accent-soft); color: var(--accent-text); border-radius: 8px; padding: 1px 8px; font-size: 12.5px; text-align: left; overflow-wrap: anywhere; }
  .pg { border-style: solid; border-color: var(--border); background: var(--subtle); color: var(--muted); }
  .unsure { font-size: 12px; color: var(--warn); }
  .cat-group { display: flex; flex-direction: column; gap: 6px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .chips .chip { white-space: normal; text-align: left; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); flex: none; }
  .chip.add { border-style: dashed; color: var(--muted); background: transparent; }
  .chip.new { border-style: dashed; }
  .tag-in { width: 180px; min-height: 32px; padding: 3px 10px; font-size: 14px; }
  .sugg-tags { margin-top: 2px; }
  /* People and budget rows lay out by the card's own width (the PDF may sit beside the form):
     wide = one table row under a shared header; narrow = a small stacked card per row. */
  .rows { container-type: inline-size; display: flex; flex-direction: column; gap: 8px; }
  .rline, .rhead { display: grid; gap: 8px 10px; align-items: end; }
  .rline { padding: 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); }
  .rline.invalid { border-color: var(--bad); }
  .rline .full { grid-column: 1 / -1; }
  .rline input, .rline select { width: 100%; min-width: 0; }
  .rhead { display: none; padding: 0 11px; font-size: 12.5px; font-weight: 600; color: var(--muted); }
  .rm { align-self: end; margin-bottom: 2px; }
  .total { font-size: 12.5px; color: var(--muted); }
  .total.off { color: var(--warn); }
  .bgroup { display: flex; flex-direction: column; gap: 8px; }
  .bgroup + .bgroup { padding-top: 12px; border-top: 1px solid var(--border); }

  /* Narrow (default) */
  .person { grid-template-columns: 96px minmax(0, 1fr) 36px; grid-template-areas: 'pfx nm rm' 'rl rl rl' 'pc un un'; }
  .inst { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 36px; grid-template-areas: 'lb lb rm' 'am pc pc' 'due due due' 'cond cond cond'; }
  .item { grid-template-columns: minmax(0, 1fr) 36px; grid-template-areas: 'grp rm' 'lb lb' 'am am'; }
  .pfx { grid-area: pfx; } .nm { grid-area: nm; } .rl { grid-area: rl; } .pc { grid-area: pc; } .un { grid-area: un; }
  .lb { grid-area: lb; } .am { grid-area: am; } .due { grid-area: due; } .cond { grid-area: cond; } .grp { grid-area: grp; }
  .rline .rm { grid-area: rm; }
  @container (min-width: 460px) {
    .person { grid-template-columns: 100px minmax(0, 1fr) 150px 36px; grid-template-areas: 'pfx nm rl rm' 'pc un un un'; }
    .inst { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 80px 36px; grid-template-areas: 'lb am pc rm' 'due cond cond cond'; }
    .item { grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) 36px; grid-template-areas: 'grp lb rm' 'am am .'; }
  }
  @container (min-width: 760px) {
    .rhead { display: grid; }
    .rline .field > span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
    .rline { padding: 6px 10px; }
    .person { grid-template-columns: 100px minmax(0, 1.6fr) 140px 80px minmax(0, 1fr) 36px; grid-template-areas: 'pfx nm rl pc un rm'; }
    .inst { grid-template-columns: 110px 130px 70px 130px minmax(0, 1fr) 36px; grid-template-areas: 'lb am pc due cond rm'; }
    .item { grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.4fr) 140px 36px; grid-template-areas: 'grp lb am rm'; }
  }
  .savebar { position: sticky; bottom: 0; z-index: 5; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 12px 0; background: linear-gradient(to top, var(--bg) 70%, transparent); }
  .waiting { max-width: 520px; margin: 40px auto; padding: 32px 24px; display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
  .spin.big { width: 32px; height: 32px; border-width: 3px; }
  @media (max-width: 767px) {
    .savebar { bottom: calc(var(--bottom-h) + env(safe-area-inset-bottom)); }
    .savebar .btn { flex: 1; }
  }
</style>
