<script>
  // Phone "บัญชี" tab: who am I, theme, admin entry, log out.
  import Icon from '../components/Icon.svelte';
  import { session, isAdmin, theme, setTheme } from '../lib/state.svelte.js';
  import { logout } from '../lib/auth.js';
</script>

<div class="page">
  <section class="card pad who">
    <span class="avatar">{session.user?.display_name?.slice(0, 1)}</span>
    <div>
      <h2>{session.user?.display_name}</h2>
      <p class="muted">{session.user?.email} · {isAdmin() ? 'ผู้ดูแลระบบ' : 'ผู้ใช้'}</p>
    </div>
  </section>

  {#if isAdmin()}
    <a class="card pad rowlink" href="/admin"><Icon name="shield" /><span>ผู้ดูแลระบบ</span><Icon name="chevron" size={18} /></a>
  {/if}

  <section class="card pad stack">
    <span class="label">ธีม</span>
    <div class="seg">
      {#each [['system', 'ตามเครื่อง'], ['light', 'สว่าง'], ['dark', 'มืด']] as [v, l] (v)}
        <button aria-pressed={theme.value === v} onclick={() => setTheme(v)}>{l}</button>
      {/each}
    </div>
  </section>

  <button class="btn ghost big" onclick={logout}><Icon name="logout" />ออกจากระบบ</button>
</div>

<style>
  .page { max-width: 560px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
  .who { display: flex; gap: 14px; align-items: center; }
  .who p { font-size: 13px; overflow-wrap: anywhere; }
  .avatar { width: 48px; height: 48px; border-radius: 50%; background: var(--primary-soft); color: var(--primary-text); display: grid; place-items: center; font-family: var(--f-display); font-size: 20px; flex: none; }
  .rowlink { display: flex; align-items: center; gap: 12px; color: var(--text); text-decoration: none; }
  .rowlink span { flex: 1; font-weight: 500; }
</style>
