<script>
  import { get, put, errorText } from '../../lib/api.js';
  import { toast } from '../../lib/state.svelte.js';

  const ITEMS = [
    ['share.default_ttl_hours', 'อายุลิงก์เริ่มต้น', 'ชั่วโมง'],
    ['share.max_ttl_user_hours', 'อายุลิงก์สูงสุด (ผู้ใช้)', 'ชั่วโมง'],
    ['share.max_ttl_admin_hours', 'อายุลิงก์สูงสุด (ผู้ดูแลระบบ)', 'ชั่วโมง'],
    ['share.max_failed_attempts', 'ล็อกลิงก์เมื่อใส่รหัสผิด', 'ครั้ง'],
  ];
  let values = $state(null);
  let saved = $state({});
  let error = $state('');

  get('/admin/settings')
    .then((v) => {
      values = { ...v };
      saved = { ...v };
    })
    .catch((err) => (error = errorText(err)));

  async function save(key) {
    try {
      await put(`/admin/settings/${encodeURIComponent(key)}`, { value: Number(values[key]) });
      saved[key] = values[key];
      toast('บันทึกแล้ว');
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
</script>

<div class="stack">
  <h1>ตั้งค่า</h1>
  {#if error}<div class="notice bad">{error}</div>{/if}
  <section class="card pad stack">
    <h3>ลิงก์แชร์</h3>
    {#if values}
      {#each ITEMS as [key, label, unit] (key)}
        <div class="setting">
          <label class="field" for="s-{key}"><span>{label}</span></label>
          <div class="row">
            <input id="s-{key}" class="input num" type="number" min="1" bind:value={values[key]} />
            <span class="muted">{unit}{unit === 'ชั่วโมง' && values[key] >= 24 ? ` (${Math.round((values[key] / 24) * 10) / 10} วัน)` : ''}</span>
            {#if String(values[key]) !== String(saved[key])}<button class="btn small" onclick={() => save(key)}>บันทึก</button>{/if}
          </div>
        </div>
      {/each}
    {:else}
      <div class="skel" style="width:50%"></div>
    {/if}
  </section>
  <section class="card pad stack">
    <h3>เทมเพลตการอ่านเอกสาร</h3>
    <p class="hint">กฎการอ่านข้อมูลจากแบบฟอร์มแก้ไขผ่าน API (<span class="mono">PATCH /api/admin/templates/&#123;id&#125;</span>) หรือ migration เท่านั้น เพื่อให้ตรวจสอบก่อนใช้งานได้ ดูได้ที่ <a href="/api/docs" target="_blank" rel="noopener">เอกสาร API</a></p>
  </section>
</div>

<style>
  .setting { display: flex; flex-direction: column; gap: 4px; }
  .setting .input { width: 130px; }
</style>
