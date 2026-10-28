<script>
  // Share links I created (admins see everyone's under ผู้ดูแลระบบ → ลิงก์แชร์ทั้งหมด).
  import { get } from '../lib/api.js';
  import { errorText } from '../lib/api.js';
  import ShareList from '../components/ShareList.svelte';

  let activeOnly = $state(true);
  let links = $state(null);
  let error = $state('');

  async function load() {
    try {
      links = await get('/shares', { active_only: activeOnly || undefined });
      error = '';
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    activeOnly;
    load();
  });
</script>

<div class="page">
  <div class="head">
    <div>
      <h1>ลิงก์แชร์ของฉัน</h1>
      <p class="muted">สร้างลิงก์ใหม่ได้จากหน้าเอกสาร ลิงก์จะแสดงครั้งเดียวตอนสร้าง หากทำหายให้สร้างลิงก์ใหม่</p>
    </div>
    <div class="seg">
      <button aria-pressed={activeOnly} onclick={() => (activeOnly = true)}>ใช้งานอยู่</button>
      <button aria-pressed={!activeOnly} onclick={() => (activeOnly = false)}>ทั้งหมด</button>
    </div>
  </div>
  {#if error}<div class="notice bad">{error}</div>{/if}
  <ShareList {links} onchange={load} />
</div>

<style>
  .page { max-width: 960px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
  .head p { font-size: 14px; max-width: 60ch; }
</style>
