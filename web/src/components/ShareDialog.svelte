<script>
  // Create a share link. The link (and password) are shown once: the server keeps only hashes.
  import Modal from './Modal.svelte';
  import Icon from './Icon.svelte';
  import { post, errorText } from '../lib/api.js';
  import { toast, isAdmin } from '../lib/state.svelte.js';
  import { thDateTime } from '../lib/format.js';
  import qrcode from 'qrcode-generator';

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
  let limit = $state('');
  let note = $state('');
  let busy = $state(false);
  let error = $state('');
  let created = $state(null);
  let pin = $state(false); // pin to the newest version instead of "always the latest"
  let showQr = $state(false);

  // versions[0] is the newest; the choice only exists when there is more than one
  const latestNo = $derived(doc.versions?.[0]?.version_no);
  const hasVersions = $derived((doc.versions?.length || 0) > 1);

  const url = $derived(created ? `${location.origin}${created.path}` : '');

  async function create() {
    busy = true;
    error = '';
    try {
      created = await post(`/documents/${doc.id}/shares`, {
        access,
        ttl_hours: ttl,
        max_downloads: limit ? Number(limit) : null,
        version_no: hasVersions && pin ? latestNo : null,
        note: note.trim() || null,
      });
      oncreated?.();
    } catch (err) {
      error = errorText(err);
    } finally {
      busy = false;
    }
  }

  // QR of the link only (never the password): one dark path on a white quiet zone.
  const qr = $derived.by(() => {
    if (!url) return null;
    const code = qrcode(0, 'M');
    code.addData(url);
    code.make();
    const n = code.getModuleCount();
    let d = '';
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (code.isDark(r, c)) d += `M${c + 4} ${r + 4}h1v1h-1z`;
    return { size: n + 8, d };
  });

  const message = $derived(
    created
      ? [
          `เอกสาร: ${doc.title}`,
          `ลิงก์: ${url}`,
          `ใช้ได้ถึง ${thDateTime(created.expires_at)}`,
          ...(created.password ? [`รหัสผ่าน: ${created.password}`] : []),
        ].join('\n')
      : '',
  );

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
    {#if hasVersions}
      <div class="field">
        <span>เวอร์ชันที่ผู้รับเปิดได้</span>
        <div class="seg">
          <button aria-pressed={!pin} onclick={() => (pin = false)}>เวอร์ชันล่าสุดเสมอ</button>
          <button aria-pressed={pin} onclick={() => (pin = true)}>เฉพาะเวอร์ชันนี้ (v{latestNo})</button>
        </div>
      </div>
    {/if}
    <div class="field">
      <span>ใช้ได้นาน</span>
      <div class="seg">
        {#each TTL as [h, l] (h)}<button aria-pressed={ttl === h} onclick={() => (ttl = h)}>{l}</button>{/each}
      </div>
    </div>
    <label class="field">
      <span>จำกัดจำนวนครั้งที่เปิดไฟล์</span>
      <input id="share-limit" type="number" min="1" max="1000" inputmode="numeric" bind:value={limit} placeholder="ไม่จำกัด" />
      <small>เปิดดูหรือดาวน์โหลดนับเป็น 1 ครั้ง ผู้รับเปิดดู บันทึก และพิมพ์เอกสารได้</small>
    </label>
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
    <div class="field">
      <button class="btn" onclick={() => copy(message, 'ข้อความ')}><Icon name="copy" size={16} />คัดลอกข้อความพร้อมลิงก์</button>
      <small>ข้อความพร้อมส่งทาง LINE หรืออีเมล{created.password ? ' รวมรหัสผ่านไว้ด้วย ถ้าจะส่งรหัสผ่านแยกให้คัดลอกรหัสผ่านด้านบนแทน' : ''}</small>
    </div>
    <div class="field">
      <button class="btn ghost" aria-expanded={showQr} onclick={() => (showQr = !showQr)}>{showQr ? 'ซ่อน QR' : 'แสดง QR'}</button>
      {#if showQr && qr}
        <div class="qr">
          <svg viewBox="0 0 {qr.size} {qr.size}" role="img" aria-label="คิวอาร์โค้ดของลิงก์ (ไม่รวมรหัสผ่าน)" shape-rendering="crispEdges">
            <rect width={qr.size} height={qr.size} fill="#fff" />
            <path d={qr.d} fill="#000" />
          </svg>
          <small>สแกนเพื่อเปิดลิงก์ (ไม่รวมรหัสผ่าน)</small>
        </div>
      {/if}
    </div>
    <p class="muted small">หมดอายุ {thDateTime(created.expires_at)}{created.max_downloads ? ` · เปิดไฟล์ได้ ${created.max_downloads} ครั้ง` : ''}</p>
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
  .qr { display: flex; flex-direction: column; align-items: center; gap: 6px; animation: qr-in 0.18s ease-out; }
  .qr svg { width: 220px; height: 220px; background: #fff; border-radius: 6px; } /* white even in dark mode */
  @keyframes qr-in { from { opacity: 0; } to { opacity: 1; } }
  @media (prefers-reduced-motion: reduce) { .qr { animation: none; } }
</style>
