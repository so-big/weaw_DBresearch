<script>
  import { onDestroy } from 'svelte';
  import { get, post, uploadFile, errorText, fileUrl, thai } from '../lib/api.js';
  import { trashDocs } from '../lib/trash.js';
  import { navigate } from '../lib/router.svelte.js';
  import { toast, screen, bumpReviewCount, ui } from '../lib/state.svelte.js';
  import { STATUS, KIND, FUNDING, FUNDING_SOURCE, ROLE, thDate, thDateTime, money, bytes, personName, toThaiInput, parseThaiDate } from '../lib/format.js';
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
  let versionInput = $state();
  let timer;

  async function load() {
    clearTimeout(timer);
    try {
      const d = await get(`/documents/${id}`);
      if (d.kind === 'proposal_dev' || d.kind === 'other') return navigate(`/proposals/${id}`, { replace: true });
      doc = d;
      error = '';
      if (ui.shareDoc === d.id) {
        ui.shareDoc = null; // arrived from "create a new link" after a restore
        sharing = true;
      }
      // While the scan (or a closing paper) is being read, check back every few seconds.
      const reading = doc.closure_files.some((f) => f.ocr_status === 'pending' || f.ocr_status === 'running');
      if (doc.status === 'processing' || reading) timer = setTimeout(load, 4000);
    } catch (err) {
      error = errorText(err);
    }
  }
  load();
  onDestroy(() => clearTimeout(timer));

  const groupNames = { agency: 'แหล่งทุน', grant_programme: 'โครงการทุน', research_type: 'ประเภทการวิจัย', research_group: 'กลุ่มการวิจัย', grant_type: 'ประเภททุน', discipline: 'สาขาวิชาการ' };
  function byGroup(list) {
    const out = new Map();
    for (const c of list) out.set(c.group_key, [...(out.get(c.group_key) || []), c]);
    return [...out];
  }
  const facts = $derived(
    doc
      ? [
          ['เลขที่สัญญา', doc.reference_no, 'cno'],
          ['ประเภทเอกสาร', KIND[doc.kind]],
          ['ประเภทเงินทุน', FUNDING[doc.funding_type]],
          ['แหล่งเงินทุน', doc.funding_source && `${FUNDING_SOURCE[doc.funding_source]}${doc.funder_name ? ` · ${doc.funder_name}` : ''}`],
          ['ปีงบประมาณ', doc.fiscal_year_be && `พ.ศ. ${doc.fiscal_year_be}`],
          ['วันที่เอกสาร', doc.document_date && thDate(doc.document_date)],
          ['ระยะเวลา', doc.effective_from && `${thDate(doc.effective_from)} – ${thDate(doc.effective_to)}`],
          ['งบประมาณรวม', doc.budget_total && money(doc.budget_total)],
        ]
      : [],
  );

  async function remove() {
    busy = true;
    try {
      await trashDocs([id], () => navigate(`/documents/${id}`));
      navigate('/documents');
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      busy = false;
      confirmDelete = false;
    }
  }

  // ───────── Close the project (ปิดโครงการ) ─────────
  let closing = $state(null); // the close/edit form while open
  let closeBusy = $state(false);
  let closeError = $state('');
  const PAPER = { memo: 'บันทึกขอปิดโครงการ', resolution: 'มติที่ประชุม' };
  const reading = $derived.by(() => {
    // The newest closing paper's readings: dates and reference to offer in the form.
    const out = {};
    for (const f of doc?.closure_files || []) {
      const r = f.readings || {};
      out.date ??= r.meeting_date || r.memo_date;
      out.ref ??= r.memo_no || (r.meeting_no ? `มติที่ประชุม ครั้งที่ ${r.meeting_no}${r.agenda ? ` วาระที่ ${r.agenda}` : ''}` : undefined);
    }
    return out;
  });
  const papersReading = $derived((doc?.closure_files || []).some((f) => f.ocr_status === 'pending' || f.ocr_status === 'running'));
  function openClose() {
    closeError = '';
    closing = {
      files: [],
      date: toThaiInput(doc.closed_on || reading.date || ''),
      ref: doc.closure_ref || reading.ref || '',
      note: doc.closure_note || '',
    };
  }
  function pickPapers(e) {
    const picked = [...(e.currentTarget.files || [])].filter((f) => f.type === 'application/pdf' || /\.pdf$/i.test(f.name));
    closing.files.push(...picked);
    e.currentTarget.value = '';
  }
  async function attachPapers(files) {
    for (const file of files) {
      const { status, data } = await uploadFile(`/documents/${id}/closure-files`, file);
      if (status !== 201) throw new Error(status === 409 ? `“${file.name}” มีอยู่ในระบบแล้ว` : thai(data?.detail) || `อัปโหลด “${file.name}” ไม่สำเร็จ`);
    }
  }
  async function saveClose() {
    const closedOn = parseThaiDate(closing.date);
    if (closedOn === null) return (closeError = 'รูปแบบวันที่ไม่ถูกต้อง ใช้ วว/ดด/ปปปป เช่น 7/8/2568');
    closeBusy = true;
    closeError = '';
    try {
      await attachPapers(closing.files);
      closing.files = [];
      const first = !doc.closed_at;
      doc = await post(`/documents/${id}/close`, { closed_on: closedOn || null, closure_ref: closing.ref || null, closure_note: closing.note || null });
      closing = null;
      toast(first ? 'ปิดโครงการแล้ว ย้ายไปอยู่ในคลังโครงการที่ปิดแล้ว' : 'บันทึกข้อมูลการปิดโครงการแล้ว');
      load();
    } catch (err) {
      closeError = err.message && !err.status ? err.message : errorText(err);
      load();
    } finally {
      closeBusy = false;
    }
  }
  async function addPaper(e) {
    const files = [...(e.currentTarget.files || [])];
    e.currentTarget.value = '';
    if (!files.length) return;
    busy = true;
    try {
      await attachPapers(files);
      toast('แนบเอกสารปิดโครงการแล้ว ระบบกำลังอ่านเอกสาร');
    } catch (err) {
      toast(err.message, 'bad');
    } finally {
      busy = false;
      load();
    }
  }
  async function reopen() {
    busy = true;
    try {
      doc = await post(`/documents/${id}/reopen`);
      toast('เปิดโครงการอีกครั้งแล้ว');
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      busy = false;
    }
  }

  async function newVersion(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = '';
    if (!file) return;
    busy = true;
    toast('กำลังอัปโหลดฉบับใหม่…', 'ok', 2000);
    const { status, data } = await uploadFile(`/documents/${id}/versions`, file);
    busy = false;
    if (status === 201) {
      toast('อัปโหลดฉบับใหม่แล้ว ระบบกำลังอ่านเอกสาร');
      bumpReviewCount();
      load();
    } else {
      toast(status === 409 ? 'ไฟล์นี้มีอยู่ในระบบแล้ว' : thai(data?.detail) || 'อัปโหลดไม่สำเร็จ', 'bad');
    }
  }
</script>

{#if error}
  <div class="notice bad">{error}</div>
  <a href="/documents">← กลับไปหน้าเอกสาร</a>
{:else if !doc}
  <div class="card pad stack"><div class="skel" style="width:30%"></div><div class="skel" style="width:80%;height:22px"></div><div class="skel" style="width:60%"></div></div>
{:else}
  <div class="detail">
    <div class="crumbs"><a href="/documents" onclick={(e) => history.length > 1 && (e.preventDefault(), history.back())}><Icon name="back" size={16} />เอกสารทั้งหมด</a></div>

    <header class="head">
      <span class="ftile lg f-{doc.funding_type || 'unset'}" aria-hidden="true">
        <small>ปีงบ</small>{doc.fiscal_year_be ? String(doc.fiscal_year_be).slice(2) : '–'}
      </span>
      <div class="titles">
        <div class="badges">
          <span class="badge {doc.status}">{STATUS[doc.status]}</span>
          {#if doc.closed_at}<span class="badge closed"><Icon name="check-only" size={13} stroke={2.4} />ปิดโครงการแล้ว</span>{/if}
        </div>
        <h1>{doc.title}</h1>
        {#if doc.title_en}<p class="muted en">{doc.title_en}</p>{/if}
      </div>
      <div class="actions">
        <a class="btn" href={fileUrl(doc.id)}><Icon name="download" size={18} />ดาวน์โหลด</a>
        <a class="btn ghost" href={fileUrl(doc.id, { inline: true })} target="_blank" rel="noopener"><Icon name="eye" size={18} />เปิดดู</a>
        <button class="btn ghost" onclick={() => (sharing = true)}><Icon name="link" size={18} />แชร์ลิงก์</button>
        {#if doc.can_edit}
          <a class="btn ghost" href="/documents/{doc.id}/review"><Icon name="edit" size={18} />{doc.status === 'ready' ? 'แก้ไขข้อมูล' : 'ตรวจสอบข้อมูล'}</a>
        {/if}
      </div>
    </header>

    {#if doc.status === 'processing'}
      <div class="notice info"><span class="spin"></span>ระบบกำลังอ่านเอกสารและเติมข้อมูลให้อัตโนมัติ หน้านี้จะอัปเดตเอง</div>
    {:else if doc.status !== 'ready' && doc.can_edit}
      <div class="notice warn"><Icon name="warn" size={18} /><span>เอกสารนี้ยังไม่ได้ตรวจสอบข้อมูล <a href="/documents/{doc.id}/review">ตรวจสอบตอนนี้</a></span></div>
    {/if}

    <div class="grid">
      <section class="card pad">
        <h3>ข้อมูลเอกสาร</h3>
        <dl class="facts">
          {#each facts as [label, value, cls] (label)}
            <dt>{label}</dt>
            <dd class={value ? cls : 'muted'}>{value || '–'}</dd>
          {/each}
        </dl>
      </section>

      <section class="card pad">
        <h3>ผู้เกี่ยวข้อง</h3>
        {#if doc.people.length}
          <ul class="people">
            {#each doc.people as p (p.id + p.role)}
              <li>
                <span><a href="/people/{p.id}">{personName(p)}</a>{#if p.name_en && p.name_th}<small class="muted"> · {p.name_en}</small>{/if}</span>
                <small class="muted">{ROLE[p.role]}{p.share_pct ? ` · ${Number(p.share_pct)}%` : ''}{p.unit ? ` · ${p.unit}` : ''}</small>
              </li>
            {/each}
          </ul>
        {:else}<p class="muted">ยังไม่ได้ระบุ</p>{/if}
      </section>

      <section class="card pad">
        <h3>หมวดหมู่และแท็ก</h3>
        {#if doc.categories.length || doc.tags.length}
          <dl class="facts">
            {#each byGroup(doc.categories) as [key, cats] (key)}
              <dt>{groupNames[key] || key}</dt>
              <dd>{cats.map((c) => c.name_th).join(', ')}</dd>
            {/each}
            {#if doc.tags.length}
              <dt>แท็ก</dt>
              <dd class="tags">{#each doc.tags as t (t.name)}<span class="chip">{t.name}</span>{/each}</dd>
            {/if}
          </dl>
        {:else}<p class="muted">ยังไม่ได้ระบุ</p>{/if}
      </section>

      {#if doc.budget_lines.length}
        <section class="card pad wide">
          <h3>รายการงบประมาณ</h3>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th>ประเภท</th><th>รายการ</th><th class="r">จำนวนเงิน</th><th>กำหนด</th></tr></thead>
              <tbody>
                {#each doc.budget_lines as b, i (i)}
                  <tr>
                    <td>{b.line_type === 'installment' ? 'งวดเงิน' : 'รายการ'}</td>
                    <td>{b.group_label ? `${b.group_label} · ` : ''}{b.label}{b.condition ? ` (${b.condition})` : ''}</td>
                    <td class="r num">{money(b.amount)}{b.percent ? ` (${Number(b.percent)}%)` : ''}</td>
                    <td>{b.due_date ? thDate(b.due_date) : '–'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </section>
      {/if}

      <section class="card pad wide closure" class:done={doc.closed_at}>
        <div class="row">
          <h3>การปิดโครงการ</h3>
          <span class="spacer"></span>
          {#if doc.can_edit}
            {#if doc.closed_at}
              <button class="btn small ghost" onclick={openClose}><Icon name="edit" size={15} />แก้ไข</button>
              <button class="btn small ghost" onclick={reopen} disabled={busy}>เปิดโครงการอีกครั้ง</button>
            {:else}
              <label class="btn small ghost">
                <Icon name="upload" size={15} />แนบเอกสารปิดโครงการ
                <input class="sr-only" type="file" accept="application/pdf,.pdf" multiple onchange={addPaper} disabled={busy} />
              </label>
              <button class="btn small" onclick={openClose}>ปิดโครงการ</button>
            {/if}
          {/if}
        </div>
        {#if doc.closed_at}
          <dl class="facts">
            <dt>วันที่อนุมัติปิด</dt><dd class={doc.closed_on ? '' : 'muted'}>{doc.closed_on ? thDate(doc.closed_on) : 'ไม่ระบุ'}</dd>
            <dt>เลขที่อ้างอิง</dt><dd class={doc.closure_ref ? '' : 'muted'}>{doc.closure_ref || '–'}</dd>
            {#if doc.closure_note}<dt>หมายเหตุ</dt><dd>{doc.closure_note}</dd>{/if}
            <dt>บันทึกในระบบ</dt><dd class="muted">{doc.closed_by_name || '–'} · {thDateTime(doc.closed_at)}</dd>
          </dl>
        {:else}
          <p class="muted">โครงการยังดำเนินการอยู่ เมื่อได้รับอนุมัติปิดโครงการ ให้แนบบันทึกขอปิดโครงการหรือมติที่ประชุม แล้วกด “ปิดโครงการ” เอกสารจะย้ายไปอยู่ในคลังโครงการที่ปิดแล้ว</p>
        {/if}
        {#if doc.closure_files.length}
          <ul class="papers">
            {#each doc.closure_files as f (f.version_no)}
              <li>
                <div class="pinfo">
                  <span class="fname">{f.original_filename}</span>
                  <small class="muted">{PAPER[f.paper] || 'เอกสารปิดโครงการ'} · {f.page_count ? `${f.page_count} หน้า · ` : ''}{bytes(f.size_bytes)} · {thDateTime(f.created_at)}</small>
                  {#if f.ocr_status === 'pending' || f.ocr_status === 'running'}
                    <small class="muted"><span class="spin"></span> ระบบกำลังอ่านเอกสาร</small>
                  {:else if Object.keys(f.readings).length}
                    <small class="read">
                      ระบบอ่านได้:
                      {[
                        f.readings.memo_no && `ที่ ${f.readings.memo_no}`,
                        f.readings.meeting_no && `ครั้งที่ ${f.readings.meeting_no}${f.readings.agenda ? ` วาระ ${f.readings.agenda}` : ''}`,
                        (f.readings.meeting_date || f.readings.memo_date) && `วันที่ ${thDate(f.readings.meeting_date || f.readings.memo_date)}`,
                        f.readings.owner,
                      ].filter(Boolean).join(' · ') || 'ไม่พบวันที่หรือเลขที่'}
                    </small>
                  {/if}
                  {#if f.title_match !== null && f.title_match < 70}
                    <small class="mismatch"><Icon name="warn" size={13} />ชื่อโครงการในเอกสารนี้ไม่ตรงกับสัญญา อาจแนบผิดไฟล์: “{f.readings.title}”</small>
                  {/if}
                </div>
                <a class="link-btn" href={fileUrl(doc.id, { closure: f.version_no, inline: true })} target="_blank" rel="noopener">เปิดดู</a>
                <a class="link-btn" href={fileUrl(doc.id, { closure: f.version_no })}>ดาวน์โหลด</a>
              </li>
            {/each}
          </ul>
          {#if doc.closed_at && doc.can_edit}
            <label class="link-btn add-paper">
              + แนบเอกสารเพิ่ม
              <input class="sr-only" type="file" accept="application/pdf,.pdf" multiple onchange={addPaper} disabled={busy} />
            </label>
          {/if}
        {/if}
      </section>

      <section class="card pad wide">
        <div class="row">
          <h3>ไฟล์และฉบับแก้ไข</h3>
          <span class="spacer"></span>
          {#if doc.can_edit}
            <label class="btn small ghost">
              <Icon name="upload" size={15} />อัปโหลดฉบับใหม่
              <input bind:this={versionInput} class="sr-only" type="file" accept="application/pdf,.pdf" onchange={newVersion} disabled={busy} />
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
  {#if closing}
    <Modal title={doc.closed_at ? 'แก้ไขข้อมูลการปิดโครงการ' : 'ปิดโครงการ'} onclose={() => !closeBusy && (closing = null)} width={520}>
      <div class="stack">
        {#if !doc.closed_at}
          <p class="muted">โครงการที่ปิดแล้วจะย้ายไปอยู่ใน “คลังโครงการที่ปิดแล้ว” ยังค้นหาและเปิดดูได้ตามปกติ และเปิดโครงการอีกครั้งได้ภายหลัง</p>
        {/if}
        <div class="field">
          <span>เอกสารปิดโครงการ (PDF)</span>
          <label class="drop">
            <Icon name="upload" size={18} />
            <span>เลือกไฟล์บันทึกขออนุมัติปิดโครงการ / มติที่ประชุม</span>
            <input class="sr-only" type="file" accept="application/pdf,.pdf" multiple onchange={pickPapers} disabled={closeBusy} />
          </label>
          {#each closing.files as f, i (f.name + i)}
            <div class="picked"><span class="fname">{f.name}</span><small class="muted">{bytes(f.size)}</small><button type="button" class="icon-btn" onclick={() => closing.files.splice(i, 1)} aria-label="เอา {f.name} ออก"><Icon name="x" size={15} /></button></div>
          {/each}
          {#if doc.closure_files.length}<small>แนบไว้แล้ว {doc.closure_files.length} ไฟล์</small>{/if}
        </div>
        <label class="field">
          <span>วันที่อนุมัติปิดโครงการ</span>
          <input id="c-date" bind:value={closing.date} placeholder="วว/ดด/ปปปป (พ.ศ.)" inputmode="numeric" />
          {#if parseThaiDate(closing.date)}<small>{thDate(parseThaiDate(closing.date))}</small>{/if}
          {#if reading.date && toThaiInput(reading.date) !== closing.date}
            <button type="button" class="sugg" onclick={() => (closing.date = toThaiInput(reading.date))}>ระบบอ่านได้: {thDate(reading.date)}</button>
          {/if}
        </label>
        <label class="field">
          <span>เลขที่บันทึก / มติที่ประชุม</span>
          <input id="c-ref" bind:value={closing.ref} placeholder="เช่น อว 0000.00/123 หรือ มติที่ประชุม ครั้งที่ 9/2568" />
          {#if reading.ref && reading.ref !== closing.ref}
            <button type="button" class="sugg" onclick={() => (closing.ref = reading.ref)}>ระบบอ่านได้: {reading.ref}</button>
          {/if}
        </label>
        <label class="field"><span>หมายเหตุ</span><textarea id="c-note" rows="2" bind:value={closing.note}></textarea></label>
        {#if papersReading}<small class="muted">ระบบกำลังอ่านเอกสารที่แนบไว้ ค่าที่อ่านได้จะขึ้นในหน้าเอกสารเมื่อเสร็จ</small>{/if}
        {#if closeError}<div class="notice bad">{closeError}</div>{/if}
      </div>
      {#snippet footer()}
        <button class="btn ghost" onclick={() => (closing = null)} disabled={closeBusy}>ยกเลิก</button>
        <button class="btn" onclick={saveClose} disabled={closeBusy}>{closeBusy ? 'กำลังบันทึก…' : doc.closed_at ? 'บันทึก' : 'ปิดโครงการ'}</button>
      {/snippet}
    </Modal>
  {/if}
  {#if confirmDelete}
    <Modal title="ย้ายเอกสารไปถังขยะ?" onclose={() => (confirmDelete = false)}>
      <p>“{doc.title}” จะหายไปจากการค้นหา และลิงก์แชร์ทั้งหมดของเอกสารนี้จะใช้ไม่ได้ทันที กู้คืนได้จาก “ถังขยะของฉัน” ในเมนูบัญชี</p>
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
  .head > .ftile { flex: none; }
  .titles h1 { font-size: 23px; line-height: 1.4; overflow-wrap: anywhere; }
  .en { font-size: 14.5px; overflow-wrap: anywhere; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
  .grid .wide { grid-column: 1 / -1; }
  section h3 { margin-bottom: 10px; }
  .facts { display: grid; grid-template-columns: auto 1fr; gap: 6px 16px; margin: 0; font-size: 14px; }
  .facts dt { color: var(--muted); white-space: nowrap; }
  .facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .people { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
  .people li { display: flex; flex-direction: column; }
  .people small { font-size: 12.5px; }
  .versions { list-style: none; margin: 0; padding: 0; }
  .versions li { display: grid; grid-template-columns: 120px minmax(0, 1fr) auto auto; gap: 12px; align-items: baseline; padding: 8px 0; border-top: 1px solid var(--border); font-size: 14px; }
  .versions li:first-child { border-top: 0; }
  .vno { font-weight: 600; }
  .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .r { text-align: right; }
  .danger { display: flex; justify-content: flex-end; }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; }
  .badge.closed::before { display: none; }
  .closure { display: flex; flex-direction: column; gap: 10px; }
  .closure h3 { margin-bottom: 0; }
  .closure > p { font-size: 14px; margin: 0; }
  .papers { list-style: none; margin: 0; padding: 0; }
  .papers li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px 12px; align-items: baseline; padding: 8px 0; border-top: 1px solid var(--border); font-size: 14px; }
  .pinfo { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .pinfo small { font-size: 12.5px; }
  .read { color: var(--muted); overflow-wrap: anywhere; }
  .mismatch { display: inline-flex; gap: 4px; align-items: flex-start; color: var(--warn); overflow-wrap: anywhere; }
  .add-paper { align-self: flex-start; cursor: pointer; }
  .drop { display: flex; gap: 8px; align-items: center; padding: 12px; border: 1px dashed var(--border-strong); border-radius: 10px; cursor: pointer; font-size: 14px; color: var(--muted); }
  .drop:hover { background: var(--subtle); }
  .picked { display: grid; grid-template-columns: minmax(0, 1fr) auto 32px; gap: 8px; align-items: center; font-size: 14px; }
  .sugg { align-self: flex-start; border: 1px dashed var(--accent); background: var(--accent-soft); color: var(--accent-text); border-radius: 8px; padding: 1px 8px; font-size: 12.5px; text-align: left; }
  @media (max-width: 640px) {
    .head { flex-wrap: wrap; }
    .titles { flex: 1 1 0; }
    .titles h1 { font-size: 19px; }
    .actions { width: 100%; }
    .actions > :first-child { flex: 1 1 100%; min-height: 46px; }
    .actions > :not(:first-child) { flex: 1; }
    .versions li { grid-template-columns: 1fr auto; }
    .versions .fname, .versions small { grid-column: 1; }
    .papers li { grid-template-columns: 1fr auto; }
    .papers .pinfo { grid-column: 1 / -1; }
  }
</style>
