<script>
  import { get, post, errorText } from '../../lib/api.js';
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
    'auth.login_blocked': 'ถูกระงับชั่วคราว', 'auth.logout_all': 'ออกจากระบบทุกอุปกรณ์',
    'auth.provider_error': 'ระบบมหาวิทยาลัยไม่ตอบ', 'auth.login_unlocked': 'ปลดล็อกการเข้าสู่ระบบ',
    'user.create': 'เพิ่มผู้ใช้', 'user.update': 'แก้ไขผู้ใช้', 'user.password_reset': 'ตั้งรหัสผ่านใหม่',
    'user.sessions_revoked': 'ให้ออกจากระบบทุกอุปกรณ์',
    'category.create': 'เพิ่มหมวดหมู่', 'category.update': 'แก้ไขหมวดหมู่', 'category.delete': 'ลบหมวดหมู่',
    'category_group.create': 'เพิ่มกลุ่มหมวดหมู่', 'category_group.update': 'แก้ไขกลุ่มหมวดหมู่',
    'template.update': 'แก้ไขเทมเพลต', 'settings.update': 'แก้ไขการตั้งค่า',
  };

  // Why a login failed (audit `reason`), in words.
  const REASON = {
    wrong_password: 'รหัสผ่านผิด', unknown_user: 'ไม่พบบัญชี', disabled: 'บัญชีถูกปิดใช้งาน',
    not_registered: 'ยังไม่ได้เพิ่มในระบบ', username: 'บัญชีนี้ผิดหลายครั้ง', ip: 'IP นี้ผิดหลายครั้ง',
  };
  const reason = (v) => REASON[v] || (String(v).startsWith('type_not_allowed:') ? `ประเภทบัญชีไม่ได้รับอนุญาต (${v.split(':')[1]})` : v);

  let security = $state(null);
  const loadSecurity = () => get('/admin/security').then((r) => (security = r)).catch(() => {});
  loadSecurity();

  // Clear a brute-force lock (testers lock themselves out); written to the audit log.
  async function unlock(kind, key) {
    try {
      await post('/admin/security/unlock', { kind, key });
      await loadSecurity();
      load();
    } catch (err) {
      error = errorText(err);
    }
  }

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
    const skip = new Set(['version', 'user_agent']);
    return Object.entries(d || {})
      .filter(([k]) => !skip.has(k))
      .map(([k, v]) => (k === 'reason' || k === 'locked' ? reason(v) : `${k}: ${Array.isArray(v) ? v.join(', ') : v}`))
      .join(' · ');
  }
</script>

<div class="stack">
  <h1>บันทึกการใช้งาน</h1>
  {#if security}
    {#each security.warnings as w (w)}<div class="notice bad">ตั้งค่าเซิร์ฟเวอร์ไม่ปลอดภัย: {w}</div>{/each}
    <section class="card pad sec">
      <div class="row"><b>การเข้าสู่ระบบ 24 ชั่วโมงล่าสุด</b></div>
      <div class="stats">
        <div><span class="num big">{security.logins}</span><small class="muted">สำเร็จ</small></div>
        <div class:warn={security.failed}><span class="num big">{security.failed}</span><small class="muted">ไม่สำเร็จ</small></div>
        <div class:warn={security.blocked}><span class="num big">{security.blocked}</span><small class="muted">ถูกระงับ</small></div>
        {#if security.provider_errors}<div class="warn"><span class="num big">{security.provider_errors}</span><small class="muted">ระบบมหาวิทยาลัยไม่ตอบ</small></div>{/if}
      </div>
      {#if security.by_username.length || security.by_ip.length}
        <div class="tops">
          {#each [['บัญชีที่ผิดบ่อย', security.by_username, false], ['IP ที่ผิดบ่อย', security.by_ip, true]] as [title, list, mono] (title)}
            {#if list.length}
              <div>
                <span class="label">{title}</span>
                <ul>
                  {#each list as x (x.key)}
                    <li><span class:mono>{x.key}</span> <small class="muted">{x.failures} ครั้ง</small>{#if x.locked} <span class="badge failed">ระงับอยู่</span> <button class="btn small ghost" onclick={() => unlock(mono ? 'ip' : 'username', x.key)}>ปลดล็อก</button>{/if}</li>
                  {/each}
                </ul>
              </div>
            {/if}
          {/each}
        </div>
      {/if}
    </section>
  {/if}
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
  .sec { display: flex; flex-direction: column; gap: 12px; }
  .stats { display: flex; gap: 24px; flex-wrap: wrap; }
  .stats > div { display: flex; flex-direction: column; }
  .big { font-size: 22px; font-weight: 600; }
  .warn .big { color: var(--bad); }
  .tops { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .tops ul { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
  .tops li { overflow-wrap: anywhere; }
</style>
