<script>
  // Admin area: the only place with a side menu (many sub-pages). Phones get scrollable chips.
  import { isAdmin, screen, access, refreshAccessRequests } from '../../lib/state.svelte.js';
  import Users from './Users.svelte';
  import AllShares from './AllShares.svelte';
  import Trash from './Trash.svelte';
  import Categories from './Categories.svelte';
  import Audit from './Audit.svelte';
  import Settings from './Settings.svelte';
  import Icon from '../../components/Icon.svelte';

  let { section } = $props();
  const SECTIONS = [
    { key: 'users', label: 'ผู้ใช้', icon: 'user', C: Users },
    { key: 'shares', label: 'ลิงก์แชร์ทั้งหมด', icon: 'link', C: AllShares },
    { key: 'trash', label: 'ถังขยะ', icon: 'trash', C: Trash },
    { key: 'categories', label: 'หมวดหมู่', icon: 'archive', C: Categories },
    { key: 'audit', label: 'บันทึกการใช้งาน', icon: 'clock', C: Audit },
    { key: 'settings', label: 'ตั้งค่า', icon: 'shield', C: Settings },
  ];
  refreshAccessRequests();
  const current = $derived(SECTIONS.find((s) => s.key === section) || SECTIONS[0]);
</script>

{#if !isAdmin()}
  <div class="notice warn">หน้านี้สำหรับผู้ดูแลระบบเท่านั้น</div>
{:else}
  <div class="admin" class:wide={screen.wide}>
    <nav class="sub" aria-label="เมนูผู้ดูแลระบบ">
      {#if screen.wide}<span class="cap">ผู้ดูแลระบบ</span>{/if}
      {#each SECTIONS as s (s.key)}
        <a href="/admin/{s.key}" class:on={current.key === s.key} aria-current={current.key === s.key ? 'page' : undefined}>{#if screen.wide}<Icon name={s.icon} size={18} />{/if}<span>{s.label}</span>{#if s.key === 'users' && access.requests}<span class="count" aria-label="{access.requests} คำขอรออนุมัติ">{access.requests}</span>{/if}</a>
      {/each}
    </nav>
    <div class="content">
      {#key current.key}
        <div class="enter"><current.C /></div>
      {/key}
    </div>
  </div>
{/if}

<style>
  .admin { display: flex; flex-direction: column; gap: 16px; }
  .admin.wide { display: grid; grid-template-columns: 224px minmax(0, 1fr); gap: 24px; align-items: start; }
  .sub { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; margin: 0 -16px; padding: 0 16px 2px; }
  .sub::-webkit-scrollbar { display: none; }
  .sub a { flex: none; display: flex; align-items: center; height: 32px; padding: 0 12px; border-radius: 16px; border: 1px solid var(--border); background: var(--surface); color: var(--text); text-decoration: none; font-size: 13px; white-space: nowrap; }
  .sub a.on { background: var(--primary-soft); border-color: var(--primary); color: var(--primary-text); }
  .cap { font-size: 12px; color: var(--muted); padding: 4px 12px 8px; }
  .wide .sub { position: sticky; top: calc(var(--header-h) + 24px); flex-direction: column; gap: 2px; margin: 0; padding: 0; overflow: visible; }
  .wide .sub a { gap: 12px; height: 36px; border: 0; border-radius: 8px; font-size: 14px; background: none; color: var(--muted); transition: background var(--t-fast), color var(--t-fast); }
  .wide .sub a span { flex: 1; }
  .wide .sub a:hover { background: var(--subtle); color: var(--text); }
  .wide .sub a.on { background: var(--surface); color: var(--text); font-weight: 500; box-shadow: inset 0 0 0 1px var(--border), inset 2px 0 0 var(--primary); }
  .content { min-width: 0; }
  .count { display: inline-grid; place-items: center; margin-left: 8px; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--warn-soft); color: var(--warn); font-size: 12px; font-weight: 500; }
</style>
