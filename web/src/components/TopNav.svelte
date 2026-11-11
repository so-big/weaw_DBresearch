<script>
  // PC / tablet header: brand, tabs with a sliding underline, search, upload, account.
  // หน้าแรก is everyone's start page; ภาพรวม (system overview) is for admins only.
  import Icon from './Icon.svelte';
  import { route, navigate } from '../lib/router.svelte.js';
  import { session, review, isAdmin, theme, setTheme, ui } from '../lib/state.svelte.js';
  import { openUpload, busyCount, uploads } from '../lib/uploads.svelte.js';
  import { logout } from '../lib/auth.js';
  import Modal from './Modal.svelte';

  const tabs = $derived([
    { href: '/', label: 'หน้าแรก', on: route.path === '/' },
    { href: '/documents', label: 'สัญญาทุนวิจัย', on: route.path === '/documents' || route.path.startsWith('/documents/') },
    { href: '/proposals', label: 'ทุนพัฒนาข้อเสนอ', on: route.path === '/proposals' || route.path.startsWith('/proposals/') },
    { href: '/review', label: 'รอตรวจสอบ', count: review.count, on: route.path === '/review' },
    { href: '/shares', label: 'ลิงก์แชร์', on: route.path === '/shares' },
    ...(isAdmin()
      ? [
          { href: '/overview', label: 'ภาพรวม', on: route.path === '/overview' },
          { href: '/admin', label: 'ผู้ดูแลระบบ', on: route.path.startsWith('/admin') },
        ]
      : []),
  ]);

  let nav = $state();
  let ind = $state({ x: 0, w: 0, show: false });
  // The search box searches the section you are in (contracts unless in proposal grants).
  const listPath = $derived(route.path.startsWith('/proposals') ? '/proposals' : '/documents');
  let q = $state(route.path === '/documents' || route.path === '/proposals' ? route.query.get('q') || '' : '');
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
    ind = { x: r.left - box.left + nav.scrollLeft + 12, w: r.width - 24, show: true };
  });

  $effect(() => {
    if (route.path === '/documents' || route.path === '/proposals') q = route.query.get('q') || '';
  });

  function submit(e) {
    e.preventDefault();
    const here = route.path === listPath;
    const sp = new URLSearchParams(here ? route.query : '');
    if (q.trim()) sp.set('q', q.trim());
    else sp.delete('q');
    sp.delete('page');
    navigate(`${listPath}${sp.toString() ? `?${sp}` : ''}`, { replace: here });
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
    <a class="brand" href="/">
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
    {#if route.path !== '/documents' && route.path !== '/proposals' && route.path !== '/'}
      <form class="search" onsubmit={submit} role="search">
        <Icon name="search" size={16} />
        <input bind:this={searchInput} bind:value={q} type="search" placeholder={listPath === '/proposals' ? 'ค้นหาทุนพัฒนาข้อเสนอ' : 'ค้นหาชื่อเรื่อง เลขสัญญา ข้อความ'} aria-label="ค้นหาเอกสาร" />
        <kbd>/</kbd>
      </form>
    {/if}
    <button class="btn up" onclick={openUpload} aria-label="อัปโหลด"><Icon name="upload" size={16} /><span>อัปโหลด</span></button>
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
  .bar { display: flex; align-items: center; gap: 16px; height: var(--header-h); padding: 0 max(24px, env(safe-area-inset-right)) 0 max(24px, env(safe-area-inset-left)); max-width: 1440px; margin: 0 auto; }
  .brand { display: flex; flex-direction: column; text-decoration: none; line-height: 1.2; margin-right: 8px; }
  .brand .name { font-family: var(--f-display); font-weight: 500; font-size: 16px; color: var(--primary-text); white-space: nowrap; }
  .brand .sub { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .tabs { position: relative; display: flex; height: 100%; min-width: 0; overflow-x: auto; scrollbar-width: none; }
  .tabs::-webkit-scrollbar { display: none; }
  .tabs a { display: flex; align-items: center; gap: 8px; padding: 0 12px; color: var(--muted); text-decoration: none; font-size: 14px; white-space: nowrap; transition: color var(--t-fast); }
  .tabs a:hover { color: var(--text); }
  .tabs a[aria-current='page'] { color: var(--text); font-weight: 500; }
  .ind { position: absolute; left: 0; bottom: -1px; width: 1px; height: 2px; background: var(--primary); transform-origin: left; opacity: 0; transition: transform var(--t-med) var(--ease-out), opacity var(--t-fast); }
  .ind.show { opacity: 1; }
  .count { font-size: 12px; font-weight: 500; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--warn-soft); color: var(--warn); display: inline-grid; place-items: center; font-variant-numeric: tabular-nums; }
  .search { display: flex; align-items: center; gap: 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 0 8px 0 12px; width: min(280px, 24vw); height: 36px; color: var(--muted); transition: border-color var(--t-fast); }
  .search:focus-within { border-color: var(--primary); }
  .search input { border: 0; background: none; outline: none; padding: 0; font-size: 14px; width: 100%; min-width: 0; color: var(--text); }
  .search kbd { font-family: var(--f-mono); font-size: 12px; line-height: 18px; border: 1px solid var(--border); border-radius: 4px; padding: 0 6px; }
  .pill { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--border); background: var(--surface); border-radius: 16px; height: 32px; padding: 0 12px 0 8px; font-size: 13px; color: var(--muted); white-space: nowrap; animation: fade-up var(--t-med) var(--ease-out); }
  .acct { position: relative; }
  .avatar { background: var(--subtle); color: var(--text); font-weight: 500; font-family: var(--f-display); }
  .backdrop { position: fixed; inset: 0; background: transparent; border: 0; z-index: 1; cursor: default; }
  .menu { position: absolute; right: 0; top: calc(100% + 8px); width: 264px; padding: 16px; display: flex; flex-direction: column; gap: 12px; z-index: 2; box-shadow: var(--shadow); }
  .who { display: flex; flex-direction: column; }
  .mlink { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin: 0 -4px; border-radius: 8px; color: var(--text); text-decoration: none; font-size: 14px; }
  .mlink:hover { background: var(--subtle); }
  .all { font-size: 13px; padding: 4px 0; align-self: center; }
  .who small { font-size: 12px; overflow-wrap: anywhere; }
  @media (max-width: 1100px) { .brand .sub { display: none; } .search kbd { display: none; } }
  @media (max-width: 960px) { .search { display: none; } .up span { display: none; } .up { padding: 0 12px; } }
</style>
