<script>
  // Admin area: the only place with a side menu (many sub-pages). Phones get scrollable chips.
  import { isAdmin, screen, access, refreshAccessRequests } from '../../lib/state.svelte.js';
  import Users from './Users.svelte';
  import AllShares from './AllShares.svelte';
  import Trash from './Trash.svelte';
  import Categories from './Categories.svelte';
  import Audit from './Audit.svelte';
  import Settings from './Settings.svelte';

  let { section } = $props();
  const SECTIONS = [
    { key: 'users', label: 'ผู้ใช้', C: Users },
    { key: 'shares', label: 'ลิงก์แชร์ทั้งหมด', C: AllShares },
    { key: 'trash', label: 'ถังขยะ', C: Trash },
    { key: 'categories', label: 'หมวดหมู่', C: Categories },
    { key: 'audit', label: 'บันทึกการใช้งาน', C: Audit },
    { key: 'settings', label: 'ตั้งค่า', C: Settings },
  ];
  refreshAccessRequests();
  const current = $derived(SECTIONS.find((s) => s.key === section) || SECTIONS[0]);
</script>

{#if !isAdmin()}
  <div class="notice warn">หน้านี้สำหรับผู้ดูแลระบบเท่านั้น</div>
{:else}
  <div class="admin" class:wide={screen.wide}>
    <nav class="sub" aria-label="เมนูผู้ดูแลระบบ">
      {#each SECTIONS as s (s.key)}
        <a href="/admin/{s.key}" class:on={current.key === s.key} aria-current={current.key === s.key ? 'page' : undefined}>{s.label}{#if s.key === 'users' && access.requests}<span class="count" aria-label="{access.requests} คำขอรออนุมัติ">{access.requests}</span>{/if}</a>
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
  .admin { display: flex; flex-direction: column; gap: 14px; }
  .admin.wide { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 20px; align-items: start; }
  .sub { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -12px; padding: 0 12px 2px; }
  .sub::-webkit-scrollbar { display: none; }
  .sub a { flex: none; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text); text-decoration: none; font-size: 13.5px; white-space: nowrap; }
  .sub a.on { background: var(--primary-soft); border-color: var(--primary-soft); color: var(--primary-text); font-weight: 600; }
  .wide .sub { position: sticky; top: calc(var(--header-h) + 20px); flex-direction: column; gap: 2px; margin: 0; padding: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .wide .sub a { border: 0; border-radius: 8px; padding: 8px 12px; font-size: 14px; background: none; }
  .wide .sub a:hover { background: var(--subtle); }
  .wide .sub a.on { background: var(--primary-soft); box-shadow: inset 3px 0 0 var(--primary); }
  .content { min-width: 0; }
  .count { display: inline-block; margin-left: 6px; min-width: 20px; padding: 0 6px; border-radius: 999px; background: var(--warn-soft); color: var(--warn); font-size: 12px; font-weight: 600; text-align: center; line-height: 20px; }
</style>
