<script>
  // Accounts and roles. Staff log in with their university account; a local username and
  // password is only for the demo and bootstrap admins. Every account opens one "manage"
  // window (role, on/off, devices, password, delete), so the list itself stays readable.
  import { get, post, patch, del, errorText } from '../../lib/api.js';
  import { toast, session, access, screen } from '../../lib/state.svelte.js';
  import { thDateTime } from '../../lib/format.js';
  import Modal from '../../components/Modal.svelte';
  import Icon from '../../components/Icon.svelte';

  let view = $state('active'); // 'active' (in use: active + disabled) or 'deleted'
  let users = $state(null);
  let requests = $state([]);
  let filter = $state('');
  let error = $state('');
  let rejecting = $state(null);
  let creating = $state(null);
  let managing = $state(null); // the account whose manage window is open
  let sessions = $state(null); // its devices, loaded when the window opens
  let resetting = $state(null);
  let deleting = $state(null);
  let formError = $state('');

  async function load() {
    try {
      [users, requests] = await Promise.all([
        get('/admin/users', view === 'deleted' ? { deleted: true } : undefined),
        get('/admin/users/requests'),
      ]);
      access.requests = requests.length;
      error = '';
      if (managing) managing = users.find((u) => u.id === managing.id) || null;
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    view;
    users = null;
    load();
  });

  const shown = $derived.by(() => {
    const f = filter.trim().toLowerCase();
    if (!users) return null;
    if (!f) return users;
    return users.filter((u) => [u.display_name, u.email, u.university_id].some((v) => v?.toLowerCase().includes(f)));
  });
  const counts = $derived(users && view === 'active' ? { admins: users.filter((u) => u.role === 'admin' && u.status === 'active').length, off: users.filter((u) => u.status !== 'active').length } : null);

  const LOGIN = { local: 'รหัสผ่านระบบ', university: 'บัญชีมหาวิทยาลัย' };
  const ROLE = { user: 'ผู้ใช้', admin: 'ผู้ดูแลระบบ' };
  const me = (u) => u.id === session.user.id;

  function device(ua) {
    if (!ua) return 'ไม่ทราบ';
    const os = /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : '';
    const app = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : '';
    return [app, os].filter(Boolean).join(' · ') || ua.slice(0, 40);
  }

  // ── new account ──
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
      view = 'active';
      load();
    } catch (err) {
      formError = err.status === 409 ? 'อีเมล ชื่อผู้ใช้ หรือรหัสมหาวิทยาลัยนี้มีอยู่แล้ว (รวมบัญชีที่ลบไว้)' : errorText(err);
    }
  }

  // ── access requests ──
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

  // ── manage one account ──
  async function manage(u) {
    managing = u;
    sessions = null;
    if (u.active_sessions) {
      try {
        sessions = await get(`/admin/users/${u.id}/sessions`);
      } catch {
        sessions = [];
      }
    } else sessions = [];
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
  async function endSessions(u) {
    try {
      await post(`/admin/users/${u.id}/sessions/revoke`);
      toast('ออกจากระบบทุกอุปกรณ์แล้ว');
      sessions = [];
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function resetPassword() {
    formError = '';
    try {
      await post(`/admin/users/${resetting.id}/password`, { password: resetting.password });
      toast('ตั้งรหัสผ่านใหม่แล้ว ผู้ใช้ต้องเข้าสู่ระบบใหม่');
      resetting = null;
    } catch (err) {
      formError = err.status === 404 ? 'บัญชีนี้ไม่ได้ใช้รหัสผ่านของระบบ' : errorText(err);
    }
  }
  async function remove() {
    const u = deleting;
    try {
      const res = await del(`/admin/users/${u.id}`);
      deleting = null;
      managing = null;
      const links = res.revoked_links ? ` ยกเลิกลิงก์แชร์ ${res.revoked_links} ลิงก์` : '';
      toast(res.removed ? `ลบบัญชี ${u.display_name} แล้ว` : `ลบบัญชี ${u.display_name} แล้ว ประวัติยังเก็บไว้${links}`);
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function restore(u) {
    try {
      await post(`/admin/users/${u.id}/restore`);
      toast(`กู้คืน ${u.display_name} แล้ว บัญชียังปิดใช้งานอยู่ เปิดได้จากแท็บใช้งานอยู่`);
      load();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
</script>

<div class="users">
  <div class="head">
    <h1>ผู้ใช้</h1>
    {#if counts}<span class="muted num">{users.length} บัญชี · ผู้ดูแลระบบ {counts.admins}{counts.off ? ` · ปิดใช้งาน ${counts.off}` : ''}</span>{/if}
    <span class="spacer"></span>
    <button class="btn" onclick={newUser}><Icon name="plus" size={16} />เพิ่มผู้ใช้</button>
  </div>
  {#if error}<div class="notice bad">{error}</div>{/if}

  {#if requests.length}
    <section class="card requests" aria-labelledby="req-h">
      <div class="req-head">
        <h2 id="req-h">คำขอเข้าใช้งาน</h2>
        <span class="badge needs_review">{requests.length} รออนุมัติ</span>
      </div>
      <p class="hint">เจ้าหน้าที่ที่เข้าระบบครั้งแรก ใช้งานได้หลังอนุมัติ และอ่านเอกสารได้ทุกฉบับ</p>
      <ul>
        {#each requests as r (r.id)}
          <li>
            <div class="who">
              <b>{r.display_name}</b>
              <small class="muted">{[r.email, r.university_id && `รหัส ${r.university_id}`, r.department, r.account_type].filter(Boolean).join(' · ')}</small>
              <small class="muted">ขอเมื่อ {thDateTime(r.requested_at)}</small>
            </div>
            <div class="acts">
              <button class="btn ghost small" onclick={() => (rejecting = r)}>ปฏิเสธ</button>
              <button class="btn small" onclick={() => decide(r, 'approve')}>อนุมัติ</button>
            </div>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <div class="tools">
    <div class="seg" role="group" aria-label="แสดงบัญชี">
      <button aria-pressed={view === 'active'} onclick={() => (view = 'active')}>ใช้งานอยู่</button>
      <button aria-pressed={view === 'deleted'} onclick={() => (view = 'deleted')}>ลบแล้ว</button>
    </div>
    <label class="find">
      <Icon name="search" size={16} />
      <input type="search" bind:value={filter} placeholder="ค้นหาชื่อ อีเมล รหัส" aria-label="ค้นหาผู้ใช้" />
    </label>
  </div>

  {#if shown === null}
    <div class="card list"><div class="item"><div class="skel" style="width:40%"></div></div><div class="item"><div class="skel" style="width:55%"></div></div></div>
  {:else if !shown.length}
    <div class="card empty muted">{filter ? 'ไม่พบบัญชีที่ตรงกับคำค้น' : view === 'deleted' ? 'ไม่มีบัญชีที่ลบไว้' : 'ยังไม่มีบัญชี'}</div>
  {:else if screen.wide}
    <div class="card table-wrap">
      <table class="data">
        <thead>
          <tr><th>ชื่อ</th><th>บทบาท</th><th>สถานะ</th><th>เข้าใช้ล่าสุด</th><th class="r">อุปกรณ์</th><th></th></tr>
        </thead>
        <tbody>
          {#each shown as u (u.id)}
            <tr class:off={u.status !== 'active'}>
              <td>
                <div class="name"><b>{u.display_name}</b>{#if me(u)}<span class="you">คุณ</span>{/if}</div>
                <small class="muted">{u.email}{#each u.logins as l (l)} · {LOGIN[l] || l}{/each}</small>
              </td>
              <td><span class="role" class:admin={u.role === 'admin'}>{ROLE[u.role]}</span></td>
              <td>{@render status(u)}</td>
              <td class="num"><small>{thDateTime(u.last_login_at)}</small></td>
              <td class="r num">{u.active_sessions || '–'}</td>
              <td class="r">
                {#if view === 'deleted'}
                  <button class="btn small ghost" onclick={() => restore(u)}><Icon name="undo" size={16} />กู้คืน</button>
                {:else}
                  <button class="btn small ghost" onclick={() => manage(u)}>จัดการ</button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <ul class="card list">
      {#each shown as u (u.id)}
        <li class="item" class:off={u.status !== 'active'}>
          <div class="who">
            <div class="name"><b>{u.display_name}</b>{#if me(u)}<span class="you">คุณ</span>{/if}</div>
            <small class="muted">{u.email}</small>
            <div class="line">
              <span class="role" class:admin={u.role === 'admin'}>{ROLE[u.role]}</span>
              {@render status(u)}
            </div>
          </div>
          {#if view === 'deleted'}
            <button class="btn small ghost" onclick={() => restore(u)}>กู้คืน</button>
          {:else}
            <button class="btn small ghost" onclick={() => manage(u)}>จัดการ</button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <details class="about">
    <summary>เกี่ยวกับบัญชีผู้ใช้</summary>
    <ul>
      <li>เจ้าหน้าที่เข้าสู่ระบบด้วยรหัสและรหัสผ่านของมหาวิทยาลัย ครั้งแรกต้องรออนุมัติ ยกเว้นผู้ที่เพิ่มไว้ก่อนในหน้านี้</li>
      <li>อาจารย์ไม่ต้องมีบัญชี ส่งลิงก์แชร์ให้เปิดดูและพิมพ์เอกสารได้</li>
      <li>ชื่อผู้ใช้และรหัสผ่านของระบบใช้สำหรับระบบทดลองและผู้ดูแลระบบเท่านั้น</li>
      <li>ผู้ใช้ออกจากระบบอัตโนมัติเมื่อไม่ได้ใช้งาน 1 ชั่วโมง</li>
      <li>บัญชีที่ลบแล้วเข้าระบบไม่ได้ ชื่อยังแสดงในประวัติเอกสาร และกู้คืนได้จากแท็บลบแล้ว</li>
    </ul>
  </details>
</div>

{#snippet status(u)}
  {#if view === 'deleted'}
    <span class="badge neutral">ลบแล้ว</span>
  {:else}
    <span class="badge {u.status === 'active' ? 'ready' : 'neutral'}">{u.status === 'active' ? 'ใช้งาน' : 'ปิดใช้งาน'}</span>
  {/if}
{/snippet}

{#if managing}
  {@const u = managing}
  <Modal title={u.display_name} onclose={() => (managing = null)} width={520}>
    <p class="muted sub">{u.email}{#if u.university_id} · รหัส {u.university_id}{/if}{#each u.logins as l (l)} · {LOGIN[l] || l}{/each}</p>

    <div class="mrow">
      <div class="mlabel"><b>บทบาท</b><small class="muted">ผู้ดูแลระบบจัดการผู้ใช้ ถังขยะ และการตั้งค่าได้</small></div>
      <div class="seg">
        {#each ['user', 'admin'] as r (r)}
          <button aria-pressed={u.role === r} disabled={me(u)} onclick={() => u.role !== r && change(u, { role: r }, 'เปลี่ยนบทบาทแล้ว')}>{ROLE[r]}</button>
        {/each}
      </div>
    </div>

    <div class="mrow">
      <div class="mlabel"><b>สถานะ</b><small class="muted">ปิดใช้งานแล้วเข้าระบบไม่ได้ อุปกรณ์ทุกเครื่องออกจากระบบ</small></div>
      <div class="seg">
        <button aria-pressed={u.status === 'active'} disabled={me(u)} onclick={() => u.status !== 'active' && change(u, { status: 'active' }, 'เปิดใช้งานบัญชีแล้ว')}>ใช้งาน</button>
        <button aria-pressed={u.status !== 'active'} disabled={me(u)} onclick={() => u.status === 'active' && change(u, { status: 'disabled' }, 'ปิดใช้งานบัญชีแล้ว')}>ปิดใช้งาน</button>
      </div>
    </div>

    <div class="mrow col">
      <div class="mlabel"><b>อุปกรณ์ที่เข้าระบบอยู่</b><small class="muted">เข้าใช้ล่าสุด {thDateTime(u.last_login_at)}</small></div>
      {#if sessions === null}
        <div class="skel" style="width:60%"></div>
      {:else if !sessions.length}
        <small class="muted">ไม่มี</small>
      {:else}
        <ul class="devices">
          {#each sessions as s (s.id)}
            <li><span>{device(s.user_agent)}</span><small class="muted">IP {s.ip || '–'} · ใช้ล่าสุด {thDateTime(s.last_seen_at)}</small></li>
          {/each}
        </ul>
        <button class="btn small ghost" onclick={() => endSessions(u)}><Icon name="logout" size={16} />ออกจากระบบทุกอุปกรณ์</button>
      {/if}
    </div>

    {#if u.logins.includes('local')}
      <div class="mrow">
        <div class="mlabel"><b>รหัสผ่านของระบบ</b><small class="muted">ตั้งใหม่แล้วผู้ใช้ต้องเข้าระบบใหม่ทุกเครื่อง</small></div>
        <button class="btn small ghost" onclick={() => ((formError = ''), (resetting = { id: u.id, name: u.display_name, password: '' }))}>ตั้งรหัสผ่าน</button>
      </div>
    {/if}

    {#if !me(u)}
      <div class="mrow danger-zone">
        <div class="mlabel"><b>ลบบัญชี</b><small class="muted">ซ่อนจากรายชื่อและเข้าระบบไม่ได้ ประวัติยังอยู่</small></div>
        <button class="btn small ghost bad" onclick={() => (deleting = u)}><Icon name="trash" size={16} />ลบบัญชี</button>
      </div>
    {/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (managing = null)}>ปิด</button>
    {/snippet}
  </Modal>
{/if}

{#if deleting}
  <Modal title="ลบบัญชี {deleting.display_name}?" onclose={() => (deleting = null)}>
    <ul class="effects">
      <li>เข้าสู่ระบบไม่ได้ และทุกอุปกรณ์ออกจากระบบทันที</li>
      <li>ลิงก์แชร์ที่บัญชีนี้สร้างไว้และยังใช้งานได้ จะถูกยกเลิก</li>
      <li>เอกสารที่อัปโหลดไว้ยังอยู่ครบ ชื่อยังแสดงในประวัติ</li>
      <li>ถ้าบัญชียังไม่เคยใช้งานเลย ระบบจะลบออกถาวร ไม่เช่นนั้นกู้คืนได้จากแท็บลบแล้ว</li>
    </ul>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (deleting = null)}>ยกเลิก</button>
      <button class="btn danger" onclick={remove}>ลบบัญชี</button>
    {/snippet}
  </Modal>
{/if}

{#if creating}
  <Modal title="เพิ่มผู้ใช้" onclose={() => (creating = null)}>
    <label class="field"><span>ชื่อที่แสดง</span><input id="u-name" bind:value={creating.display_name} /></label>
    <label class="field"><span>อีเมล</span><input id="u-email" type="email" bind:value={creating.email} /></label>
    <div class="field"><span>บทบาท</span>
      <div class="seg"><button aria-pressed={creating.role === 'user'} onclick={() => (creating.role = 'user')}>ผู้ใช้</button><button aria-pressed={creating.role === 'admin'} onclick={() => (creating.role = 'admin')}>ผู้ดูแลระบบ</button></div>
    </div>
    <label class="field"><span>รหัสบุคลากรของมหาวิทยาลัย (ไม่บังคับ)</span><input id="u-uni" bind:value={creating.university_id} autocapitalize="off" /><small>ใส่ถ้าต้องการเพิ่มไว้ก่อนเข้าระบบครั้งแรก</small></label>
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

{#if resetting}
  <Modal title="ตั้งรหัสผ่านใหม่" onclose={() => (resetting = null)}>
    <p>{resetting.name} จะถูกออกจากระบบทุกเครื่อง และต้องใช้รหัสใหม่</p>
    <label class="field"><span>รหัสผ่านใหม่ (อย่างน้อย 10 ตัวอักษร)</span><input id="reset-pass" type="password" bind:value={resetting.password} autocomplete="new-password" /></label>
    {#if formError}<div class="notice bad">{formError}</div>{/if}
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (resetting = null)}>ยกเลิก</button>
      <button class="btn" onclick={resetPassword} disabled={resetting.password.length < 10}>บันทึก</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .users { display: flex; flex-direction: column; gap: 16px; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .head .muted { font-size: 13px; }

  .requests { padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; border-color: var(--warn); }
  .req-head { display: flex; gap: 8px; align-items: center; }
  .req-head h2 { font-size: 16px; }
  .requests ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .requests li { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; padding: 12px 0; border-top: 1px solid var(--border); }
  .who { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .acts { display: flex; gap: 8px; }

  .tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .find { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; flex: 1; max-width: 320px; min-width: 200px; background: var(--surface); border: 1px solid var(--border-strong); border-radius: 10px; color: var(--muted); }
  .find:focus-within { border-color: var(--primary); }
  .find input { border: 0; background: none; outline: none; flex: 1; min-width: 0; font-size: 14px; color: var(--text); }

  .name { display: flex; align-items: center; gap: 8px; }
  .you { font-size: 12px; color: var(--muted); border: 1px solid var(--border); border-radius: 4px; padding: 0 4px; line-height: 18px; }
  .role { font-size: 13px; }
  .role.admin { color: var(--primary-text); font-weight: 500; }
  .off td, .item.off .who { opacity: 0.6; }
  .r { text-align: right; }
  table.data td { vertical-align: middle; }
  table.data small { font-size: 12px; }

  .list { list-style: none; margin: 0; padding: 0; }
  .item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-top: 1px solid var(--border); }
  .item:first-child { border-top: 0; }
  .item .who { flex: 1; }
  .item small { font-size: 12px; overflow-wrap: anywhere; }
  .line { display: flex; gap: 8px; align-items: center; margin-top: 4px; }
  .empty { padding: 32px 16px; text-align: center; font-size: 14px; }

  .about { font-size: 13px; color: var(--muted); }
  .about summary { cursor: pointer; width: fit-content; }
  .about ul { margin: 8px 0 0; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }

  /* manage window */
  .sub { font-size: 13px; overflow-wrap: anywhere; margin-bottom: 8px; }
  .mrow { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; border-top: 1px solid var(--border); flex-wrap: wrap; }
  .mrow.col { flex-direction: column; align-items: stretch; gap: 8px; }
  .mrow.col .btn { align-self: flex-start; }
  .mlabel { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1 1 220px; }
  .mlabel b { font-weight: 500; font-size: 14px; }
  .mlabel small { font-size: 12px; }
  .devices { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
  .devices li { display: flex; flex-direction: column; }
  .devices small { font-size: 12px; }
  .btn.bad { color: var(--bad); }
  .btn.bad:hover { background: var(--bad-soft); border-color: var(--bad-soft); }
  .effects { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
</style>
