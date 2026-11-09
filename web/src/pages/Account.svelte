<script>
  // Phone "บัญชี" tab: who am I, overview, my bin, admin entry, theme, log out.
  import Icon from '../components/Icon.svelte';
  import { session, isAdmin, theme, setTheme } from '../lib/state.svelte.js';
  import { logout } from '../lib/auth.js';
  import Modal from '../components/Modal.svelte';

  let askAll = $state(false);
</script>

<div class="page">
  <section class="card pad who">
    <span class="avatar">{session.user?.display_name?.slice(0, 1)}</span>
    <div>
      <h2>{session.user?.display_name}</h2>
      <p class="muted">{session.user?.email} · {isAdmin() ? 'ผู้ดูแลระบบ' : 'ผู้ใช้'}</p>
    </div>
  </section>

  <nav class="card links">
    <a class="rowlink" href="/overview"><Icon name="chart" /><span>ภาพรวม</span><Icon name="chevron" size={18} /></a>
    <a class="rowlink" href="/trash"><Icon name="trash" /><span>ถังขยะของฉัน</span><Icon name="chevron" size={18} /></a>
    {#if isAdmin()}
      <a class="rowlink" href="/admin"><Icon name="shield" /><span>ผู้ดูแลระบบ</span><Icon name="chevron" size={18} /></a>
    {/if}
  </nav>

  <section class="card pad stack">
    <span class="label">ธีม</span>
    <div class="seg">
      {#each [['system', 'ตามเครื่อง'], ['light', 'สว่าง'], ['dark', 'มืด']] as [v, l] (v)}
        <button aria-pressed={theme.value === v} onclick={() => setTheme(v)}>{l}</button>
      {/each}
    </div>
  </section>

  <button class="btn ghost big" onclick={() => logout()}><Icon name="logout" />ออกจากระบบ</button>
  <button class="link-btn all" onclick={() => (askAll = true)}>ออกจากระบบทุกอุปกรณ์</button>
</div>

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
  .page { max-width: 560px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
  .who { display: flex; gap: 14px; align-items: center; }
  .who p { font-size: 13px; overflow-wrap: anywhere; }
  .avatar { width: 48px; height: 48px; border-radius: 50%; background: var(--primary-soft); color: var(--primary-text); display: grid; place-items: center; font-family: var(--f-display); font-size: 20px; flex: none; }
  .links { overflow: hidden; }
  .rowlink { display: flex; align-items: center; gap: 12px; padding: 14px 16px; min-height: 52px; color: var(--text); text-decoration: none; border-top: 1px solid var(--border); }
  .rowlink:first-child { border-top: 0; }
  .rowlink:active { background: var(--subtle); }
  .rowlink span { flex: 1; font-weight: 500; }
  .all { align-self: center; padding: 8px; }
</style>
