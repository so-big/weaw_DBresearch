<script>
  // My bin: documents I uploaded or deleted that sit in the trash. I can take back what I
  // deleted myself; what an admin removed stays with the admin. Only admins purge.
  import { get, errorText } from '../lib/api.js';
  import { restoreDocs } from '../lib/trash.js';
  import { isAdmin } from '../lib/state.svelte.js';
  import { thDate, FUNDING } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';

  let items = $state(null);
  let error = $state('');
  let busy = $state(null); // id being restored, or 'all'

  async function load() {
    try {
      items = await get('/documents/trash');
      error = '';
    } catch (err) {
      error = errorText(err);
    }
  }
  load();

  const restorable = $derived((items || []).filter((d) => d.can_restore));

  async function restore(ids, key) {
    busy = key;
    await restoreDocs(ids, load);
    busy = null;
  }
</script>

<div class="bin">
  <div class="head">
    <div>
      <h1>ถังขยะของฉัน</h1>
      <p class="muted">เอกสารที่คุณอัปโหลดหรือลบ จะอยู่ที่นี่จนกว่าผู้ดูแลระบบจะลบถาวร กู้คืนแล้วลิงก์แชร์เดิมยังใช้ไม่ได้ ต้องสร้างใหม่</p>
    </div>
    {#if restorable.length > 1}
      <button class="btn ghost" onclick={() => restore(restorable.map((d) => d.id), 'all')} disabled={busy !== null}>
        <Icon name="undo" size={17} />กู้คืนทั้งหมด ({restorable.length})
      </button>
    {/if}
  </div>
  {#if isAdmin()}<div class="notice info"><span>ผู้ดูแลระบบดูและลบถาวรเอกสารของทุกคนได้ที่ <a href="/admin/trash">ผู้ดูแลระบบ › ถังขยะ</a></span></div>{/if}
  {#if error}<div class="notice bad">{error} <button class="link-btn" onclick={load}>ลองใหม่</button></div>{/if}

  {#if items === null && !error}
    <div class="card list">
      {#each Array(3) as _, i (i)}<div class="item"><div class="grow"><div class="skel" style="width:60%;height:14px"></div><div class="skel" style="width:35%;margin-top:8px"></div></div></div>{/each}
    </div>
  {:else if items && !items.length}
    <div class="card empty">
      <Icon name="trash" size={30} />
      <p>ถังขยะว่าง</p>
      <span class="muted">เอกสารที่ลบจะมาอยู่ที่นี่ก่อน กู้คืนได้ตลอดจนกว่าผู้ดูแลระบบจะลบถาวร</span>
    </div>
  {:else if items}
    <div class="card list">
      {#each items as d (d.id)}
        <div class="item">
          <div class="grow">
            <div class="topline">
              {#if d.reference_no}<span class="cno">{d.reference_no}</span>{/if}
              {#if d.funding_type}<span class="muted">{FUNDING[d.funding_type]}</span>{/if}
            </div>
            <b class="t">{d.title}</b>
            <div class="muted meta">
              ลบเมื่อ {thDate(d.deleted_at)}{#if d.deleted_by_name} โดย {d.deleted_by_name}{/if}
            </div>
          </div>
          {#if d.can_restore}
            <button class="btn small ghost" onclick={() => restore([d.id], d.id)} disabled={busy !== null}>
              {#if busy === d.id}<span class="spin"></span>{:else}<Icon name="undo" size={15} />{/if}กู้คืน
            </button>
          {:else}
            <span class="muted note">ผู้ดูแลระบบลบ ติดต่อผู้ดูแลระบบเพื่อกู้คืน</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .bin { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .head { display: flex; gap: 12px; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; }
  .head h1 { font-size: 24px; }
  .head p { font-size: 13.5px; margin-top: 4px; max-width: 560px; }
  .list { overflow: hidden; }
  .item { display: flex; gap: 12px; align-items: center; padding: 13px 16px; border-top: 1px solid var(--border); flex-wrap: wrap; }
  .item:first-child { border-top: 0; }
  .grow { flex: 1 1 260px; min-width: 0; }
  .topline { display: flex; gap: 10px; align-items: baseline; font-size: 12px; }
  .t { display: block; font-weight: 500; font-size: 15px; line-height: 1.45; overflow-wrap: anywhere; }
  .meta { font-size: 12.5px; margin-top: 2px; }
  .note { font-size: 12.5px; max-width: 200px; }
  .empty { padding: 40px 16px; display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; color: var(--muted); }
  .empty p { color: var(--text); }
  .empty span { font-size: 13px; }
</style>
