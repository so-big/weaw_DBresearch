<script>
  import { onDestroy } from 'svelte';
  import { get, del, uploadFile, errorText, fileUrl, thai } from '../lib/api.js';
  import { navigate } from '../lib/router.svelte.js';
  import { toast, screen, bumpReviewCount } from '../lib/state.svelte.js';
  import { STATUS, KIND, FUNDING, ROLE, thDate, thDateTime, money, bytes, personName } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';
  import Modal from '../components/Modal.svelte';
  import ShareDialog from '../components/ShareDialog.svelte';

  let { id } = $props();
  let doc = $state(null);
  let error = $state('');
  let sharing = $state(false);
  let confirmDelete = $state(false);
  let busy = $state(false);
  let versionInput = $state();
  let timer;

  async function load() {
    clearTimeout(timer);
    try {
      doc = await get(`/documents/${id}`);
      error = '';
      // While the scan is being read, check back every few seconds.
      if (doc.status === 'processing') timer = setTimeout(load, 4000);
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
      await del(`/documents/${id}`);
      bumpReviewCount();
      toast('ย้ายเอกสารไปถังขยะแล้ว');
      navigate('/documents');
    } catch (err) {
      toast(errorText(err), 'bad');
    } finally {
      busy = false;
      confirmDelete = false;
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
      <div class="titles">
        <span class="badge {doc.status}">{STATUS[doc.status]}</span>
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
                <span>{personName(p)}{#if p.name_en && p.name_th}<small class="muted"> · {p.name_en}</small>{/if}</span>
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

    {#if doc.can_edit}
      <div class="danger">
        <button class="btn ghost small" onclick={() => (confirmDelete = true)}><Icon name="trash" size={15} />ย้ายไปถังขยะ</button>
      </div>
    {/if}
  </div>

  {#if sharing}<ShareDialog {doc} onclose={() => (sharing = false)} />{/if}
  {#if confirmDelete}
    <Modal title="ย้ายเอกสารไปถังขยะ?" onclose={() => (confirmDelete = false)}>
      <p>“{doc.title}” จะหายไปจากการค้นหา และลิงก์แชร์ทั้งหมดของเอกสารนี้จะใช้ไม่ได้ทันที ผู้ดูแลระบบกู้คืนได้จากถังขยะ</p>
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
  .titles { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; min-width: 0; flex: 1 1 420px; }
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
  @media (max-width: 640px) {
    .titles h1 { font-size: 19px; }
    .actions { width: 100%; }
    .actions > :first-child { flex: 1 1 100%; min-height: 46px; }
    .actions > :not(:first-child) { flex: 1; }
    .versions li { grid-template-columns: 1fr auto; }
    .versions .fname, .versions small { grid-column: 1; }
  }
</style>
