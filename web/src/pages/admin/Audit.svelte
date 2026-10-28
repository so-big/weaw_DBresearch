<script>
  import { get, errorText } from '../../lib/api.js';
  import { thDateTime } from '../../lib/format.js';

  const ACTIONS = [
    ['', 'ทั้งหมด'],
    ['document.download', 'ดาวน์โหลด'],
    ['document.view', 'เปิดดู'],
    ['document.', 'เอกสาร'],
    ['share.', 'ลิงก์แชร์'],
    ['auth.', 'เข้าสู่ระบบ'],
    ['user.', 'ผู้ใช้'],
    ['settings.', 'ตั้งค่า'],
  ];
  const LABEL = {
    'document.upload': 'อัปโหลด', 'document.new_version': 'อัปโหลดฉบับใหม่', 'document.download': 'ดาวน์โหลด',
    'document.view': 'เปิดดู', 'document.confirm': 'ยืนยันข้อมูล', 'document.update': 'แก้ไขข้อมูล',
    'document.delete': 'ย้ายไปถังขยะ', 'document.restore': 'กู้คืน', 'document.purge': 'ลบถาวร',
    'document.reprocess': 'สั่งอ่านใหม่',
    'share.create': 'สร้างลิงก์', 'share.revoke': 'ยกเลิกลิงก์', 'share.new_password': 'รหัสลิงก์ใหม่',
    'auth.login': 'เข้าสู่ระบบ', 'auth.logout': 'ออกจากระบบ', 'auth.login_failed': 'เข้าสู่ระบบไม่สำเร็จ',
    'user.create': 'เพิ่มผู้ใช้', 'user.update': 'แก้ไขผู้ใช้', 'user.password_reset': 'ตั้งรหัสผ่านใหม่',
    'category.create': 'เพิ่มหมวดหมู่', 'category.update': 'แก้ไขหมวดหมู่', 'category.delete': 'ลบหมวดหมู่',
    'category_group.create': 'เพิ่มกลุ่มหมวดหมู่', 'category_group.update': 'แก้ไขกลุ่มหมวดหมู่',
    'template.update': 'แก้ไขเทมเพลต', 'settings.update': 'แก้ไขการตั้งค่า',
  };

  let action = $state('');
  let rows = $state(null);
  let more = $state(false);
  let error = $state('');
  const PAGE = 100;

  async function load(append = false) {
    try {
      const before = append && rows?.length ? rows[rows.length - 1].id : undefined;
      const res = await get('/admin/audit', { action: action || undefined, limit: PAGE, before_id: before });
      rows = append ? [...rows, ...res] : res;
      more = res.length === PAGE;
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    action;
    load();
  });

  function details(d) {
    const skip = new Set(['version']);
    return Object.entries(d || {})
      .filter(([k]) => !skip.has(k))
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
      .join(' · ');
  }
</script>

<div class="stack">
  <h1>บันทึกการใช้งาน</h1>
  <div class="chips">
    {#each ACTIONS as [v, l] (v)}<button class="chip" aria-pressed={action === v} onclick={() => (action = v)}>{l}</button>{/each}
  </div>
  {#if error}<div class="notice bad">{error}</div>{/if}
  <div class="card table-wrap">
    <table class="data">
      <thead><tr><th>เวลา</th><th>ผู้ใช้</th><th>การกระทำ</th><th>รายละเอียด</th><th>IP</th></tr></thead>
      <tbody>
        {#if rows === null}
          <tr><td colspan="5"><div class="skel" style="width:50%"></div></td></tr>
        {:else if !rows.length}
          <tr><td colspan="5" class="muted">ไม่มีรายการ</td></tr>
        {:else}
          {#each rows as r (r.id)}
            <tr>
              <td class="num nowrap">{thDateTime(r.at)}</td>
              <td>{r.actor_name || (r.details?.via === 'share' ? 'ผู้มีลิงก์' : '–')}</td>
              <td class="nowrap">{LABEL[r.action] || r.action}</td>
              <td class="det">{#if r.entity_type === 'document' && r.entity_id && !r.action.endsWith('purge')}<a href="/documents/{r.entity_id}">เปิดเอกสาร</a> {/if}<small class="muted">{details(r.details)}</small></td>
              <td class="mono">{r.ip || '–'}</td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
  {#if more}<button class="btn ghost" style="align-self:center" onclick={() => load(true)}>แสดงเพิ่ม</button>{/if}
</div>

<style>
  .chips { display: flex; gap: 6px; flex-wrap: wrap; }
  .nowrap { white-space: nowrap; }
  .det { min-width: 200px; overflow-wrap: anywhere; }
</style>
