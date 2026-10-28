<script>
  // Documents waiting for a person to confirm the auto-filled details.
  import { onDestroy } from 'svelte';
  import { get, errorText } from '../lib/api.js';
  import { isAdmin, review } from '../lib/state.svelte.js';
  import { openUpload } from '../lib/uploads.svelte.js';
  import { STATUS, thDate } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';

  let mineOnly = $state(!isAdmin());
  let items = $state(null);
  let error = $state('');
  let timer;

  async function load() {
    clearTimeout(timer);
    try {
      const res = await get('/documents', {
        status: ['processing', 'needs_review', 'failed'],
        mine: mineOnly || undefined,
        sort: 'oldest',
        page_size: 100,
      });
      items = res.items;
      // The tab badge counts the same scope: own documents for users, all for admins.
      if (isAdmin() !== mineOnly) review.count = res.items.filter((d) => d.status !== 'processing').length;
      error = '';
      // Files still being read: check again shortly so rows flip to "รอตรวจสอบ" by themselves.
      if (items.some((d) => d.status === 'processing')) timer = setTimeout(load, 5000);
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    mineOnly;
    load();
  });
  onDestroy(() => clearTimeout(timer));

  const ready = $derived((items || []).filter((d) => d.status !== 'processing'));
  const reading = $derived((items || []).filter((d) => d.status === 'processing'));
</script>

<div class="page">
  <div class="head">
    <div>
      <h1>รอตรวจสอบ</h1>
      <p class="muted">เอกสารที่ระบบอ่านแล้ว รอให้คุณยืนยันข้อมูล ทำเมื่อไหร่ก็ได้ ระหว่างนี้เอกสารค้นหาและเปิดดูได้ตามปกติ</p>
    </div>
    {#if isAdmin()}
      <div class="seg">
        <button aria-pressed={mineOnly} onclick={() => (mineOnly = true)}>ของฉัน</button>
        <button aria-pressed={!mineOnly} onclick={() => (mineOnly = false)}>ทั้งหมด</button>
      </div>
    {/if}
  </div>

  {#if error}<div class="notice bad">{error}</div>{/if}

  {#if items === null}
    <div class="card list">{#each Array(3) as _, i (i)}<div class="item"><div class="skel" style="width:70%;height:14px"></div></div>{/each}</div>
  {:else if !items.length}
    <div class="card empty">
      <Icon name="check" size={32} />
      <p>ไม่มีเอกสารค้างตรวจ</p>
      <button class="btn ghost" onclick={openUpload}><Icon name="upload" size={17} />อัปโหลดเอกสาร</button>
    </div>
  {:else}
    {#if ready.length}
      <div class="card list">
        {#each ready as d (d.id)}
          <div class="item enter">
            <div class="grow">
              <a class="t" href="/documents/{d.id}">{d.title}</a>
              <div class="meta">
                {#if d.reference_no}<span class="cno">{d.reference_no}</span>{/if}
                <span>อัปโหลด {thDate(d.updated_at)}</span>
                {#if d.owners?.length}<span>{d.owners.join(', ')}</span>{/if}
              </div>
            </div>
            <span class="badge {d.status}">{STATUS[d.status]}</span>
            <a class="btn small" href="/documents/{d.id}/review">ตรวจสอบ</a>
          </div>
        {/each}
      </div>
    {/if}
    {#if reading.length}
      <h3 class="sub">ระบบกำลังอ่าน ({reading.length})</h3>
      <div class="card list">
        {#each reading as d (d.id)}
          <div class="item">
            <span class="spin"></span>
            <div class="grow"><span class="t plain">{d.title}</span></div>
            <span class="badge processing">{STATUS.processing}</span>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 960px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
  .head p { font-size: 14px; max-width: 60ch; }
  .list { overflow: hidden; }
  .item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-top: 1px solid var(--border); }
  .item:first-child { border-top: 0; }
  .grow { flex: 1; min-width: 0; }
  .t { font-weight: 500; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
  .t:hover { color: var(--primary-text); }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; color: var(--muted); }
  .sub { margin-top: 8px; color: var(--muted); font-size: 15px; }
  .empty { padding: 40px 16px; display: flex; flex-direction: column; align-items: center; gap: 12px; color: var(--muted); }
  .empty p { color: var(--text); }
  @media (max-width: 640px) {
    .item { flex-wrap: wrap; padding: 12px; }
    .item .grow { flex-basis: 100%; }
    .item .btn { margin-left: auto; }
  }
</style>
