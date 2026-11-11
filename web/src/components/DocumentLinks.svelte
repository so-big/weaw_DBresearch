<script>
  // Every active share link on one document, for its uploader and admins (colleagues' links included).
  import { get, errorText } from '../lib/api.js';
  import ShareList from './ShareList.svelte';

  let { id, refresh = 0 } = $props(); // bump `refresh` to reload (e.g. after a link is created)

  let links = $state(null);
  let error = $state('');

  async function load() {
    try {
      links = await get(`/documents/${id}/shares`);
      error = '';
    } catch (err) {
      error = errorText(err);
    }
  }
  $effect(() => {
    refresh;
    load();
  });
</script>

<section class="card pad stack">
  <h3>ลิงก์แชร์ที่ใช้งานอยู่</h3>
  {#if error}
    <div class="notice bad">{error}</div>
  {:else if links && !links.length}
    <p class="muted">ยังไม่มีลิงก์ที่ใช้งานอยู่</p>
  {:else}
    <ShareList {links} onchange={load} byDoc />
  {/if}
</section>
