<script>
  // Accounts and roles. Local username/password is for the demo; SSO users need neither.
  import { get, post, patch, errorText } from '../../lib/api.js';
  import { toast, session } from '../../lib/state.svelte.js';
  import { thDateTime } from '../../lib/format.js';
  import Modal from '../../components/Modal.svelte';
  import Icon from '../../components/Icon.svelte';

  let users = $state(null);
  let error = $state('');
  let creating = $state(null);
  let resetting = $state(null);
  let formError = $state('');

  async function load() {
    try {
      users = await get('/admin/users');
    } catch (err) {
      error = errorText(err);
    }
  }
  load();

  function newUser() {
    formError = '';
    creating = { email: '', display_name: '', role: 'user', username: '', password: '' };
  }
  async function create() {
    formError = '';
    const c = creating;
    try {
      await post('/admin/users', {
        email: c.email.trim(),
        display_name: c.display_name.trim(),
        role: c.role,
        username: c.username.trim() || null,
        password: c.username.trim() ? c.password : null,
      });
      toast('เพิ่มผู้ใช้แล้ว');
      creating = null;
      load();
    } catch (err) {
      formError = err.status === 409 ? 'อีเมลหรือชื่อผู้ใช้นี้มีอยู่แล้ว' : errorText(err);
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
  <div class="card table-wrap">
    <table class="data">
      <thead><tr><th>ชื่อ</th><th>บทบาท</th><th>สถานะ</th><th>เข้าใช้ล่าสุด</th><th></th></tr></thead>
      <tbody>
        {#if users === null}
          <tr><td colspan="5"><div class="skel" style="width:50%"></div></td></tr>
        {:else}
          {#each users as u (u.id)}
            <tr class:off={u.status !== 'active'}>
              <td><b>{u.display_name}</b><br /><small class="muted">{u.email}</small></td>
              <td>
                <select id="role-{u.id}" class="input mini" value={u.role} disabled={u.id === session.user.id} onchange={(e) => change(u, { role: e.currentTarget.value }, 'เปลี่ยนบทบาทแล้ว')}>
                  <option value="user">ผู้ใช้</option><option value="admin">ผู้ดูแลระบบ</option>
                </select>
              </td>
              <td><span class="badge {u.status === 'active' ? 'ready' : 'neutral'}">{u.status === 'active' ? 'ใช้งาน' : 'ปิดใช้งาน'}</span></td>
              <td class="num"><small>{thDateTime(u.last_login_at)}</small></td>
              <td class="acts">
                {#if u.id !== session.user.id}
                  {#if u.status === 'active'}
                    <button class="link-btn" onclick={() => change(u, { status: 'disabled' }, 'ปิดใช้งานบัญชีแล้ว')}>ปิดใช้งาน</button>
                  {:else}
                    <button class="link-btn" onclick={() => change(u, { status: 'active' }, 'เปิดใช้งานบัญชีแล้ว')}>เปิดใช้งาน</button>
                  {/if}
                {/if}
                <button class="link-btn" onclick={() => ((formError = ''), (resetting = { user: u, password: '' }))}>ตั้งรหัสผ่าน</button>
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
  <p class="hint">เมื่อเชื่อมต่อ SSO ของมหาวิทยาลัยแล้ว ผู้ใช้จะเข้าสู่ระบบด้วยบัญชีมหาวิทยาลัย ชื่อผู้ใช้และรหัสผ่านในหน้านี้ใช้สำหรับระบบทดลองเท่านั้น</p>
</div>

{#if creating}
  <Modal title="เพิ่มผู้ใช้" onclose={() => (creating = null)}>
    <label class="field"><span>ชื่อที่แสดง</span><input id="u-name" bind:value={creating.display_name} /></label>
    <label class="field"><span>อีเมล</span><input id="u-email" type="email" bind:value={creating.email} /></label>
    <div class="field"><span>บทบาท</span>
      <div class="seg"><button aria-pressed={creating.role === 'user'} onclick={() => (creating.role = 'user')}>ผู้ใช้</button><button aria-pressed={creating.role === 'admin'} onclick={() => (creating.role = 'admin')}>ผู้ดูแลระบบ</button></div>
    </div>
    <label class="field"><span>ชื่อผู้ใช้ (ไม่บังคับ)</span><input id="u-username" bind:value={creating.username} autocapitalize="off" /><small>เว้นว่างถ้าจะให้เข้าระบบผ่าน SSO</small></label>
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
  .mini { min-height: 32px; padding: 3px 8px; font-size: 13.5px; width: auto; }
  .acts { white-space: nowrap; }
</style>
