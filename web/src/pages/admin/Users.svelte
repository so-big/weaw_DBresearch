<script>
  // Accounts and roles. Local username/password is for the demo; SSO users need neither.
  import { get, post, patch, errorText } from '../../lib/api.js';
  import { toast, session, access } from '../../lib/state.svelte.js';
  import { thDateTime } from '../../lib/format.js';
  import Modal from '../../components/Modal.svelte';
  import Icon from '../../components/Icon.svelte';

  let users = $state(null);
  let requests = $state([]);
  let rejecting = $state(null);
  let error = $state('');
  let creating = $state(null);
  let resetting = $state(null);
  let formError = $state('');

  async function load() {
    try {
      [users, requests] = await Promise.all([get('/admin/users'), get('/admin/users/requests')]);
      access.requests = requests.length;
    } catch (err) {
      error = errorText(err);
    }
  }
  load();

  function newUser() {
    formError = '';
    creating = { email: '', display_name: '', role: 'user', university_id: '', username: '', password: '' };
  }
  async function create() {
    formError = '';
    const c = creating;
    try {
      await post('/admin/users', {
        email: c.email.trim(),
        display_name: c.display_name.trim(),
        role: c.role,
        university_id: c.university_id.trim() || null,
        username: c.username.trim() || null,
        password: c.username.trim() ? c.password : null,
      });
      toast('เพิ่มผู้ใช้แล้ว');
      creating = null;
      load();
    } catch (err) {
      formError = err.status === 409 ? 'อีเมล ชื่อผู้ใช้ หรือรหัสมหาวิทยาลัยนี้มีอยู่แล้ว' : errorText(err);
    }
  }
  async function change(u, body, msg) {
    try {
      await patch(`/admin/users/${u.id}`, body);
      toast(msg);
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function decide(r, action) {
    try {
      await post(`/admin/users/${r.id}/${action}`);
      toast(action === 'approve' ? `อนุมัติ ${r.display_name} แล้ว` : 'ปฏิเสธคำขอแล้ว');
    } catch (err) {
      toast(err.status === 409 ? 'คำขอนี้ได้รับการพิจารณาไปแล้ว' : errorText(err), 'bad');
    }
    rejecting = null;
    load();
  }
  async function endSessions(u) {
    try {
      await post(`/admin/users/${u.id}/sessions/revoke`);
      toast('ออกจากระบบทุกอุปกรณ์แล้ว');
      sessions = null;
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  let sessions = $state(null);
  async function showSessions(u) {
    try {
      sessions = { user: u, rows: await get(`/admin/users/${u.id}/sessions`) };
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  const LOGIN = { local: 'รหัสผ่านระบบ', university: 'บัญชีมหาวิทยาลัย' };
  function device(ua) {
    if (!ua) return 'ไม่ทราบ';
    const os = /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : '';
    const app = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : '';
    return [app, os].filter(Boolean).join(' · ') || ua.slice(0, 40);
  }

  async function resetPassword() {
    formError = '';
    try {
      await post(`/admin/users/${resetting.user.id}/password`, { password: resetting.password });
      toast('ตั้งรหัสผ่านใหม่แล้ว ผู้ใช้ต้องเข้าสู่ระบบใหม่');
      resetting = null;
    } catch (err) {
      formError = err.status === 404 ? 'บัญชีนี้ไม่ได้ใช้รหัสผ่านของระบบ (ใช้ SSO)' : errorText(err);
    }
  }
</script>

<div class="stack">
  <div class="row"><h1>ผู้ใช้</h1><span class="spacer"></span><button class="btn" onclick={newUser}><Icon name="plus" size={17} />เพิ่มผู้ใช้</button></div>
  {#if error}<div class="notice bad">{error}</div>{/if}
  {#if requests.length}
    <section class="card requests" aria-labelledby="req-h">
      <h2 id="req-h">คำขอเข้าใช้งาน <span class="badge needs_review">{requests.length}</span></h2>
      <p class="hint">บัญชีมหาวิทยาลัยที่เข้าระบบครั้งแรก ยังเข้าใช้งานไม่ได้จนกว่าจะอนุมัติ ผู้ใช้ที่อนุมัติแล้วอ่านเอกสารได้ทุกฉบับ</p>
      <ul>
        {#each requests as r (r.id)}
          <li>
            <div class="who">
              <b>{r.display_name}</b>
              <small class="muted">{[r.email, r.university_id && `รหัส ${r.university_id}`, r.department, r.account_type].filter(Boolean).join(' · ')}</small>
              <small class="muted">ขอเมื่อ {thDateTime(r.requested_at)}</small>
            </div>
            <div class="acts">
              <button class="btn ghost" onclick={() => (rejecting = r)}>ปฏิเสธ</button>
              <button class="btn" onclick={() => decide(r, 'approve')}>อนุมัติ</button>
            </div>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
  <div class="card table-wrap">
    <table class="data">
      <thead><tr><th>ชื่อ</th><th>บทบาท</th><th>สถานะ</th><th>เข้าใช้ล่าสุด</th><th>อุปกรณ์</th><th></th></tr></thead>
      <tbody>
        {#if users === null}
          <tr><td colspan="6"><div class="skel" style="width:50%"></div></td></tr>
        {:else}
          {#each users as u (u.id)}
            <tr class:off={u.status !== 'active'}>
              <td><b>{u.display_name}</b><br /><small class="muted">{u.email}{#each u.logins as l (l)} · {LOGIN[l] || l}{/each}</small></td>
              <td>
                <select id="role-{u.id}" class="input mini" value={u.role} disabled={u.id === session.user.id} onchange={(e) => change(u, { role: e.currentTarget.value }, 'เปลี่ยนบทบาทแล้ว')}>
                  <option value="user">ผู้ใช้</option><option value="admin">ผู้ดูแลระบบ</option>
                </select>
              </td>
              <td><span class="badge {u.status === 'active' ? 'ready' : 'neutral'}">{u.status === 'active' ? 'ใช้งาน' : 'ปิดใช้งาน'}</span></td>
              <td class="num"><small>{thDateTime(u.last_login_at)}</small></td>
              <td class="num">
                {#if u.active_sessions}<button class="link-btn" onclick={() => showSessions(u)}>{u.active_sessions} เครื่อง</button>{:else}<small class="muted">–</small>{/if}
              </td>
              <td class="acts">
                {#if u.id !== session.user.id}
                  {#if u.status === 'active'}
                    <button class="link-btn" onclick={() => change(u, { status: 'disabled' }, 'ปิดใช้งานบัญชีแล้ว')}>ปิดใช้งาน</button>
                  {:else}
                    <button class="link-btn" onclick={() => change(u, { status: 'active' }, 'เปิดใช้งานบัญชีแล้ว')}>เปิดใช้งาน</button>
                  {/if}
                {/if}
                {#if u.logins.includes('local')}
                  <button class="link-btn" onclick={() => ((formError = ''), (resetting = { user: u, password: '' }))}>ตั้งรหัสผ่าน</button>
                {/if}
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
  <p class="hint">อาจารย์และบุคลากรเข้าสู่ระบบด้วยรหัสและรหัสผ่านของมหาวิทยาลัย (นักศึกษาเข้าไม่ได้) ครั้งแรกต้องรอผู้ดูแลระบบอนุมัติ ยกเว้นผู้ที่เพิ่มไว้ก่อนในหน้านี้ ชื่อผู้ใช้และรหัสผ่านในหน้านี้ใช้สำหรับระบบทดลองและผู้ดูแลระบบเท่านั้น ผู้ใช้จะออกจากระบบอัตโนมัติเมื่อไม่ได้ใช้งาน 1 ชั่วโมง</p>
</div>

{#if creating}
  <Modal title="เพิ่มผู้ใช้" onclose={() => (creating = null)}>
    <label class="field"><span>ชื่อที่แสดง</span><input id="u-name" bind:value={creating.display_name} /></label>
    <label class="field"><span>อีเมล</span><input id="u-email" type="email" bind:value={creating.email} /></label>
    <div class="field"><span>บทบาท</span>
      <div class="seg"><button aria-pressed={creating.role === 'user'} onclick={() => (creating.role = 'user')}>ผู้ใช้</button><button aria-pressed={creating.role === 'admin'} onclick={() => (creating.role = 'admin')}>ผู้ดูแลระบบ</button></div>
    </div>
    <label class="field"><span>รหัสอาจารย์ของมหาวิทยาลัย (ไม่บังคับ)</span><input id="u-uni" bind:value={creating.university_id} autocapitalize="off" /><small>ใส่ถ้าต้องการเพิ่มไว้ก่อนเข้าระบบครั้งแรก</small></label>
    <label class="field"><span>ชื่อผู้ใช้ของระบบ (ไม่บังคับ)</span><input id="u-username" bind:value={creating.username} autocapitalize="off" /><small>สำหรับระบบทดลองหรือผู้ดูแลระบบ เว้นว่างถ้าใช้บัญชีมหาวิทยาลัย</small></label>
    {#if creating.username.trim()}
      <label class="field"><span>รหัสผ่าน (อย่างน้อย 10 ตัวอักษร)</span><input id="u-password" type="password" bind:value={creating.password} autocomplete="new-password" /></label>
    {/if}
    {#if formError}<div class="notice bad">{formError}</div>{/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (creating = null)}>ยกเลิก</button>
      <button class="btn" onclick={create} disabled={!creating.email.trim() || !creating.display_name.trim()}>เพิ่มผู้ใช้</button>
    {/snippet}
  </Modal>
{/if}

{#if rejecting}
  <Modal title="ปฏิเสธคำขอ" onclose={() => (rejecting = null)}>
    <p>{rejecting.display_name} จะเข้าระบบไม่ได้ บัญชีจะอยู่ในรายชื่อแบบปิดใช้งาน เปิดใช้งานภายหลังได้</p>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (rejecting = null)}>ยกเลิก</button>
      <button class="btn danger" onclick={() => decide(rejecting, 'reject')}>ปฏิเสธ</button>
    {/snippet}
  </Modal>
{/if}

{#if sessions}
  <Modal title="อุปกรณ์ที่เข้าระบบอยู่" onclose={() => (sessions = null)}>
    <p>{sessions.user.display_name}</p>
    {#if !sessions.rows.length}<p class="muted">ไม่มีอุปกรณ์ที่เข้าระบบอยู่</p>{/if}
    <ul class="devices">
      {#each sessions.rows as s (s.id)}
        <li><b>{device(s.user_agent)}</b><small class="muted">IP {s.ip || '–'} · เข้าระบบ {thDateTime(s.created_at)} · ใช้ล่าสุด {thDateTime(s.last_seen_at)}</small></li>
      {/each}
    </ul>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (sessions = null)}>ปิด</button>
      {#if sessions.rows.length}<button class="btn danger" onclick={() => endSessions(sessions.user)}>ออกจากระบบทุกอุปกรณ์</button>{/if}
    {/snippet}
  </Modal>
{/if}

{#if resetting}
  <Modal title="ตั้งรหัสผ่านใหม่" onclose={() => (resetting = null)}>
    <p>{resetting.user.display_name} จะถูกออกจากระบบทุกเครื่อง และต้องใช้รหัสใหม่</p>
    <label class="field"><span>รหัสผ่านใหม่ (อย่างน้อย 10 ตัวอักษร)</span><input id="reset-pass" type="password" bind:value={resetting.password} autocomplete="new-password" /></label>
    {#if formError}<div class="notice bad">{formError}</div>{/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (resetting = null)}>ยกเลิก</button>
      <button class="btn" onclick={resetPassword} disabled={resetting.password.length < 10}>บันทึก</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .off { opacity: 0.6; }
  .requests { padding: 16px; display: flex; flex-direction: column; gap: 8px; }
  .requests h2 { font-size: 17px; font-weight: 600; display: flex; gap: 8px; align-items: center; }
  .requests ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .requests li { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--border); }
  .who { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .requests .acts { display: flex; gap: 8px; }
  .mini { min-height: 32px; padding: 3px 8px; font-size: 13.5px; width: auto; }
  .acts { white-space: nowrap; }
  .devices { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  .devices li { display: flex; flex-direction: column; gap: 2px; }
</style>
