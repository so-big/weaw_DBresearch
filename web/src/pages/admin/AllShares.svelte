<script>
  import { get, errorText } from '../../lib/api.js';
  import ShareList from '../../components/ShareList.svelte';

  let state = $state('active');
  let links = $state(null);
  let error = $state('');

  async function load() {
    try {
      links = await get('/admin/shares', { state });
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    state;
    load();
  });
</script>

<div class="stack">
  <div class="row">
    <h1>ลิงก์แชร์ทั้งหมด</h1>
    <span class="spacer"></span>
    <div class="seg">
      <button aria-pressed={state === 'active'} onclick={() => (state = 'active')}>ใช้งานอยู่</button>
      <button aria-pressed={state === 'all'} onclick={() => (state = 'all')}>ทั้งหมด</button>
    </div>
  </div>
  {#if error}<div class="notice bad">{error}</div>{/if}
  <ShareList {links} onchange={load} />
</div>
