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
  <aside class="brand-side">
    <div class="brand-in">
      <span class="fac">คณะวิศวกรรมศาสตร์</span>
      <h1>คลังเอกสารวิจัย</h1>
      <p>สัญญาและเอกสารทุนวิจัยของคณะ ค้นหา ดาวน์โหลด และแชร์ได้ในที่เดียว ไฟล์ทุกฉบับถูกเข้ารหัสก่อนจัดเก็บ</p>
    </div>
  </aside>
  <main class="form-side">
    <form class="box enter" onsubmit={submit}>
      <h2>เข้าสู่ระบบ</h2>
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
  </main>
</div>

<style>
  .wrap { min-height: 100vh; display: grid; grid-template-columns: minmax(320px, 0.9fr) 1fr; }
  .brand-side {
    position: relative; overflow: hidden; color: #fff; display: flex; align-items: flex-end;
    padding: 48px max(40px, env(safe-area-inset-left));
    background:
      radial-gradient(circle at 105% -5%, rgba(255, 255, 255, 0.12) 0 210px, transparent 211px),
      radial-gradient(circle at -10% 110%, rgba(255, 255, 255, 0.08) 0 170px, transparent 171px),
      linear-gradient(150deg, var(--band-3), var(--band-2) 45%, var(--band-1));
  }
  .brand-in { max-width: 420px; display: flex; flex-direction: column; gap: 12px; }
  .fac { font-size: 14px; opacity: 0.85; }
  .brand-in h1 { font-size: 44px; font-weight: 600; color: #fff; line-height: 1.15; }
  .brand-in p { font-size: 15.5px; line-height: 1.7; opacity: 0.9; }
  .form-side { display: grid; place-items: center; padding: 32px 24px; }
  .box { width: min(380px, 100%); display: flex; flex-direction: column; gap: 16px; }
  .box h2 { font-size: 24px; font-weight: 600; }
  .hint { text-align: center; }
  @media (max-width: 767px) {
    .wrap { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .brand-side { padding: calc(28px + env(safe-area-inset-top)) 20px 26px; border-radius: 0 0 24px 24px; }
    .brand-in h1 { font-size: 30px; }
    .brand-in p { font-size: 14px; }
    .form-side { place-items: start center; padding-top: 28px; }
  }
</style>
