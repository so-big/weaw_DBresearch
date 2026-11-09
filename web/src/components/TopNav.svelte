<script>
  // PC / tablet header: brand, tabs with a sliding underline, search, upload, account.
  import Icon from './Icon.svelte';
  import { route, navigate } from '../lib/router.svelte.js';
  import { session, review, isAdmin, theme, setTheme, ui } from '../lib/state.svelte.js';
  import { openUpload, busyCount, uploads } from '../lib/uploads.svelte.js';
  import { logout } from '../lib/auth.js';
  import Modal from './Modal.svelte';

  const tabs = $derived([
    { href: '/documents', label: 'เอกสาร', on: route.path === '/documents' || route.path.startsWith('/documents/') },
    { href: '/review', label: 'รอตรวจสอบ', count: review.count, on: route.path === '/review' },
    { href: '/overview', label: 'ภาพรวม', on: route.path === '/overview' },
    { href: '/shares', label: 'ลิงก์แชร์', on: route.path === '/shares' },
    ...(isAdmin() ? [{ href: '/admin', label: 'ผู้ดูแลระบบ', on: route.path.startsWith('/admin') }] : []),
  ]);

  let nav = $state();
  let ind = $state({ x: 0, w: 0, show: false });
  let q = $state(route.path === '/documents' ? route.query.get('q') || '' : '');
  let menuOpen = $state(false);
  let askAll = $state(false);
  let searchInput = $state();
  let measure = $state(0); // bumps on resize / font load so the underline re-measures
  document.fonts?.ready.then(() => measure++);

  // Slide the underline with a transform only (no layout work).
  $effect(() => {
    tabs; // re-run when the active tab changes
    measure;
    const el = nav?.querySelector('a[aria-current="page"]');
    if (!el) {
      ind.show = false;
      return;
    }
    const box = nav.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    ind = { x: r.left - box.left + 10, w: r.width - 20, show: true };
  });

  $effect(() => {
    if (route.path === '/documents') q = route.query.get('q') || '';
  });

  function submit(e) {
    e.preventDefault();
    const sp = new URLSearchParams(route.path === '/documents' ? route.query : '');
    if (q.trim()) sp.set('q', q.trim());
    else sp.delete('q');
    sp.delete('page');
    navigate(`/documents${sp.toString() ? `?${sp}` : ''}`, { replace: route.path === '/documents' });
  }

  function onKey(e) {
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) {
      e.preventDefault();
      if (searchInput) searchInput.focus();
      else ui.searchFocus++; // the documents page's own search box
    }
    if (e.key === 'Escape') menuOpen = false;
  }
</script>

<svelte:window onkeydown={onKey} onresize={() => measure++} />

<header class="top">
  <div class="strip"></div>
  <div class="bar">
    <a class="brand" href="/documents">
      <span class="name">คลังเอกสารวิจัย</span>
      <span class="sub">คณะวิศวกรรมศาสตร์</span>
    </a>
    <nav class="tabs" bind:this={nav} aria-label="เมนูหลัก">
      {#each tabs as t (t.href)}
        <a href={t.href} aria-current={t.on ? 'page' : undefined}>
          {t.label}
          {#if t.count}<span class="count">{t.count}</span>{/if}
        </a>
      {/each}
      <span class="ind" class:show={ind.show} style="transform: translateX({ind.x}px) scaleX({ind.w})"></span>
    </nav>
    <span class="spacer"></span>
    {#if busyCount() > 0 && !uploads.open}
      <button class="pill" onclick={openUpload}><span class="spin"></span>กำลังอัปโหลด {busyCount()} ไฟล์</button>
    {/if}
    {#if route.path !== '/documents'}
      <form class="search" onsubmit={submit} role="search">
        <Icon name="search" size={16} />
        <input bind:this={searchInput} bind:value={q} type="search" placeholder="ค้นหาชื่อเรื่อง เลขสัญญา ข้อความ" aria-label="ค้นหาเอกสาร" />
        <kbd>/</kbd>
      </form>
    {/if}
    <button class="btn" onclick={openUpload}><Icon name="upload" size={17} />อัปโหลด</button>
    <div class="acct">
      <button class="icon-btn avatar" onclick={() => (menuOpen = !menuOpen)} aria-expanded={menuOpen} aria-label="บัญชี">
        {session.user?.display_name?.slice(0, 1) || '?'}
      </button>
      {#if menuOpen}
        <button class="backdrop" aria-label="ปิดเมนู" onclick={() => (menuOpen = false)}></button>
        <div class="menu card enter">
          <div class="who">
            <b>{session.user?.display_name}</b>
            <small class="muted">{session.user?.email} · {isAdmin() ? 'ผู้ดูแลระบบ' : 'ผู้ใช้'}</small>
          </div>
          <div class="label">ธีม</div>
          <div class="seg">
            {#each [['system', 'ตามเครื่อง'], ['light', 'สว่าง'], ['dark', 'มืด']] as [v, l] (v)}
              <button aria-pressed={theme.value === v} onclick={() => setTheme(v)}>{l}</button>
            {/each}
          </div>
          <a class="mlink" href="/trash" onclick={() => (menuOpen = false)}><Icon name="trash" size={17} />ถังขยะของฉัน</a>
          <button class="btn ghost" onclick={() => logout()}><Icon name="logout" size={17} />ออกจากระบบ</button>
          <button class="link-btn all" onclick={() => ((menuOpen = false), (askAll = true))}>ออกจากระบบทุกอุปกรณ์</button>
        </div>
      {/if}
    </div>
  </div>
</header>

{#if askAll}
  <Modal title="ออกจากระบบทุกอุปกรณ์?" onclose={() => (askAll = false)}>
    <p>ทุกเครื่องที่เข้าระบบด้วยบัญชีนี้อยู่ รวมถึงเครื่องนี้ จะต้องเข้าสู่ระบบใหม่</p>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (askAll = false)}>ยกเลิก</button>
      <button class="btn danger" onclick={() => logout(true)}>ออกจากระบบทุกอุปกรณ์</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .top { position: sticky; top: 0; z-index: 20; background: var(--surface); border-bottom: 1px solid var(--border); }
  .strip { height: 3px; background: var(--primary); }
  .bar { display: flex; align-items: center; gap: 18px; height: var(--header-h); padding: 0 max(20px, env(safe-area-inset-right)) 0 max(20px, env(safe-area-inset-left)); max-width: 1440px; margin: 0 auto; }
  .brand { display: flex; flex-direction: column; text-decoration: none; line-height: 1.15; }
  .brand .name { font-family: var(--f-display); font-weight: 600; font-size: 16px; color: var(--primary-text); white-space: nowrap; }
  .brand .sub { font-size: 11px; color: var(--muted); white-space: nowrap; }
  .tabs { position: relative; display: flex; height: 100%; }
  .tabs a { display: flex; align-items: center; gap: 6px; padding: 0 12px; color: var(--muted); text-decoration: none; font-size: 14.5px; white-space: nowrap; transition: color var(--t-fast); }
  .tabs a:hover { color: var(--text); }
  .tabs a[aria-current='page'] { color: var(--text); font-weight: 600; }
  .ind { position: absolute; left: 0; bottom: -1px; width: 1px; height: 3px; background: var(--primary); border-radius: 3px 3px 0 0; transform-origin: left; opacity: 0; transition: transform var(--t-med) var(--ease-out), opacity var(--t-fast); }
  .ind.show { opacity: 1; }
  .count { font-size: 11px; font-weight: 600; min-width: 19px; height: 19px; padding: 0 6px; border-radius: 999px; background: var(--warn-soft); color: var(--warn); display: inline-grid; place-items: center; animation: pop 320ms var(--ease-out); }
  @keyframes pop { 40% { transform: scale(1.3); } }
  .search { display: flex; align-items: center; gap: 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 0 10px; width: min(300px, 26vw); color: var(--muted); transition: border-color var(--t-fast); }
  .search:focus-within { border-color: var(--primary); }
  .search input { border: 0; background: none; outline: none; padding: 8px 0; font-size: 14px; width: 100%; min-width: 0; color: var(--text); }
  .search kbd { font-family: var(--f-mono); font-size: 11px; border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; }
  .pill { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 4px 12px 4px 8px; font-size: 12.5px; color: var(--muted); white-space: nowrap; animation: fade-up var(--t-med) var(--ease-out); }
  .acct { position: relative; }
  .avatar { background: var(--primary-soft); color: var(--primary-text); font-weight: 600; font-family: var(--f-display); }
  .backdrop { position: fixed; inset: 0; background: transparent; border: 0; z-index: 1; cursor: default; }
  .menu { position: absolute; right: 0; top: calc(100% + 8px); width: 260px; padding: 14px; display: flex; flex-direction: column; gap: 10px; z-index: 2; box-shadow: var(--shadow); }
  .who { display: flex; flex-direction: column; }
  .mlink { display: flex; align-items: center; gap: 10px; padding: 8px 10px; margin: 0 -4px; border-radius: 8px; color: var(--text); text-decoration: none; font-size: 14px; }
  .mlink:hover { background: var(--subtle); }
  .all { font-size: 13px; padding: 4px 0; align-self: center; }
  .who small { font-size: 12px; overflow-wrap: anywhere; }
  @media (max-width: 1020px) { .brand .sub { display: none; } .search kbd { display: none; } }
</style>
