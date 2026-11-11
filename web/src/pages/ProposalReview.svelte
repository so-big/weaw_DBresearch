<script>
  // Review / edit a proposal-development grant (DESIGN §11). First review: pre-filled from what
  // the memo reader found; later edits: the saved values, with the readings as hints.
  import { onDestroy } from 'svelte';
  import { get, put, post, errorText, fileUrl } from '../lib/api.js';
  import { navigate, setLeaveGuard } from '../lib/router.svelte.js';
  import { createDraft } from '../lib/draft.js';
  import { toast, screen, session, bumpReviewCount, isAdmin } from '../lib/state.svelte.js';
  import { FUNDING_SOURCE, OUTCOME, BE, thDate, money, toThaiInput, parseThaiDate, docPath } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';

  let { id } = $props();

  let doc = $state(null);
  let sug = $state(null); // the memo reader's payload: { kind, fields, warnings }
  let form = $state(null);
  let errors = $state({});
  let saveError = $state('');
  let saving = $state(false);
  let loadError = $state('');
  let waiting = $state(false);
  let skipWait = $state(false);
  let showPdf = $state(true);
  let pdfPage = $state(null);
  let timer;

  const fields = $derived(sug?.fields || {});
  const fresh = $derived(doc && doc.status !== 'ready');
  const LABEL = {
    title: 'ชื่อโครงการ',
    owner: 'ชื่อนักวิจัย',
    fiscal_year: 'ปีงบประมาณ',
    budget_total: 'จำนวนเงิน',
    new_title: 'ชื่อเรื่องใหม่',
  };

  async function load() {
    clearTimeout(timer);
    try {
      const [d, a] = await Promise.all([get(`/documents/${id}`), get(`/documents/${id}/autofill`)]);
      if (d.kind !== 'proposal_dev') return navigate(`/documents/${id}/review`, { replace: true });
      doc = d;
      sug = a.suggestions || {};
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
  const snapshot = (f) => JSON.stringify(f);
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

  function splitOwner(text) {
    // 'ผศ.ดร. สมมติ ทดสอบดี' → prefix + name (the reader keeps the prefix first).
    const m = (text || '').match(/^((?:\S*\.)+)\s*(.*)$/);
    return m ? { prefix: m[1], name: m[2] } : { prefix: '', name: text || '' };
  }

  function buildForm(d, s) {
    const F = s.fields || {};
    const first = d.status !== 'ready';
    const pick = (name, current) => (first && F[name]?.value != null ? F[name].value : current);
    const owner = d.people.find((p) => p.role === 'owner');
    const read = splitOwner(F.owner?.value);
    const p = d.proposal || {};
    const fy = d.fiscal_year || (first ? F.fiscal_year?.value : null);
    return {
      title: (first && F.title?.value) || d.title || '',
      prefix: owner?.prefix_th || (first ? read.prefix : '') || '',
      name: owner?.name_th || (first ? read.name : '') || '',
      department: owner?.unit || (first ? F.department?.value : '') || '',
      fiscal_year_be: fy ? String(fy + BE) : '',
      funding_source: d.funding_source || (first ? F.funding_source?.value : '') || '',
      funder_name: d.funder_name || '',
      budget_total: pick('budget_total', d.budget_total) ?? '',
      document_date: toThaiInput(pick('document_date', d.document_date)),
      effective_from: toThaiInput(pick('effective_from', d.effective_from)),
      effective_to: toThaiInput(pick('effective_to', d.effective_to)),
      request_ref: p.request_ref || (first ? F.memo_ref?.value : '') || '',
      research_area: p.research_area || (first ? F.research_area?.value : '') || '',
      kpi_target: p.kpi_target || (first ? F.kpi_target?.value : '') || '',
      kpi_due: toThaiInput(p.kpi_due || (first ? F.kpi_due?.value : '')),
      kpi_result: p.kpi_result || '',
      spent_total: p.spent_total ?? '',
      outcome: p.outcome || '',
      outcome_funder: p.outcome_funder || '',
      outcome_document_id: p.outcome_document_id || null,
      outcome_document_title: p.outcome_document_title || '',
    };
  }

  // ───────── Hints: what the reader found, when it differs from the box ─────────
  const KEY = { fiscal_year: 'fiscal_year_be', memo_ref: 'request_ref' };
  function asForm(name, v) {
    if (/date|effective|kpi_due/.test(name)) return toThaiInput(v);
    if (name === 'fiscal_year') return String(Number(v) + BE);
    return String(v);
  }
  function shown(name, v) {
    if (/date|effective|kpi_due/.test(name)) return thDate(v);
    if (name === 'budget_total') return money(v);
    if (name === 'fiscal_year') return `พ.ศ. ${Number(v) + BE}`;
    if (name === 'funding_source') return FUNDING_SOURCE[v] || v;
    return String(v);
  }
  function hintFor(name) {
    const f = fields[name];
    if (!f || f.value == null || !form) return null;
    const key = KEY[name] || name;
    const value = name === 'owner' ? `${form.prefix} ${form.name}` : form[key];
    const same = String(value ?? '').replace(/\s/g, '') === asForm(name, f.value).replace(/\s/g, '');
    return same ? null : f;
  }
  function useHint(name) {
    const f = fields[name];
    if (name === 'owner') {
      const r = splitOwner(f.value);
      form.prefix = r.prefix;
      form.name = r.name;
    } else form[KEY[name] || name] = asForm(name, f.value);
  }
  function gotoPage(p) {
    if (!p) return;
    pdfPage = p;
    showPdf = true;
  }

  const warnings = $derived(
    fresh
      ? (sug?.warnings || []).map((w) =>
          w.code === 'missing_field'
            ? `ไม่พบ${LABEL[w.field] || w.field}ในบันทึก กรุณากรอกเอง`
            : w.code === 'unknown_paper_type'
              ? 'ระบบไม่แน่ใจว่าไฟล์นี้เป็นบันทึกขออนุมัติทุน ตรวจสอบว่าอัปโหลดถูกไฟล์'
              : w.code === 'ocr_failed'
                ? 'ระบบอ่านไฟล์นี้ไม่สำเร็จ กรุณากรอกข้อมูลเอง'
                : w.code,
        )
      : [],
  );
  const notRequest = $derived(fresh && sug?.kind && sug.kind !== 'request');

  // ───────── The contract the proposal won (search contracts by title / number) ─────────
  let contractQ = $state('');
  let contractHits = $state([]);
  let contractTimer;
  function findContract(e) {
    contractQ = e.currentTarget.value;
    clearTimeout(contractTimer);
    if (contractQ.trim().length < 2) return (contractHits = []);
    contractTimer = setTimeout(async () => {
      try {
        contractHits = (await get('/documents', { section: 'contracts', q: contractQ.trim(), page_size: 6 })).items;
      } catch {
        contractHits = [];
      }
    }, 250);
  }
  function linkContract(d) {
    form.outcome_document_id = d.id;
    form.outcome_document_title = d.title;
    contractQ = '';
    contractHits = [];
  }

  // ───────── Save ─────────
  const num = (v) => (v === '' || v == null ? null : String(v).replace(/[,\s]/g, ''));
  function validate() {
    const e = {};
    if (!form.title.trim()) e.title = 'กรุณากรอกชื่อโครงการ';
    if (!form.funding_source) e.funding_source = 'เลือกแหล่งเงินทุน';
    for (const k of ['document_date', 'effective_from', 'effective_to', 'kpi_due']) {
      if (parseThaiDate(form[k]) === null) e[k] = 'รูปแบบวันที่ไม่ถูกต้อง ใช้ วว/ดด/ปปปป เช่น 1/10/2568';
    }
    const fy = form.fiscal_year_be.trim();
    if (fy && !/^\d{4}$/.test(fy)) e.fiscal_year_be = 'ใส่ปี พ.ศ. 4 หลัก เช่น 2569';
    for (const k of ['budget_total', 'spent_total']) {
      if (form[k] !== '' && isNaN(Number(num(form[k])))) e[k] = 'ใส่ตัวเลขเท่านั้น';
    }
    return e;
  }

  async function save(next) {
    errors = validate();
    saveError = '';
    if (Object.keys(errors).length) {
      toast('กรุณาแก้ช่องที่มีเครื่องหมายแดง', 'bad');
      return;
    }
    const body = {
      title: form.title.trim(),
      kind: 'proposal_dev',
      funding_source: form.funding_source,
      funder_name: form.funding_source === 'external' ? form.funder_name.trim() || null : null,
      document_date: parseThaiDate(form.document_date) || null,
      effective_from: parseThaiDate(form.effective_from) || null,
      effective_to: parseThaiDate(form.effective_to) || null,
      fiscal_year: form.fiscal_year_be.trim() ? Number(form.fiscal_year_be) - BE : null,
      budget_total: num(form.budget_total),
      // Kept as they are: grants have no categories in the form; tags stay.
      categories: doc.categories.map((c) => ({ category_id: c.id, source: c.source })),
      tags: doc.tags.map((t) => ({ name: t.name, source: t.source })),
      people: form.name.trim()
        ? [{ prefix_th: form.prefix.trim() || null, name_th: form.name.trim(), role: 'owner', unit: form.department.trim() || null }]
        : [],
      proposal: {
        request_ref: form.request_ref.trim() || null,
        research_area: form.research_area.trim() || null,
        kpi_target: form.kpi_target.trim() || null,
        kpi_due: parseThaiDate(form.kpi_due) || null,
        kpi_result: form.kpi_result.trim() || null,
        spent_total: num(form.spent_total),
        outcome: form.outcome || null,
        outcome_funder: form.outcome ? form.outcome_funder.trim() || null : null,
        outcome_document_id: form.outcome === 'won' ? form.outcome_document_id : null,
      },
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
      } else navigate(`/proposals/${id}`);
    } catch (err) {
      saveError = errorText(err);
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

  let innerWidth = $state(window.innerWidth);
  const sidePdf = $derived(screen.wide && innerWidth >= 1180);
  const pdfSrc = $derived(`${fileUrl(id, { inline: true })}${pdfPage ? `#page=${pdfPage}` : ''}`);
</script>

<svelte:window bind:innerWidth onbeforeunload={warnUnload} />

{#snippet hint(name)}
  {@const f = hintFor(name)}
  {#if f}
    <div class="hints">
      {#if f.page}<button type="button" class="pg" onclick={() => gotoPage(f.page)}>หน้า {f.page}</button>{/if}
      <button type="button" class="sugg" onclick={() => useHint(name)} title="ใช้ค่านี้">ระบบอ่านได้: {shown(name, f.value)}</button>
    </div>
  {/if}
{/snippet}

{#snippet dateField(k, label)}
  <label class="field" class:invalid={errors[k]}>
    <span>{label}</span>
    <input id="p-{k}" bind:value={form[k]} placeholder="วว/ดด/ปปปป (พ.ศ.)" inputmode="numeric" />
    {#if errors[k]}<small class="err">{errors[k]}</small>{:else if parseThaiDate(form[k])}<small>{thDate(parseThaiDate(form[k]))}</small>{/if}
    {@render hint(k)}
  </label>
{/snippet}

{#if loadError}
  <div class="notice bad">{loadError}</div>
{:else if !doc}
  <div class="card pad stack"><div class="skel" style="width:30%"></div><div class="skel" style="width:70%;height:20px"></div><div class="skel" style="width:90%"></div></div>
{:else if !doc.can_edit}
  <div class="notice warn">เฉพาะผู้อัปโหลดหรือผู้ดูแลระบบเท่านั้นที่แก้ไขข้อมูลโครงการนี้ได้</div>
  <a href="/proposals/{id}">← กลับไปหน้าโครงการ</a>
{:else if waiting}
  <div class="card waiting enter">
    <span class="spin big"></span>
    <h2>ระบบกำลังอ่านบันทึกขออนุมัติทุน</h2>
    <p class="muted">ใช้เวลาประมาณ 1 นาทีต่อไฟล์ เมื่อเสร็จ ฟอร์มจะเติมข้อมูลให้อัตโนมัติ</p>
    <div class="row">
      <a class="btn ghost" href="/review">กลับไปรายการรอตรวจสอบ</a>
      <button class="btn ghost" onclick={startManual}>กรอกเองเลย</button>
    </div>
  </div>
{:else if form}
  <div class="review" class:split={sidePdf && showPdf}>
    <div class="form-col">
      <div class="crumbs"><a href="/proposals/{id}"><Icon name="back" size={16} />กลับไปหน้าโครงการ</a></div>
      <div class="titlebar">
        <div>
          <h1>{doc.status === 'ready' ? 'แก้ไขข้อมูลโครงการ' : 'ตรวจสอบข้อมูลโครงการ'}</h1>
          <p class="muted">ทุนพัฒนาข้อเสนอโครงการวิจัย · {doc.versions[0]?.original_filename}</p>
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
        <div class="notice info"><Icon name="info" size={18} /><span>ระบบเติมข้อมูลจากบันทึกขออนุมัติทุนให้แล้ว ตรวจและแก้ให้ถูกต้องก่อนบันทึก ค่าที่ระบบอ่านได้จะแสดงใต้ช่อง กดเพื่อใช้ค่านั้น</span></div>
      {/if}
      {#if notRequest}
        <div class="notice warn"><Icon name="warn" size={18} /><span>ไฟล์นี้ดูเหมือนเป็นบันทึก{sug.kind === 'close' ? 'ขอปิดทุน' : sug.kind === 'cancel' ? 'ขอยกเลิกทุน' : 'เปลี่ยนแปลงโครงการ'} ไม่ใช่บันทึกขออนุมัติทุน ถ้าใช่ ให้แนบไฟล์นี้จากหน้าโครงการเดิมแทน</span></div>
      {/if}
      {#each warnings as w, i (i)}
        <div class="notice warn"><Icon name="warn" size={18} /><span>{w}</span></div>
      {/each}

      <section class="card pad stack">
        <h3>ข้อมูลโครงการ</h3>
        <label class="field" class:invalid={errors.title}>
          <span>ชื่อโครงการ *</span>
          <textarea id="p-title" rows="2" bind:value={form.title}></textarea>
          {#if errors.title}<small class="err">{errors.title}</small>{/if}
          {@render hint('title')}
        </label>
        <div class="who">
          <label class="field"><span>คำนำหน้า</span><input id="p-prefix" bind:value={form.prefix} placeholder="ผศ.ดร." /></label>
          <label class="field"><span>นักวิจัย (ผู้รับทุน)</span><input id="p-name" bind:value={form.name} placeholder="ชื่อ นามสกุล" /></label>
        </div>
        {@render hint('owner')}
        <label class="field">
          <span>ภาควิชา</span>
          <input id="p-dept" bind:value={form.department} placeholder="เช่น ภาควิชาวิศวกรรมเครื่องกล" />
          {@render hint('department')}
        </label>
        <div class="field" class:invalid={errors.funding_source}>
          <span>แหล่งเงินทุน *</span>
          <div class="seg wrap">{#each Object.entries(FUNDING_SOURCE) as [v, l] (v)}<button type="button" aria-pressed={form.funding_source === v} onclick={() => (form.funding_source = v)}>{l}</button>{/each}</div>
          {#if errors.funding_source}<small class="err">{errors.funding_source}</small>{:else}<small>งบประมาณ FF รายได้ ม.นเรศวร และรายได้คณะ นับเป็นทุนภายใน · แหล่งทุนภายนอก นับเป็นทุนภายนอก</small>{/if}
          {@render hint('funding_source')}
        </div>
        {#if form.funding_source === 'external'}
          <label class="field"><span>ชื่อแหล่งทุนภายนอก</span><input id="p-funder" bind:value={form.funder_name} /></label>
        {/if}
        <div class="two">
          <label class="field" class:invalid={errors.fiscal_year_be}>
            <span>ปีงบประมาณ (พ.ศ.)</span>
            <input id="p-fy" bind:value={form.fiscal_year_be} inputmode="numeric" maxlength="4" placeholder="ว่างไว้ = คำนวณจากวันที่บันทึก" />
            {#if errors.fiscal_year_be}<small class="err">{errors.fiscal_year_be}</small>{/if}
            {@render hint('fiscal_year')}
          </label>
          <label class="field" class:invalid={errors.budget_total}>
            <span>จำนวนเงินที่ได้รับ (บาท)</span>
            <input id="p-budget" bind:value={form.budget_total} inputmode="decimal" placeholder="เช่น 20000" />
            {#if errors.budget_total}<small class="err">{errors.budget_total}</small>{:else if form.budget_total !== '' && !isNaN(Number(num(form.budget_total)))}<small>{money(num(form.budget_total))}</small>{/if}
            {@render hint('budget_total')}
          </label>
        </div>
        <div class="two">
          <label class="field">
            <span>เลขที่บันทึกขออนุมัติ</span>
            <input id="p-ref" bind:value={form.request_ref} placeholder="อว 0000.00/123" />
            {@render hint('memo_ref')}
          </label>
          {@render dateField('document_date', 'วันที่บันทึก')}
        </div>
        <div class="two">
          {@render dateField('effective_from', 'ระยะเวลาเบิกจ่าย ตั้งแต่')}
          {@render dateField('effective_to', 'ถึง')}
        </div>
      </section>

      <section class="card pad stack">
        <h3>ผลงานที่ต้องส่ง (ตัวชี้วัด)</h3>
        <label class="field">
          <span>กรอบงานวิจัย</span>
          <input id="p-area" bind:value={form.research_area} placeholder="เช่น เทคโนโลยีพลังงาน" />
          {@render hint('research_area')}
        </label>
        <label class="field">
          <span>ผลงานที่ต้องส่ง</span>
          <textarea id="p-kpi" rows="2" bind:value={form.kpi_target} placeholder="เช่น ข้อเสนอโครงการสำหรับขอทุนวิจัยภายนอก และ Impact Pathway"></textarea>
          {@render hint('kpi_target')}
        </label>
        {@render dateField('kpi_due', 'ส่งผลงานภายในวันที่')}
      </section>

      <details class="card pad stack outcome" open={!!(doc.closed_at || form.kpi_result || form.outcome)}>
        <summary><h3>ผลการดำเนินงาน</h3><small class="muted">กรอกเมื่อปิดทุน หรือเมื่อทราบผลการยื่นขอทุน</small></summary>
        <label class="field">
          <span>ผลงานที่ส่งแล้ว</span>
          <textarea id="p-result" rows="2" bind:value={form.kpi_result}></textarea>
        </label>
        <label class="field" class:invalid={errors.spent_total}>
          <span>ใช้จ่ายจริง (บาท)</span>
          <input id="p-spent" bind:value={form.spent_total} inputmode="decimal" />
          {#if errors.spent_total}<small class="err">{errors.spent_total}</small>{:else if form.spent_total !== '' && form.budget_total !== '' && !isNaN(Number(num(form.spent_total)))}<small>เหลือคืน {money(Number(num(form.budget_total)) - Number(num(form.spent_total)))}</small>{/if}
        </label>
        <div class="field">
          <span>ผลการยื่นขอทุนภายนอก</span>
          <div class="seg wrap">
            <button type="button" aria-pressed={!form.outcome} onclick={() => (form.outcome = '')}>ยังไม่ทราบ</button>
            {#each Object.entries(OUTCOME) as [v, l] (v)}<button type="button" aria-pressed={form.outcome === v} onclick={() => (form.outcome = v)}>{l}</button>{/each}
          </div>
        </div>
        {#if form.outcome}
          <label class="field"><span>แหล่งทุนที่ยื่น</span><input id="p-ofunder" bind:value={form.outcome_funder} placeholder="เช่น วช. หรือ บพข." /></label>
        {/if}
        {#if form.outcome === 'won'}
          <div class="field">
            <span>สัญญาทุนวิจัยที่ได้รับ (ถ้ามีในระบบ)</span>
            {#if form.outcome_document_id}
              <div class="linked"><Icon name="link" size={15} /><a href="/documents/{form.outcome_document_id}">{form.outcome_document_title || 'สัญญาที่เชื่อมไว้'}</a><button type="button" class="link-btn" onclick={() => (form.outcome_document_id = null)}>เอาออก</button></div>
            {:else}
              <input id="p-contract" value={contractQ} oninput={findContract} placeholder="พิมพ์ชื่อเรื่องหรือเลขที่สัญญา" autocomplete="off" />
              {#if contractHits.length}
                <ul class="hits">
                  {#each contractHits as d (d.id)}
                    <li><button type="button" onclick={() => linkContract(d)}><b>{d.reference_no || 'ไม่มีเลขที่'}</b> {d.title}</button></li>
                  {/each}
                </ul>
              {/if}
            {/if}
          </div>
        {/if}
      </details>

      {#if saveError}<div class="notice bad" role="alert">{saveError}</div>{/if}

      <div class="savebar">
        <a class="btn ghost" href="/proposals/{id}">ยกเลิก</a>
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
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
  .who { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 10px; }
  .seg.wrap { flex-wrap: wrap; }
  .err { color: var(--bad) !important; }
  .hints { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .sugg, .pg { border: 1px dashed var(--accent); background: var(--accent-soft); color: var(--accent-text); border-radius: 8px; padding: 1px 8px; font-size: 12.5px; text-align: left; overflow-wrap: anywhere; }
  .pg { border-style: solid; border-color: var(--border); background: var(--subtle); color: var(--muted); }
  .outcome summary { list-style: none; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; cursor: pointer; }
  .outcome summary::-webkit-details-marker { display: none; }
  .outcome summary h3 { margin: 0; }
  .outcome[open] summary { margin-bottom: 4px; }
  .linked { display: flex; align-items: center; gap: 8px; font-size: 14px; overflow-wrap: anywhere; }
  .hits { list-style: none; margin: 4px 0 0; padding: 4px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
  .hits button { width: 100%; text-align: left; border: 0; background: none; padding: 8px; border-radius: 8px; font-size: 14px; color: var(--text); overflow-wrap: anywhere; }
  .hits button:hover { background: var(--subtle); }
  .savebar { position: sticky; bottom: 0; z-index: 5; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 12px 0; background: linear-gradient(to top, var(--bg) 70%, transparent); }
  .waiting { max-width: 520px; margin: 40px auto; padding: 32px 24px; display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
  .spin.big { width: 32px; height: 32px; border-width: 3px; }
  @media (max-width: 767px) {
    .savebar { bottom: calc(var(--bottom-h) + env(safe-area-inset-bottom)); }
    .savebar .btn { flex: 1; }
  }
</style>
