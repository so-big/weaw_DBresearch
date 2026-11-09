<script>
  // List of share links with revoke / new password / access log. Used by "my links" and admin.
  import { get, post, del, errorText } from '../lib/api.js';
  import { toast } from '../lib/state.svelte.js';
  import { LINK_STATE, thDateTime, timeLeft } from '../lib/format.js';
  import Icon from './Icon.svelte';
  import Modal from './Modal.svelte';

  let { links, onchange } = $props();

  let revoking = $state(null);
  let logFor = $state(null);
  let log = $state(null);
  let newPass = $state(null);

  const EVENT = { open: 'เปิดลิงก์', view: 'เปิดดูไฟล์', download: 'ดาวน์โหลด', bad_password: 'รหัสผ่านผิด', denied: 'ถูกปฏิเสธ' };

  async function revoke() {
    try {
      await del(`/shares/${revoking.id}`);
      toast('ยกเลิกลิงก์แล้ว');
      onchange?.();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
    revoking = null;
  }
  async function showLog(link) {
    logFor = link;
    log = null;
    try {
      log = await get(`/shares/${link.id}/log`);
    } catch (err) {
      toast(errorText(err), 'bad');
      logFor = null;
    }
  }
  async function regenerate(link) {
    try {
      const res = await post(`/shares/${link.id}/password`);
      newPass = { link, password: res.password };
      onchange?.();
    } catch (err) {
      toast(errorText(err), 'bad');
    }
  }
  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast('คัดลอกแล้ว');
    } catch {
      toast('คัดลอกไม่ได้ ให้เลือกข้อความแล้วคัดลอกเอง', 'bad');
    }
  }
</script>

{#if links === null}
  <div class="card pad"><div class="skel" style="width:60%"></div></div>
{:else if !links.length}
  <div class="card empty"><Icon name="link" size={30} /><p>ยังไม่มีลิงก์</p></div>
{:else}
  <div class="list">
    {#each links as l (l.id)}
      <div class="card item enter" class:inactive={l.state !== 'active'}>
        <div class="top">
          <a class="t" href="/documents/{l.document_id}">{l.document_title}</a>
          <span class="badge {l.state === 'active' ? 'ready' : 'neutral'}">{LINK_STATE[l.state] || l.state}</span>
        </div>
        <div class="meta">
          <span class="acc">{#if l.access === 'password'}<Icon name="lock" size={13} />ต้องใช้รหัสผ่าน{:else}ทุกคนที่มีลิงก์{/if}</span>
          <span>เปิดไฟล์แล้ว {l.download_count}{l.max_downloads ? `/${l.max_downloads}` : ''} ครั้ง</span>
          <span title={thDateTime(l.expires_at)}>{l.state === 'active' ? `หมดอายุ${timeLeft(l.expires_at)}` : `หมดอายุ ${thDateTime(l.expires_at)}`}</span>
          <span>สร้าง {thDateTime(l.created_at)}</span>
          {#if l.note}<span class="note">“{l.note}”</span>{/if}
        </div>
        <div class="acts">
          <button class="link-btn" onclick={() => showLog(l)}>ประวัติการเข้าถึง</button>
          {#if l.state === 'active' || l.state === 'locked'}
            {#if l.access === 'password'}<button class="link-btn" onclick={() => regenerate(l)}>ตั้งรหัสผ่านใหม่</button>{/if}
            <button class="link-btn danger" onclick={() => (revoking = l)}>ยกเลิกลิงก์</button>
          {/if}
        </div>
      </div>
    {/each}
  </div>
{/if}

{#if revoking}
  <Modal title="ยกเลิกลิงก์นี้?" onclose={() => (revoking = null)}>
    <p>คนที่มีลิงก์ของ “{revoking.document_title}” จะเปิดไม่ได้อีกทันที ย้อนกลับไม่ได้</p>
    {#snippet footer()}
      <button class="btn ghost" onclick={() => (revoking = null)}>ไม่ใช่ตอนนี้</button>
      <button class="btn danger" onclick={revoke}>ยกเลิกลิงก์</button>
    {/snippet}
  </Modal>
{/if}

{#if newPass}
  <Modal title="รหัสผ่านใหม่" onclose={() => (newPass = null)}>
    <div class="notice warn">รหัสนี้แสดงครั้งเดียว รหัสเดิมใช้ไม่ได้แล้ว</div>
    <div class="copyrow">
      <input id="new-pass" class="input mono" readonly value={newPass.password} onfocus={(e) => e.currentTarget.select()} />
      <button class="btn" onclick={() => copy(newPass.password)}><Icon name="copy" size={16} />คัดลอก</button>
    </div>
    {#snippet footer()}<button class="btn" onclick={() => (newPass = null)}>เสร็จแล้ว</button>{/snippet}
  </Modal>
{/if}

{#if logFor}
  <Modal title="ประวัติการเข้าถึง" onclose={() => (logFor = null)} width={620}>
    <p class="muted">{logFor.document_title}</p>
    {#if log === null}
      <div class="skel" style="width:70%"></div>
    {:else if !log.length}
      <p class="muted">ยังไม่มีใครเปิดลิงก์นี้</p>
    {:else}
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>เวลา</th><th>ผู้เข้าถึง</th><th>เหตุการณ์</th><th>IP</th></tr></thead>
          <tbody>
            {#each log as e, i (i)}
              <tr><td class="num">{thDateTime(e.at)}</td><td>{#if e.user_name}<span class="who"><Icon name="user" size={13} />{e.user_name}</span>{:else}<span class="muted">บุคคลภายนอก</span>{/if}</td><td>{EVENT[e.event] || e.event}{e.reason ? ` (${e.reason})` : ''}</td><td class="mono">{e.ip || '–'}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Modal>
{/if}

<style>
  .list { display: flex; flex-direction: column; gap: 10px; }
  .item { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; }
  .item.inactive { opacity: 0.7; }
  .top { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
  .t { font-weight: 500; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
  .t:hover { color: var(--primary-text); }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; color: var(--muted); }
  .note { font-style: italic; }
  .acc { display: inline-flex; align-items: center; gap: 4px; }
  .who { display: inline-flex; align-items: center; gap: 5px; font-weight: 500; white-space: nowrap; }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-left: -4px; }
  .danger { color: var(--bad); }
  .empty { padding: 36px 16px; display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--muted); }
  .copyrow { display: flex; gap: 8px; }
  .copyrow input { flex: 1; min-width: 0; }
</style>
