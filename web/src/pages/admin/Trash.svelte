<script>
  // Restore, or purge for good (deletes the encrypted file and its key; backups keep a copy).
  import { get, post, del, errorText } from '../../lib/api.js';
  import { toast } from '../../lib/state.svelte.js';
  import { thDate } from '../../lib/format.js';
  import Modal from '../../components/Modal.svelte';

  let items = $state(null);
  let error = $state('');
  let purging = $state(null);
  let confirmText = $state('');

  async function load() {
    try {
      items = await get('/admin/trash');
    } catch (err) {
      error = errorText(err);
    }
  }
  load();

  async function restore(d) {
    try {
      await post(`/admin/trash/${d.id}/restore`);
      toast('กู้คืนเอกสารแล้ว (ลิงก์แชร์เดิมยังใช้ไม่ได้)');
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function purge() {
    try {
      await del(`/admin/trash/${purging.id}`);
      toast('ลบถาวรแล้ว');
      purging = null;
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  const purgeWord = $derived(purging?.reference_no || 'ลบ');
</script>

<div class="stack">
  <h1>ถังขยะ</h1>
  <p class="hint">เอกสารที่ถูกลบจะอยู่ที่นี่จนกว่าผู้ดูแลระบบจะลบถาวร การกู้คืนไม่ได้เปิดลิงก์แชร์เดิมกลับมา</p>
  {#if error}<div class="notice bad">{error}</div>{/if}
  {#if items === null}
    <div class="card pad"><div class="skel" style="width:50%"></div></div>
  {:else if !items.length}
    <div class="card pad muted">ถังขยะว่าง</div>
  {:else}
    <div class="card list">
      {#each items as d (d.id)}
        <div class="item">
          <div class="grow">
            <b>{d.title}</b>
            <div class="muted meta">{#if d.reference_no}<span class="cno">{d.reference_no}</span> · {/if}ลบเมื่อ {thDate(d.deleted_at)}{#if d.deleted_by_name} โดย {d.deleted_by_name}{/if}</div>
          </div>
          <button class="btn small ghost" onclick={() => restore(d)}>กู้คืน</button>
          <button class="btn small danger" onclick={() => ((confirmText = ''), (purging = d))}>ลบถาวร</button>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if purging}
  <Modal title="ลบถาวร?" onclose={() => (purging = null)}>
    <div class="notice bad">ไฟล์และกุญแจเข้ารหัสของ “{purging.title}” จะถูกลบออกจากระบบ ย้อนกลับไม่ได้ (สำเนาในข้อมูลสำรองยังอยู่)</div>
    <label class="field">
      <span>พิมพ์ <b class="mono">{purgeWord}</b> เพื่อยืนยัน</span>
      <input id="purge-confirm" bind:value={confirmText} autocomplete="off" />
    </label>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (purging = null)}>ยกเลิก</button>
      <button class="btn danger" onclick={purge} disabled={confirmText.trim() !== purgeWord}>ลบถาวร</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .list { overflow: hidden; }
  .item { display: flex; gap: 10px; align-items: center; padding: 12px 16px; border-top: 1px solid var(--border); flex-wrap: wrap; }
  .item:first-child { border-top: 0; }
  .grow { flex: 1 1 260px; min-width: 0; overflow-wrap: anywhere; }
  .meta { font-size: 13px; }
</style>
