<script>
  // Create a share link. The link (and password) are shown once: the server keeps only hashes.
  import Modal from './Modal.svelte';
  import Icon from './Icon.svelte';
  import { post, errorText } from '../lib/api.js';
  import { toast, isAdmin } from '../lib/state.svelte.js';
  import { thDateTime } from '../lib/format.js';

  let { doc, onclose, oncreated } = $props();

  const TTL = [
    [1, '1 ชั่วโมง'],
    [24, '1 วัน'],
    [72, '3 วัน'],
    [168, '7 วัน'],
    ...(isAdmin() ? [[720, '30 วัน']] : []),
  ];
  let access = $state('public');
  let ttl = $state(24);
  let allowDownload = $state(true);
  let limit = $state('');
  let note = $state('');
  let busy = $state(false);
  let error = $state('');
  let created = $state(null);

  const url = $derived(created ? `${location.origin}${created.path}` : '');

  async function create() {
    busy = true;
    error = '';
    try {
      created = await post(`/documents/${doc.id}/shares`, {
        access,
        ttl_hours: ttl,
        allow_download: allowDownload,
        max_downloads: limit ? Number(limit) : null,
        note: note.trim() || null,
      });
      oncreated?.();
    } catch (err) {
      error = errorText(err);
    } finally {
      busy = false;
    }
  }

  async function copy(text, what) {
    try {
      await navigator.clipboard.writeText(text);
      toast(`คัดลอก${what}แล้ว`);
    } catch {
      toast('คัดลอกไม่ได้ ให้กดค้างที่ข้อความแล้วเลือกคัดลอก', 'bad');
    }
  }
</script>

<Modal title={created ? 'สร้างลิงก์แล้ว' : 'แชร์เอกสาร'} {onclose} width={500}>
  {#if !created}
    <p class="muted doc">{doc.title}</p>
    <div class="field">
      <span>ใครเปิดได้</span>
      <div class="seg">
        <button aria-pressed={access === 'public'} onclick={() => (access = 'public')}>ทุกคนที่มีลิงก์</button>
        <button aria-pressed={access === 'password'} onclick={() => (access = 'password')}><Icon name="lock" size={14} /> ต้องใส่รหัสผ่าน</button>
      </div>
    </div>
    <div class="field">
      <span>ใช้ได้นาน</span>
      <div class="seg">
        {#each TTL as [h, l] (h)}<button aria-pressed={ttl === h} onclick={() => (ttl = h)}>{l}</button>{/each}
      </div>
    </div>
    <label class="check"><input id="share-dl" type="checkbox" bind:checked={allowDownload} />อนุญาตให้ดาวน์โหลด (ไม่เลือก = เปิดดูได้อย่างเดียว)</label>
    {#if allowDownload}
      <label class="field">
        <span>จำกัดจำนวนครั้งที่ดาวน์โหลด</span>
        <input id="share-limit" type="number" min="1" max="1000" inputmode="numeric" bind:value={limit} placeholder="ไม่จำกัด" />
      </label>
    {/if}
    <label class="field">
      <span>บันทึกถึงตัวเอง</span>
      <input id="share-note" bind:value={note} maxlength="300" placeholder="เช่น ส่งให้ฝ่ายการเงิน" />
    </label>
    {#if error}<div class="notice bad">{error}</div>{/if}
  {:else}
    <div class="notice warn"><Icon name="info" size={18} />ลิงก์{created.password ? 'และรหัสผ่าน' : ''}จะแสดงครั้งเดียวเท่านั้น คัดลอกเก็บไว้ก่อนปิดหน้าต่าง</div>
    <div class="field">
      <span>ลิงก์</span>
      <div class="copyrow">
        <input id="share-url" class="input mono" readonly value={url} onfocus={(e) => e.currentTarget.select()} />
        <button class="btn" onclick={() => copy(url, 'ลิงก์')}><Icon name="copy" size={16} />คัดลอก</button>
      </div>
    </div>
    {#if created.password}
      <div class="field">
        <span>รหัสผ่าน (ส่งแยกจากลิงก์)</span>
        <div class="copyrow">
          <input id="share-pass" class="input mono" readonly value={created.password} onfocus={(e) => e.currentTarget.select()} />
          <button class="btn ghost" onclick={() => copy(created.password, 'รหัสผ่าน')}><Icon name="copy" size={16} />คัดลอก</button>
        </div>
      </div>
    {/if}
    <p class="muted small">หมดอายุ {thDateTime(created.expires_at)}{created.max_downloads ? ` · ดาวน์โหลดได้ ${created.max_downloads} ครั้ง` : ''}{created.allow_download ? '' : ' · เปิดดูอย่างเดียว'}</p>
  {/if}

  {#snippet footer()}
    {#if !created}
      <button class="btn ghost" onclick={onclose}>ยกเลิก</button>
      <button class="btn" onclick={create} disabled={busy}>{busy ? 'กำลังสร้าง…' : 'สร้างลิงก์'}</button>
    {:else}
      <button class="btn" onclick={onclose}>เสร็จแล้ว</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .doc { font-size: 14px; overflow-wrap: anywhere; }
  .copyrow { display: flex; gap: 8px; }
  .copyrow input { flex: 1; min-width: 0; font-size: 13px; }
  .small { font-size: 13px; }
</style>
