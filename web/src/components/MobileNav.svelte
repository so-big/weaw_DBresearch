<script>
  // Phone layout: slim top bar (brand + upload) and a bottom bar with a raised search button.
  import Icon from './Icon.svelte';
  import { route, navigate } from '../lib/router.svelte.js';
  import { review, ui } from '../lib/state.svelte.js';
  import { openUpload, busyCount } from '../lib/uploads.svelte.js';

  const on = (prefix) => route.path === prefix || route.path.startsWith(prefix + '/');

  function search() {
    if (route.path !== '/documents') navigate('/documents');
    ui.searchFocus++;
  }
</script>

<header class="mtop">
  <div class="strip"></div>
  <div class="bar">
    <a class="brand" href="/documents">คลังเอกสารวิจัย</a>
    <button class="up" onclick={openUpload}>
      {#if busyCount() > 0}<span class="spin"></span>{busyCount()}{:else}<Icon name="plus" size={16} stroke={2.2} />อัปโหลด{/if}
    </button>
  </div>
</header>

<nav class="bottom" aria-label="เมนูหลัก">
  <a href="/documents" aria-current={on('/documents') ? 'page' : undefined}><Icon name="doc" size={22} />เอกสาร</a>
  <a href="/review" aria-current={on('/review') ? 'page' : undefined}>
    <Icon name="check" size={22} />รอตรวจ
    {#if review.count}<span class="count">{review.count}</span>{/if}
  </a>
  <button class="fab" onclick={search} aria-label="ค้นหา">
    <span class="circle"><Icon name="search" size={26} stroke={2.3} /></span>ค้นหา
  </button>
  <a href="/shares" aria-current={on('/shares') ? 'page' : undefined}><Icon name="link" size={22} />แชร์</a>
  <a href="/account" aria-current={on('/account') || on('/admin') ? 'page' : undefined}><Icon name="user" size={22} />บัญชี</a>
</nav>

<style>
  .mtop { position: sticky; top: 0; z-index: 20; background: var(--surface); border-bottom: 1px solid var(--border); padding-top: env(safe-area-inset-top); }
  .strip { height: 3px; background: var(--primary); }
  .bar { display: flex; align-items: center; justify-content: space-between; height: 50px; padding: 0 max(14px, env(safe-area-inset-right)) 0 max(14px, env(safe-area-inset-left)); }
  .brand { font-family: var(--f-display); font-weight: 600; font-size: 17px; color: var(--primary-text); text-decoration: none; }
  .up { display: inline-flex; align-items: center; gap: 6px; border: 0; background: var(--primary-soft); color: var(--primary-text); border-radius: 10px; padding: 6px 12px; font-size: 14px; font-weight: 600; min-height: 36px; }

  .bottom {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 20;
    display: grid; grid-template-columns: repeat(5, 1fr); align-items: end;
    height: calc(var(--bottom-h) + env(safe-area-inset-bottom));
    padding: 0 env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
    background: var(--surface); border-top: 1px solid var(--border);
  }
  .bottom a, .fab {
    position: relative; display: flex; flex-direction: column; align-items: center; gap: 2px;
    padding: 8px 0 9px; font-size: 11px; color: var(--muted); text-decoration: none;
    border: 0; background: none; transition: color var(--t-fast);
  }
  .bottom a[aria-current='page'] { color: var(--primary-text); font-weight: 600; }
  .count { position: absolute; top: 3px; left: calc(50% + 6px); font-size: 10px; font-weight: 600; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 999px; background: var(--primary); color: var(--on-primary); display: grid; place-items: center; }
  .fab { color: var(--primary-text); font-weight: 600; }
  .circle {
    width: 58px; height: 58px; margin-top: -26px; border-radius: 50%;
    background: var(--primary); color: var(--on-primary); display: grid; place-items: center;
    box-shadow: 0 8px 18px -6px rgba(139, 21, 56, 0.6), 0 0 0 5px var(--surface);
    transition: transform var(--t-fast) var(--ease-out);
  }
  .fab:active .circle { transform: scale(0.93); }
</style>
