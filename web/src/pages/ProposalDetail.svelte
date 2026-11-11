<script>
  // A proposal-development grant (DESIGN §11): project facts, the KPI, and a timeline of its
  // memos (approval, changes, closing, cancellation). Programme papers ('other') show the
  // facts and file only.
  import { onDestroy } from 'svelte';
  import { get, post, patch, uploadFile, errorText, fileUrl, thai } from '../lib/api.js';
  import { trashDocs } from '../lib/trash.js';
  import { navigate } from '../lib/router.svelte.js';
  import { toast, bumpReviewCount, ui } from '../lib/state.svelte.js';
  import { STATUS, FUNDING_SOURCE, PROJECT_STATE, EVENT, OUTCOME, thDate, thDateTime, money, bytes, personName, toThaiInput, parseThaiDate } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';
  import Modal from '../components/Modal.svelte';
  import ShareDialog from '../components/ShareDialog.svelte';
  import DocumentLinks from '../components/DocumentLinks.svelte';

  let { id } = $props();
  let doc = $state(null);
  let error = $state('');
  let sharing = $state(false);
  let linksKey = $state(0);
  let confirmDelete = $state(false);
  let busy = $state(false);
  let timer;

  const reading = (f) => f && (f.ocr_status === 'pending' || f.ocr_status === 'running');
  async function load() {
    clearTimeout(timer);
    try {
      const d = await get(`/documents/${id}`);
      if (d.kind !== 'proposal_dev' && d.kind !== 'other') return navigate(`/documents/${id}`, { replace: true });
      doc = d;
      error = '';
      if (ui.shareDoc === d.id) {
        ui.shareDoc = null; // arrived from "create a new link" after a restore
        sharing = true;
      }
      // While a memo is being read, check back every few seconds.
      if (d.status === 'processing' || d.events.some((e) => reading(e.paper)) || d.papers.some(reading)) timer = setTimeout(load, 4000);
    } catch (err) {
      error = errorText(err);
    }
  }
  load();
  onDestroy(() => clearTimeout(timer));

  const grant = $derived(doc?.kind === 'proposal_dev');
  const owner = $derived(doc?.people.find((p) => p.role === 'owner'));
  const p = $derived(doc?.proposal || {});
  const remaining = $derived(doc?.budget_total != null && p.spent_total != null ? Number(doc.budget_total) - Number(p.spent_total) : null);
  const facts = $derived(
    doc
      ? [
          ['นักวิจัย', owner && personName(owner)],
          ['ภาควิชา', owner?.unit],
          ['ปีงบประมาณ', doc.fiscal_year_be && `พ.ศ. ${doc.fiscal_year_be}`],
          ['แหล่งเงินทุน', doc.funding_source && `${FUNDING_SOURCE[doc.funding_source]}${doc.funder_name ? ` · ${doc.funder_name}` : ''}`],
          ['จำนวนเงิน', doc.budget_total && money(doc.budget_total)],
          ['ระยะเวลาเบิกจ่าย', doc.effective_from && `${thDate(doc.effective_from)} – ${thDate(doc.effective_to)}`],
          ['เลขที่บันทึกขออนุมัติ', p.request_ref],
          ['เลขรับ', p.received_no],
          ['วันที่บันทึก', doc.document_date && thDate(doc.document_date)],
          ['กรอบงานวิจัย', p.research_area],
        ].filter(([, v], i) => grant || i === 2 || i === 8)
      : [],
  );

  // A file link for the memo behind a timeline entry.
  function paperUrl(e, inline = false) {
    const f = e.paper;
    if (e.paper_purpose === 'closure') return fileUrl(doc.id, { closure: f.version_no, inline });
    if (e.paper_purpose === 'paper') return fileUrl(doc.id, { paper: f.version_no, inline });
    return fileUrl(doc.id, { version: f.version_no, inline });
  }
  // What the system read from an entry's memo (date, number), offered when the entry lacks it.
  const readDate = (e) => e.paper?.readings?.document_date;
  const readRef = (e) => e.paper?.readings?.memo_ref;
  const readReceived = (e) => e.paper?.readings?.received_no;
  function detailLine(e) {
    const d = e.details || {};
    return [
      d.old_title && d.new_title && `จาก “${d.old_title}” เป็น “${d.new_title}”`,
      d.kpi_result && `ผลงาน: ${d.kpi_result}`,
      d.reason && `เหตุผล: ${d.reason}`,
      d.note,
    ].filter(Boolean);
  }

  // ───────── Attach a memo (change / other) ─────────
  let attaching = $state(null);
  let formError = $state('');
  function openAttach(type = 'title_change') {
    formError = '';
    attaching = { type, file: null, new_title: '' };
  }
  function pickFile(e, target) {
    const f = e.currentTarget.files?.[0];
    e.currentTarget.value = '';
    if (f && !(f.type === 'application/pdf' || /\.pdf$/i.test(f.name))) return toast('รับเฉพาะไฟล์ PDF', 'bad');
    if (f) target.file = f;
  }
  async function sendPaper(type, file, fields = {}) {
    const { status, data } = await uploadFile(`/documents/${id}/papers`, file, null, null, { paper_type: type, ...fields });
    if (status !== 201) throw new Error(status === 409 ? `“${file.name}” มีอยู่ในระบบแล้ว` : thai(data?.detail) || 'อัปโหลดไม่สำเร็จ');
    return data;
  }
  async function saveAttach() {
    if (!attaching.file) return (formError = 'เลือกไฟล์บันทึก (PDF)');
    if (attaching.type === 'title_change' && !attaching.new_title.trim()) return (formError = 'กรอกชื่อเรื่องใหม่');
    busy = true;
    formError = '';
    try {
      doc = await sendPaper(attaching.type, attaching.file, { new_title: attaching.type === 'title_change' ? attaching.new_title.trim() : '' });
      attaching = null;
      toast('แนบบันทึกแล้ว ระบบกำลังอ่านเอกสาร');
      load();
    } catch (err) {
      formError = err.message;
    } finally {
      busy = false;
    }
  }

  // ───────── Close (ปิดทุน) / cancel (ยกเลิก) ─────────
  let deciding = $state(null); // { mode: 'close' | 'cancel', ... }
  const latestReading = (type) => {
    const e = [...(doc?.events || [])].reverse().find((x) => x.event_type === type && x.paper);
    return e?.paper?.readings || {};
  };
  function openDecide(mode) {
    formError = '';
    const r = latestReading(mode);
    deciding =
      mode === 'close'
        ? {
            mode,
            file: null,
            date: toThaiInput(doc.closed_on || r.document_date || ''),
            ref: doc.closure_ref || r.memo_ref || '',
            result: p.kpi_result || r.kpi_result || '',
            spent: p.spent_total ?? r.spent_total ?? '',
            note: doc.closure_note || '',
          }
        : {
            mode,
            file: null,
            date: toThaiInput(doc.cancelled_on || r.document_date || ''),
            ref: doc.cancel_ref || r.memo_ref || '',
            reason: doc.cancel_reason || r.cancel_reason || '',
          };
  }
  async function saveDecide() {
    const on = parseThaiDate(deciding.date);
    if (on === null) return (formError = 'รูปแบบวันที่ไม่ถูกต้อง ใช้ วว/ดด/ปปปป เช่น 4/8/2569');
    const spent = String(deciding.spent ?? '').replace(/[,\s]/g, '');
    if (deciding.mode === 'close' && spent && isNaN(Number(spent))) return (formError = 'ใช้จ่ายจริง: ใส่ตัวเลขเท่านั้น');
    busy = true;
    formError = '';
    try {
      if (deciding.file) await sendPaper(deciding.mode, deciding.file);
      const first = deciding.mode === 'close' ? !doc.closed_at : !doc.cancelled_at;
      doc =
        deciding.mode === 'close'
          ? await post(`/documents/${id}/close`, { closed_on: on || null, closure_ref: deciding.ref || null, closure_note: deciding.note || null, kpi_result: deciding.result || null, spent_total: spent || null })
          : await post(`/documents/${id}/cancel`, { cancelled_on: on || null, cancel_ref: deciding.ref || null, cancel_reason: deciding.reason || null });
      toast(first ? (deciding.mode === 'close' ? 'ปิดทุนแล้ว' : 'ยกเลิกทุนแล้ว') : 'บันทึกแล้ว');
      deciding = null;
      load();
    } catch (err) {
      formError = err.message && !err.status ? err.message : errorText(err);
      load();
    } finally {
      busy = false;
    }
  }
  async function reopen() {
    busy = true;
    try {
      doc = await post(`/documents/${id}/reopen`);
      toast('โครงการกลับมาดำเนินการอยู่แล้ว');
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      busy = false;
    }
  }

  // ───────── Correct a timeline entry ─────────
  let editing = $state(null);
  function openEdit(e) {
    formError = '';
    editing = { id: e.id, type: e.event_type, date: toThaiInput(e.event_on || readDate(e) || ''), ref: e.memo_ref || readRef(e) || '', received: e.received_no || readReceived(e) || '', note: e.details?.note || '' };
  }
  async function saveEdit() {
    const on = parseThaiDate(editing.date);
    if (on === null) return (formError = 'รูปแบบวันที่ไม่ถูกต้อง');
    busy = true;
    try {
      doc = await patch(`/documents/${id}/events/${editing.id}`, { event_on: on || null, memo_ref: editing.ref || null, received_no: editing.received?.trim() || null, note: editing.note || null });
      editing = null;
    } catch (err) {
      formError = errorText(err);
    } finally {
      busy = false;
    }
  }

  async function newVersion(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = '';
    if (!file) return;
    busy = true;
    const { status, data } = await uploadFile(`/documents/${id}/versions`, file);
    busy = false;
    if (status === 201) {
      toast('อัปโหลดฉบับใหม่แล้ว ระบบกำลังอ่านเอกสาร');
      bumpReviewCount();
      load();
    } else toast(status === 409 ? 'ไฟล์นี้มีอยู่ในระบบแล้ว' : thai(data?.detail) || 'อัปโหลดไม่สำเร็จ', 'bad');
  }
  async function remove() {
    busy = true;
    try {
      await trashDocs([id], () => navigate(`/proposals/${id}`));
      navigate('/proposals');
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      busy = false;
      confirmDelete = false;
    }
  }
  const PAPER_TYPES = [
    ['title_change', 'เปลี่ยนชื่อเรื่อง'],
    ['budget_change', 'เปลี่ยนแปลงหมวดค่าใช้จ่าย'],
    ['other', 'บันทึกอื่น ๆ'],
  ];
</script>

{#if error}
  <div class="notice bad">{error}</div>
  <a href="/proposals">← กลับไปหน้าทุนพัฒนาข้อเสนอ</a>
{:else if !doc}
  <div class="card pad stack"><div class="skel" style="width:30%"></div><div class="skel" style="width:80%;height:22px"></div><div class="skel" style="width:60%"></div></div>
{:else}
  <div class="detail">
    <div class="crumbs"><a href="/proposals" onclick={(e) => history.length > 1 && (e.preventDefault(), history.back())}><Icon name="back" size={16} />ทุนพัฒนาข้อเสนอทั้งหมด</a></div>

    <header class="head">
      <div class="titles">
        <div class="badges">
          {#if doc.status !== 'ready'}<span class="badge {doc.status}">{STATUS[doc.status]}</span>{/if}
          {#if doc.state}<span class="badge st-{doc.state}">{PROJECT_STATE[doc.state]}</span>{/if}
          {#if !grant}<span class="badge neutral">เอกสารประกอบโครงการ</span>{/if}
        </div>
        <h1>{doc.title}</h1>
      </div>
      <div class="actions">
        <a class="btn" href={fileUrl(doc.id)}><Icon name="download" size={18} />ดาวน์โหลด</a>
        <a class="btn ghost" href={fileUrl(doc.id, { inline: true })} target="_blank" rel="noopener"><Icon name="eye" size={18} />เปิดดู</a>
        <button class="btn ghost" onclick={() => (sharing = true)}><Icon name="link" size={18} />แชร์ลิงก์</button>
        {#if doc.can_edit && grant}
          <a class="btn ghost" href="/proposals/{doc.id}/review"><Icon name="edit" size={18} />{doc.status === 'ready' ? 'แก้ไขข้อมูล' : 'ตรวจสอบข้อมูล'}</a>
        {/if}
      </div>
    </header>

    {#if doc.status === 'processing'}
      <div class="notice info"><span class="spin"></span>ระบบกำลังอ่านบันทึกและเติมข้อมูลให้อัตโนมัติ หน้านี้จะอัปเดตเอง</div>
    {:else if grant && doc.status !== 'ready' && doc.can_edit}
      <div class="notice warn"><Icon name="warn" size={18} /><span>โครงการนี้ยังไม่ได้ตรวจสอบข้อมูล <a href="/proposals/{doc.id}/review">ตรวจสอบตอนนี้</a></span></div>
    {/if}
    {#if doc.extra?.import_notes?.length}
      <div class="notice warn"><Icon name="warn" size={18} /><span>นำเข้าจากแฟ้มเดิม ตรวจอีกครั้ง: {doc.extra.import_notes.join(' · ')}</span></div>
    {/if}

    <div class="grid">
      <section class="card pad">
        <h3>{grant ? 'ข้อมูลโครงการ' : 'ข้อมูลเอกสาร'}</h3>
        <dl class="facts">
          {#each facts as [label, value] (label)}
            <dt>{label}</dt>
            <dd class={value ? '' : 'muted'}>
              {#if label === 'นักวิจัย' && owner}<a href="/people/{owner.id}">{value}</a>{:else}{value || '–'}{/if}
            </dd>
          {/each}
        </dl>
      </section>

      {#if grant}
        <section class="card pad kpi" class:late={doc.state === 'overdue'}>
          <h3>ผลงานตามตัวชี้วัด</h3>
          <dl class="facts">
            <dt>ต้องส่ง</dt><dd class={p.kpi_target ? '' : 'muted'}>{p.kpi_target || '–'}</dd>
            <dt>ภายในวันที่</dt>
            <dd class={p.kpi_due ? '' : 'muted'}>
              {p.kpi_due ? thDate(p.kpi_due) : '–'}
              {#if doc.state === 'overdue'}<span class="late-note"><Icon name="clock" size={14} />เลยกำหนดแล้ว ยังไม่ปิดทุน</span>{/if}
            </dd>
            <dt>ส่งแล้ว</dt><dd class={p.kpi_result ? '' : 'muted'}>{p.kpi_result || (doc.closed_at ? 'ไม่ระบุ' : 'ยังไม่ปิดทุน')}</dd>
            {#if p.spent_total != null}
              <dt>ใช้จ่ายจริง</dt><dd>{money(p.spent_total)}{remaining !== null ? ` · เหลือคืน ${money(remaining)}` : ''}</dd>
            {/if}
            {#if p.outcome}
              <dt>ผลการยื่นขอทุน</dt>
              <dd>
                {OUTCOME[p.outcome]}{p.outcome_funder ? ` · ${p.outcome_funder}` : ''}
                {#if p.outcome_document_id}<br /><a href="/documents/{p.outcome_document_id}">{p.outcome_document_title || 'เปิดสัญญาที่ได้รับ'}</a>{/if}
              </dd>
            {/if}
          </dl>
        </section>

        <section class="card pad wide timeline">
          <div class="row">
            <h3>ลำดับเหตุการณ์</h3>
            <span class="spacer"></span>
            {#if doc.can_edit}
              {#if doc.closed_at || doc.cancelled_at}
                <button class="btn small ghost" onclick={() => openDecide(doc.closed_at ? 'close' : 'cancel')}><Icon name="edit" size={15} />แก้ไข{doc.closed_at ? 'การปิดทุน' : 'การยกเลิก'}</button>
                <button class="btn small ghost" onclick={reopen} disabled={busy}>เปิดโครงการอีกครั้ง</button>
              {:else}
                <button class="btn small ghost" onclick={() => openAttach()}><Icon name="upload" size={15} />แนบบันทึกเปลี่ยนแปลง</button>
                <button class="btn small ghost" onclick={() => openDecide('cancel')}>ยกเลิกทุน</button>
                <button class="btn small" onclick={() => openDecide('close')}>ปิดทุน</button>
              {/if}
            {/if}
          </div>
          {#if doc.events.length}
            <ol class="events">
              {#each doc.events as e (e.id)}
                <li class="ev ev-{e.event_type}">
                  <span class="dot" aria-hidden="true"></span>
                  <div class="evbody">
                    <div class="evhead">
                      <b>{EVENT[e.event_type]}</b>
                      <span class="muted">{e.event_on ? thDate(e.event_on) : 'ไม่ระบุวันที่'}{e.memo_ref ? ` · ที่ ${e.memo_ref}` : ''}{e.received_no ? ` · เลขรับ ${e.received_no}` : ''}</span>
                      {#if doc.can_edit}<button class="link-btn edit" onclick={() => openEdit(e)}>แก้ไข</button>{/if}
                    </div>
                    {#each detailLine(e) as line, i (i)}<p class="evline">{line}</p>{/each}
                    {#if e.paper}
                      <div class="evfile">
                        <Icon name="doc" size={14} />
                        <span class="fname">{e.paper.original_filename}</span>
                        <a class="link-btn" href={paperUrl(e, true)} target="_blank" rel="noopener">เปิดดู</a>
                        <a class="link-btn" href={paperUrl(e)}>ดาวน์โหลด</a>
                      </div>
                      {#if reading(e.paper)}
                        <small class="muted"><span class="spin"></span> ระบบกำลังอ่านบันทึกนี้</small>
                      {:else if (!e.event_on && readDate(e)) || (!e.memo_ref && readRef(e)) || (!e.received_no && readReceived(e))}
                        <small class="read">ระบบอ่านได้: {[readDate(e) && `วันที่ ${thDate(readDate(e))}`, readRef(e) && `ที่ ${readRef(e)}`, !e.received_no && readReceived(e) && `เลขรับ ${readReceived(e)} (จากชื่อไฟล์)`].filter(Boolean).join(' · ')} {#if doc.can_edit}<button class="link-btn" onclick={() => openEdit(e)}>ใช้ค่านี้</button>{/if}</small>
                      {/if}
                    {/if}
                  </div>
                </li>
              {/each}
            </ol>
          {:else}
            <p class="muted">ยังไม่มีเหตุการณ์ เมื่อตรวจสอบข้อมูลโครงการแล้ว การอนุมัติทุนจะขึ้นเป็นรายการแรก</p>
          {/if}
        </section>
      {/if}

      <section class="card pad wide">
        <div class="row">
          <h3>{grant ? 'ไฟล์บันทึกขออนุมัติ' : 'ไฟล์'}</h3>
          <span class="spacer"></span>
          {#if doc.can_edit}
            <label class="btn small ghost">
              <Icon name="upload" size={15} />อัปโหลดฉบับใหม่
              <input class="sr-only" type="file" accept="application/pdf,.pdf" onchange={newVersion} disabled={busy} />
            </label>
          {/if}
        </div>
        <ul class="versions">
          {#each doc.versions as v, i (v.version_no)}
            <li>
              <span class="vno">ฉบับที่ {v.version_no}{i === 0 ? ' (ล่าสุด)' : ''}</span>
              <span class="fname">{v.original_filename}</span>
              <small class="muted">{v.page_count ? `${v.page_count} หน้า · ` : ''}{bytes(v.size_bytes)} · {thDateTime(v.created_at)}</small>
              <a class="link-btn" href={fileUrl(doc.id, { version: v.version_no })}>ดาวน์โหลด</a>
            </li>
          {/each}
        </ul>
      </section>
    </div>

    {#if doc.can_edit}<DocumentLinks id={doc.id} refresh={linksKey} />{/if}

    {#if doc.can_edit}
      <div class="danger">
        <button class="btn ghost small" onclick={() => (confirmDelete = true)}><Icon name="trash" size={15} />ย้ายไปถังขยะ</button>
      </div>
    {/if}
  </div>

  {#if sharing}<ShareDialog {doc} onclose={() => (sharing = false)} oncreated={() => linksKey++} />{/if}

  {#if attaching}
    <Modal title="แนบบันทึกเปลี่ยนแปลงโครงการ" onclose={() => !busy && (attaching = null)} width={520}>
      <div class="stack">
        <div class="field">
          <span>เรื่องของบันทึก</span>
          <div class="seg wrap">{#each PAPER_TYPES as [v, l] (v)}<button type="button" aria-pressed={attaching.type === v} onclick={() => (attaching.type = v)}>{l}</button>{/each}</div>
        </div>
        <div class="field">
          <span>ไฟล์บันทึก (PDF)</span>
          <label class="drop"><Icon name="upload" size={18} /><span>{attaching.file ? attaching.file.name : 'เลือกไฟล์'}</span><input class="sr-only" type="file" accept="application/pdf,.pdf" onchange={(e) => pickFile(e, attaching)} /></label>
        </div>
        {#if attaching.type === 'title_change'}
          <label class="field">
            <span>ชื่อเรื่องใหม่</span>
            <textarea id="a-title" rows="2" bind:value={attaching.new_title}></textarea>
            <small>ชื่อเดิม “{doc.title}” ยังค้นหาเจอเหมือนเดิม</small>
          </label>
        {/if}
        {#if formError}<div class="notice bad">{formError}</div>{/if}
      </div>
      {#snippet footer()}
        <button class="btn ghost" onclick={() => (attaching = null)} disabled={busy}>ยกเลิก</button>
        <button class="btn" onclick={saveAttach} disabled={busy}>{busy ? 'กำลังอัปโหลด…' : 'แนบบันทึก'}</button>
      {/snippet}
    </Modal>
  {/if}

  {#if deciding}
    {@const closing = deciding.mode === 'close'}
    <Modal title={closing ? (doc.closed_at ? 'แก้ไขการปิดทุน' : 'ปิดทุน') : doc.cancelled_at ? 'แก้ไขการยกเลิกทุน' : 'ยกเลิกทุน'} onclose={() => !busy && (deciding = null)} width={540}>
      <div class="stack">
        <p class="muted">{closing ? 'ปิดทุนเมื่อส่งผลงานตามตัวชี้วัดแล้ว โครงการจะย้ายไปอยู่ในกลุ่ม “ปิดทุนแล้ว” เปิดอีกครั้งได้ภายหลัง' : 'ยกเลิกทุนเมื่อได้รับอนุมัติให้ยกเลิกแล้ว เปิดอีกครั้งได้ภายหลัง'}</p>
        <div class="field">
          <span>{closing ? 'บันทึกขออนุมัติปิดทุน (PDF)' : 'บันทึกขออนุมัติยกเลิก (PDF)'}</span>
          <label class="drop"><Icon name="upload" size={18} /><span>{deciding.file ? deciding.file.name : 'เลือกไฟล์ (ไม่บังคับ)'}</span><input class="sr-only" type="file" accept="application/pdf,.pdf" onchange={(e) => pickFile(e, deciding)} /></label>
        </div>
        <div class="two">
          <label class="field">
            <span>วันที่อนุมัติ</span>
            <input id="d-date" bind:value={deciding.date} placeholder="วว/ดด/ปปปป (พ.ศ.)" inputmode="numeric" />
            {#if parseThaiDate(deciding.date)}<small>{thDate(parseThaiDate(deciding.date))}</small>{/if}
          </label>
          <label class="field"><span>เลขที่บันทึก</span><input id="d-ref" bind:value={deciding.ref} placeholder="อว 0000.00/123" /></label>
        </div>
        {#if closing}
          <label class="field"><span>ผลงานที่ส่ง</span><textarea id="d-result" rows="2" bind:value={deciding.result} placeholder="เช่น ข้อเสนอโครงการสำหรับขอทุนวิจัยภายนอก"></textarea></label>
          <label class="field"><span>ใช้จ่ายจริง (บาท)</span><input id="d-spent" bind:value={deciding.spent} inputmode="decimal" /></label>
          <label class="field"><span>หมายเหตุ</span><textarea id="d-note" rows="2" bind:value={deciding.note}></textarea></label>
        {:else}
          <label class="field"><span>เหตุผล</span><textarea id="d-reason" rows="3" bind:value={deciding.reason}></textarea></label>
        {/if}
        {#if formError}<div class="notice bad">{formError}</div>{/if}
      </div>
      {#snippet footer()}
        <button class="btn ghost" onclick={() => (deciding = null)} disabled={busy}>ยกเลิก</button>
        <button class="btn" onclick={saveDecide} disabled={busy}>{busy ? 'กำลังบันทึก…' : closing ? (doc.closed_at ? 'บันทึก' : 'ปิดทุน') : doc.cancelled_at ? 'บันทึก' : 'ยกเลิกทุน'}</button>
      {/snippet}
    </Modal>
  {/if}

  {#if editing}
    <Modal title="แก้ไข: {EVENT[editing.type]}" onclose={() => !busy && (editing = null)} width={480}>
      <div class="stack">
        <div class="two">
          <label class="field">
            <span>วันที่ในบันทึก</span>
            <input id="e-date" bind:value={editing.date} placeholder="วว/ดด/ปปปป (พ.ศ.)" inputmode="numeric" />
            {#if parseThaiDate(editing.date)}<small>{thDate(parseThaiDate(editing.date))}</small>{/if}
          </label>
          <label class="field"><span>เลขที่บันทึก</span><input id="e-ref" bind:value={editing.ref} /></label>
          <label class="field"><span>เลขรับ</span><input id="e-received" bind:value={editing.received} inputmode="numeric" /></label>
        </div>
        <label class="field"><span>หมายเหตุ</span><textarea id="e-note" rows="2" bind:value={editing.note}></textarea></label>
        {#if formError}<div class="notice bad">{formError}</div>{/if}
      </div>
      {#snippet footer()}
        <button class="btn ghost" onclick={() => (editing = null)} disabled={busy}>ยกเลิก</button>
        <button class="btn" onclick={saveEdit} disabled={busy}>บันทึก</button>
      {/snippet}
    </Modal>
  {/if}

  {#if confirmDelete}
    <Modal title="ย้ายไปถังขยะ?" onclose={() => (confirmDelete = false)}>
      <p>“{doc.title}” และบันทึกทั้งหมดของโครงการนี้จะหายไปจากการค้นหา และลิงก์แชร์จะใช้ไม่ได้ทันที กู้คืนได้จาก “ถังขยะของฉัน” ในเมนูบัญชี</p>
      {#snippet footer()}
        <button class="btn ghost" onclick={() => (confirmDelete = false)}>ยกเลิก</button>
        <button class="btn danger" onclick={remove} disabled={busy}>ย้ายไปถังขยะ</button>
      {/snippet}
    </Modal>
  {/if}
{/if}

<style>
  .detail { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; margin: 0 auto; }
  .crumbs a { display: inline-flex; align-items: center; gap: 4px; font-size: 14px; text-decoration: none; }
  .head { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
  .titles { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; min-width: 0; flex: 1 1 360px; }
  .titles h1 { font-size: 23px; line-height: 1.4; overflow-wrap: anywhere; }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 16px; }
  .grid .wide { grid-column: 1 / -1; }
  section h3 { margin-bottom: 10px; }
  .facts { display: grid; grid-template-columns: auto 1fr; gap: 6px 16px; margin: 0; font-size: 14px; }
  .facts dt { color: var(--muted); white-space: nowrap; }
  .facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .kpi.late { border-color: var(--warn); }
  .late-note { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; color: var(--warn); font-size: 13px; }
  .timeline .row { flex-wrap: wrap; gap: 8px; margin-bottom: 6px; }
  .timeline h3 { margin: 0; }
  .events { list-style: none; margin: 0; padding: 0; position: relative; }
  .ev { position: relative; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 10px; padding: 10px 0; }
  .ev::before { content: ''; position: absolute; left: 6px; top: 0; bottom: 0; width: 2px; background: var(--border); }
  .ev:first-child::before { top: 18px; }
  .ev:last-child::before { bottom: calc(100% - 18px); }
  .dot { position: relative; width: 14px; height: 14px; border-radius: 50%; margin-top: 4px; background: var(--surface); border: 3px solid var(--info); }
  .ev-close .dot { border-color: var(--ok); background: var(--ok); }
  .ev-cancel .dot { border-color: var(--muted); background: var(--muted); }
  .ev-title_change .dot, .ev-budget_change .dot { border-color: var(--accent); }
  .evbody { display: flex; flex-direction: column; gap: 3px; min-width: 0; font-size: 14px; }
  .evhead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
  .evhead .edit { margin-left: auto; font-size: 13px; }
  .evline { margin: 0; overflow-wrap: anywhere; }
  .evfile { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); min-width: 0; }
  .read { color: var(--muted); overflow-wrap: anywhere; }
  .versions { list-style: none; margin: 0; padding: 0; }
  .versions li { display: grid; grid-template-columns: 120px minmax(0, 1fr) auto auto; gap: 12px; align-items: baseline; padding: 8px 0; border-top: 1px solid var(--border); font-size: 14px; }
  .versions li:first-child { border-top: 0; }
  .vno { font-weight: 600; }
  .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .danger { display: flex; justify-content: flex-end; }
  .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
  .seg.wrap { flex-wrap: wrap; }
  textarea { resize: vertical; line-height: 1.5; }
  .drop { display: flex; gap: 8px; align-items: center; padding: 12px; border: 1px dashed var(--border-strong); border-radius: 10px; cursor: pointer; font-size: 14px; color: var(--muted); overflow-wrap: anywhere; }
  .drop:hover { background: var(--subtle); }
  @media (max-width: 640px) {
    .titles h1 { font-size: 19px; }
    .actions { width: 100%; }
    .actions > :first-child { flex: 1 1 100%; min-height: 46px; }
    .actions > :not(:first-child) { flex: 1; }
    .versions li { grid-template-columns: 1fr auto; }
    .versions .fname, .versions small { grid-column: 1; }
    .timeline .row .btn { flex: 1; }
  }
</style>
