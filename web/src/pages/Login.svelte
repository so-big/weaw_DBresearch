<script>
  // Local login is for the demo only; college SSO replaces it later (AuthProvider).
  import { post, errorText } from '../lib/api.js';
  import { session, refreshReviewCount } from '../lib/state.svelte.js';
  import { route, navigate } from '../lib/router.svelte.js';

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let busy = $state(false);

  async function submit(e) {
    e.preventDefault();
    busy = true;
    error = '';
    try {
      session.user = await post('/auth/login', { username: username.trim(), password });
      refreshReviewCount();
      navigate(route.query.get('next') || '/documents', { replace: true });
    } catch (err) {
      error = err.status === 401 ? 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง' : errorText(err);
    } finally {
      busy = false;
    }
  }
</script>

<div class="wrap">
  <div class="strip"></div>
  <form class="card box enter" onsubmit={submit}>
    <div class="brand">
      <h1>คลังเอกสารวิจัย</h1>
      <p class="muted">คณะวิศวกรรมศาสตร์ · สัญญาและเอกสารทุนวิจัย</p>
    </div>
    <label class="field">
      <span>ชื่อผู้ใช้</span>
      <input id="login-user" bind:value={username} autocomplete="username" autocapitalize="off" required />
    </label>
    <label class="field">
      <span>รหัสผ่าน</span>
      <input id="login-pass" type="password" bind:value={password} autocomplete="current-password" required />
    </label>
    {#if error}<div class="notice bad" role="alert">{error}</div>{/if}
    <button class="btn big" disabled={busy}>{busy ? 'กำลังเข้าสู่ระบบ…' : 'เข้าสู่ระบบ'}</button>
    <p class="hint">ระบบนี้จะเปลี่ยนไปใช้บัญชีของมหาวิทยาลัย (SSO) เมื่อฝ่ายไอทีเชื่อมต่อเสร็จ</p>
  </form>
</div>

<style>
  .wrap { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; position: relative; }
  .strip { position: fixed; top: 0; left: 0; right: 0; height: 4px; background: var(--primary); }
  .box { width: min(400px, 100%); padding: 28px 24px; display: flex; flex-direction: column; gap: 16px; box-shadow: var(--shadow); }
  .brand h1 { font-size: 26px; font-weight: 600; color: var(--primary-text); }
  .brand p { font-size: 14px; }
  .hint { text-align: center; }
</style>
