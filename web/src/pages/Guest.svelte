<script>
  // A share link opened by anyone (no login). Mostly on phones: one card, one big button.
  import { onMount } from 'svelte';
  import { get, post, ApiError } from '../lib/api.js';
  import { thDate, bytes, timeLeft } from '../lib/format.js';
  import Icon from '../components/Icon.svelte';

  let { token } = $props();
  let info = $state(null);
  let gone = $state(false);
  let password = $state('');
  let pwError = $state('');
  let busy = $state(false);

  const base = $derived(`/api/s/${encodeURIComponent(token)}`);

  async function load() {
    try {
      info = await get(`/s/${encodeURIComponent(token)}`, null, { quiet401: true });
    } catch {
      gone = true;
    }
  }
  onMount(load);

  async function unlock(e) {
    e.preventDefault();
    busy = true;
    pwError = '';
    try {
      await post(`/s/${encodeURIComponent(token)}/unlock`, { password });
      await load();
    } catch (err) {
      pwError = err instanceof ApiError && err.status === 403 ? 'รหัสผ่านไม่ถูกต้อง' : 'ลิงก์นี้ใช้ไม่ได้แล้ว';
      if (err.status === 404) gone = true;
    } finally {
      busy = false;
    }
  }

  // Every open (view or download) counts down on the server; refresh the count shortly after.
  function downloaded() {
    setTimeout(load, 1500);
  }
</script>

<div class="wrap">
  <header class="band">
    <div class="bar"><span class="brand">คลังเอกสารวิจัย</span><span class="fac">คณะวิศวกรรมศาสตร์</span></div>
    <p class="lead">{gone ? 'ลิงก์แชร์เอกสาร' : 'มีผู้แชร์เอกสารนี้ให้คุณ'}</p>
  </header>

  <main>
    {#if gone}
      <div class="card box enter center">
        <Icon name="clock" size={36} />
        <h1>ลิงก์นี้ใช้ไม่ได้</h1>
        <p class="muted">ลิงก์อาจหมดอายุ ถูกยกเลิก หรือเปิดไฟล์ครบจำนวนแล้ว กรุณาขอลิงก์ใหม่จากผู้ส่ง</p>
      </div>
    {:else if !info}
      <div class="card box"><div class="skel" style="width:40%"></div><div class="skel" style="width:90%;height:18px"></div><div class="skel" style="width:70%"></div></div>
    {:else if info.requires_password && !info.unlocked}
      <form class="card box enter" onsubmit={unlock}>
        <span class="lock"><Icon name="lock" size={22} /></span>
        <h1>{info.title}</h1>
        <p class="muted">เอกสารนี้ป้องกันด้วยรหัสผ่าน ใส่รหัสที่ได้รับจากผู้ส่ง</p>
        <label class="field">
          <span>รหัสผ่าน</span>
          <input id="guest-pass" bind:value={password} autocomplete="off" autocapitalize="off" required />
        </label>
        {#if pwError}<div class="notice bad" role="alert">{pwError}</div>{/if}
        <button class="btn big" disabled={busy}>เปิดเอกสาร</button>
      </form>
    {:else}
      <div class="card box enter">
        <span class="expiry"><Icon name="clock" size={14} />หมดอายุ {thDate(info.expires_at)} ({timeLeft(info.expires_at)})</span>
        <h1>{info.title}</h1>
        <dl class="kv">
          <dt>ไฟล์</dt><dd class="name">{info.filename}</dd>
          <dt>ขนาด</dt><dd>{info.pages ? `${info.pages} หน้า · ` : ''}{bytes(info.size_bytes)}</dd>
        </dl>
        {#if info.allow_download}
          <a class="btn big" href="{base}/file?download=true" onclick={downloaded}><Icon name="download" />ดาวน์โหลด PDF</a>
        {/if}
        <a class="btn big ghost" href="{base}/file" target="_blank" rel="noopener" onclick={downloaded}><Icon name="eye" />เปิดดูในเบราว์เซอร์</a>
        <p class="note muted">
          {#if info.downloads_left !== null}เปิดไฟล์ได้อีก {info.downloads_left} ครั้ง (เปิดดูหรือดาวน์โหลดนับเป็น 1 ครั้ง)
          {/if}
        </p>
      </div>
    {/if}
  </main>
</div>

<style>
  .wrap { min-height: 100vh; display: flex; flex-direction: column; }
  .band {
    color: #fff; padding: calc(14px + env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) 64px max(16px, env(safe-area-inset-left));
    background:
      radial-gradient(circle at 100% 0%, rgba(255, 255, 255, 0.12) 0 130px, transparent 131px),
      linear-gradient(135deg, var(--band-1), var(--band-2) 55%, var(--band-3));
  }
  .bar, .lead { max-width: 528px; margin: 0 auto; }
  .bar { display: flex; align-items: baseline; gap: 10px; font-size: 12.5px; }
  .brand { font-family: var(--f-display); font-weight: 600; font-size: 17px; }
  .fac { opacity: 0.8; }
  .lead { font-family: var(--f-display); font-weight: 500; font-size: 22px; margin-top: 18px; }
  main { flex: 1; width: 100%; max-width: 560px; margin: -48px auto 0; padding: 0 max(16px, env(safe-area-inset-right)) calc(32px + env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left)); }
  .box { padding: 22px 20px; display: flex; flex-direction: column; gap: 14px; box-shadow: var(--shadow); }
  .box h1 { font-size: 20px; line-height: 1.4; overflow-wrap: anywhere; }
  .center { align-items: center; text-align: center; color: var(--muted); }
  .center h1 { color: var(--text); }
  .lock { width: 44px; height: 44px; border-radius: 50%; background: var(--primary-soft); color: var(--primary-text); display: grid; place-items: center; }
  .expiry { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft); color: var(--accent-text); font-size: 12.5px; font-weight: 500; padding: 3px 10px; border-radius: 999px; }
  .kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 0; font-size: 14px; }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; min-width: 0; }
  .name { overflow-wrap: anywhere; }
  .note { text-align: center; font-size: 13px; min-height: 1.6em; }
</style>
