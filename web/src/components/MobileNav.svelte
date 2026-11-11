<script>
  // Phone layout: top bar (brand, search, account) and a bottom bar with a raised upload button.
  import Icon from './Icon.svelte';
  import { route, navigate } from '../lib/router.svelte.js';
  import { review, ui, session } from '../lib/state.svelte.js';
  import { openUpload, busyCount } from '../lib/uploads.svelte.js';

  const on = (prefix) => route.path === prefix || route.path.startsWith(prefix + '/');
  const account = $derived(on('/account') || on('/admin') || on('/overview') || on('/trash') || on('/shares'));

  // Search the section you are in (contracts unless in proposal grants).
  function search() {
    const list = route.path.startsWith('/proposals') ? '/proposals' : '/documents';
    if (route.path !== list) navigate(list);
    ui.searchFocus++;
  }
</script>

<header class="mtop">
  <div class="strip"></div>
  <div class="bar">
    <a class="brand" href="/">คลังเอกสารวิจัย</a>
    <span class="spacer"></span>
    <button class="icon-btn" onclick={search} aria-label="ค้นหา"><Icon name="search" size={20} /></button>
    <a class="avatar" href="/account" aria-label="บัญชี" aria-current={account ? 'page' : undefined}>
      {session.user?.display_name?.slice(0, 1) || '?'}
    </a>
  </div>
</header>

<nav class="bottom" class:away={ui.bar} aria-label="เมนูหลัก" inert={ui.bar}>
  <a href="/" aria-current={route.path === '/' ? 'page' : undefined}><Icon name="home" size={22} />หน้าแรก</a>
  <a href="/documents" aria-current={on('/documents') ? 'page' : undefined}><Icon name="doc" size={22} />สัญญา</a>
  <button class="fab" onclick={openUpload} aria-label={busyCount() ? `กำลังอัปโหลด ${busyCount()} ไฟล์` : 'อัปโหลด'}>
    <span class="circle">
      {#if busyCount() > 0}<span class="busy num">{busyCount()}</span>{:else}<Icon name="upload" size={24} stroke={2} />{/if}
    </span>
    อัปโหลด
  </button>
  <a href="/proposals" aria-current={on('/proposals') ? 'page' : undefined}><Icon name="bulb" size={22} />ทุนพัฒนา</a>
  <a href="/review" aria-current={on('/review') ? 'page' : undefined}>
    <Icon name="check" size={22} />รอตรวจ
    {#if review.count}<span class="count num">{review.count}</span>{/if}
  </a>
</nav>

<style>
  .mtop { position: sticky; top: 0; z-index: 20; background: var(--surface); border-bottom: 1px solid var(--border); padding-top: env(safe-area-inset-top); }
  .strip { height: 3px; background: var(--primary); }
  .bar { display: flex; align-items: center; gap: 4px; height: 52px; padding: 0 max(12px, env(safe-area-inset-right)) 0 max(16px, env(safe-area-inset-left)); }
  .brand { font-family: var(--f-display); font-weight: 500; font-size: 17px; color: var(--primary-text); text-decoration: none; }
  .icon-btn { width: 40px; height: 40px; color: var(--text); }
  .avatar {
    width: 32px; height: 32px; margin-left: 4px; border-radius: 50%; display: grid; place-items: center;
    background: var(--subtle); color: var(--text); font-family: var(--f-display); font-size: 14px; text-decoration: none;
    transition: background var(--t-fast);
  }
  .avatar[aria-current='page'] { background: var(--primary-soft); color: var(--primary-text); box-shadow: 0 0 0 2px var(--primary); }

  .bottom {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 20;
    display: grid; grid-template-columns: repeat(5, 1fr); align-items: end;
    height: calc(var(--bottom-h) + env(safe-area-inset-bottom));
    padding: 0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
    background: var(--surface); border-top: 1px solid var(--border);
    transition: transform var(--t-med) var(--ease-out);
  }
  /* select mode: its action bar takes this place */
  .bottom.away { transform: translateY(calc(100% + 40px)); }
  .bottom a, .fab {
    position: relative; display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: 8px 0; font-size: 11px; color: var(--muted); text-decoration: none;
    border: 0; background: none; transition: color var(--t-fast);
  }
  .bottom a[aria-current='page'] { color: var(--primary-text); font-weight: 500; }
  .count { position: absolute; top: 4px; left: calc(50% + 6px); font-size: 11px; font-weight: 500; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px; background: var(--warn); color: var(--surface); display: grid; place-items: center; }
  .fab { color: var(--text); }
  .circle {
    width: 56px; height: 56px; margin-top: -24px; border-radius: 50%;
    background: var(--primary); color: var(--on-primary); display: grid; place-items: center;
    box-shadow: 0 0 0 4px var(--surface), 0 4px 12px -4px rgba(0, 0, 0, 0.3);
    transition: transform var(--t-fast) var(--ease-out);
  }
  .fab:active .circle { transform: scale(0.94); }
  .busy { font-family: var(--f-display); font-size: 20px; }
</style>
