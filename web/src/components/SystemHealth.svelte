<script>
  // Admin overview, top block: is the server healthy? Worker, job queue, backups, disk,
  // logins, then the smaller facts. Each state shows an icon and a word, never colour alone.
  import { onDestroy } from 'svelte';
  import { get, errorText } from '../lib/api.js';
  import { bytes, thDateTime } from '../lib/format.js';
  import Icon from './Icon.svelte';

  let { links = null, onrefresh = () => {} } = $props();

  let h = $state(null);
  let error = $state('');
  let busy = $state(false);
  let timer;

  async function load() {
    clearTimeout(timer);
    busy = true;
    try {
      h = await get('/admin/health');
      error = '';
    } catch (err) {
      error = errorText(err);
    } finally {
      busy = false;
      timer = setTimeout(load, 30000);
    }
  }
  load();
  onDestroy(() => clearTimeout(timer));

  const MIN = 6e4;
  const HOUR = 36e5;
  const ago = (iso) => {
    if (!iso) return null;
    const ms = Date.now() - new Date(iso);
    if (ms < MIN) return 'เมื่อสักครู่';
    if (ms < HOUR) return `${Math.round(ms / MIN)} นาทีที่แล้ว`;
    if (ms < 48 * HOUR) return `${Math.round(ms / HOUR)} ชม. ที่แล้ว`;
    return `${Math.round(ms / (24 * HOUR))} วันที่แล้ว`;
  };
  const age = (iso) => (iso ? Date.now() - new Date(iso) : Infinity);
  const n = (v) => (v ?? 0).toLocaleString('th-TH');

  const LEVEL = {
    ok: { icon: 'check-only', word: 'ปกติ' },
    warn: { icon: 'warn', word: 'ควรตรวจสอบ' },
    bad: { icon: 'warn', word: 'มีปัญหา' },
    none: { icon: 'info', word: 'ยังไม่มีข้อมูล' },
  };

  const worker = $derived.by(() => {
    if (!h) return null;
    const seen = age(h.worker_seen_at);
    // A long OCR job can hold the worker past its heartbeat, so a running job counts as alive.
    const level = seen < 2 * MIN || h.jobs.running ? 'ok' : seen < 10 * MIN ? 'warn' : 'bad';
    const note = h.worker_seen_at ? `เห็นล่าสุด ${ago(h.worker_seen_at)}` : 'ยังไม่เคยรายงานตัว';
    return { level, value: h.jobs.running ? 'กำลังอ่านเอกสาร' : level === 'ok' ? 'พร้อมทำงาน' : 'ไม่ตอบสนอง', note };
  });
  const queue = $derived.by(() => {
    if (!h) return null;
    const wait = h.oldest_queued_at ? age(h.oldest_queued_at) : 0;
    const level = h.jobs.failed ? 'bad' : wait > 15 * MIN ? 'warn' : 'ok';
    return {
      level,
      value: `${n(h.jobs.queued)} รอ · ${n(h.jobs.running)} ทำอยู่`,
      note: h.jobs.failed ? `ล้มเหลว ${n(h.jobs.failed)} งาน` : `เสร็จ ${n(h.jobs.done_24h)} งานใน 24 ชม.`,
    };
  });
  const backup = $derived.by(() => {
    if (!h) return null;
    if (!h.backup) return { level: 'none', value: 'ยังไม่มีบันทึก', note: 'ตั้งค่า scripts/backup.sh บนเซิร์ฟเวอร์' };
    const okAge = age(h.last_backup_ok_at);
    const level = !h.backup.ok ? 'bad' : okAge > 48 * HOUR ? 'warn' : 'ok';
    return {
      level,
      value: h.last_backup_ok_at ? ago(h.last_backup_ok_at) : 'ยังไม่เคยสำเร็จ',
      note: h.backup.ok ? `สำเร็จ ${thDateTime(h.backup.at)}` : `ครั้งล่าสุดล้มเหลว ${thDateTime(h.backup.at)}`,
    };
  });
  const disk = $derived.by(() => {
    if (!h?.disk) return null;
    const used = h.disk.used / h.disk.total;
    const free = h.disk.free / h.disk.total;
    return { level: free < 0.05 ? 'bad' : free < 0.15 ? 'warn' : 'ok', used, value: `ว่าง ${bytes(h.disk.free)}`, note: `จาก ${bytes(h.disk.total)} · ใช้ไป ${Math.round(used * 100)}%` };
  });
  const logins = $derived.by(() => {
    if (!h) return null;
    const l = h.logins_24h;
    return {
      level: l.blocked ? 'warn' : 'ok',
      value: `${n(l.ok)} สำเร็จ`,
      note: `ผิด ${n(l.failed)} · ถูกบล็อก ${n(l.blocked)}`,
    };
  });
  const tiles = $derived(
    [
      worker && { key: 'worker', label: 'ระบบอ่านเอกสาร', ...worker },
      queue && { key: 'queue', label: 'คิวงาน', ...queue },
      backup && { key: 'backup', label: 'สำรองข้อมูลล่าสุด', ...backup },
      disk && { key: 'disk', label: 'พื้นที่ดิสก์', ...disk },
      logins && { key: 'logins', label: 'เข้าสู่ระบบ 24 ชม.', ...logins },
    ].filter(Boolean),
  );
  const problems = $derived(tiles.filter((t) => t.level === 'bad' || t.level === 'warn').length);
  const overall = $derived(!h ? null : tiles.some((t) => t.level === 'bad') ? 'bad' : problems || h.warnings.length ? 'warn' : 'ok');

  function refresh() {
    load();
    onrefresh();
  }
</script>

<section class="health" aria-labelledby="h-health">
  <div class="head">
    <h2 id="h-health">สถานะเซิร์ฟเวอร์</h2>
    {#if overall}
      <span class="state {overall}"><Icon name={LEVEL[overall].icon} size={16} stroke={2.2} />{overall === 'ok' ? 'ทุกอย่างปกติ' : LEVEL[overall].word}</span>
    {/if}
    <span class="spacer"></span>
    {#if h}<small class="muted">ตรวจเมื่อ {thDateTime(h.checked_at)}</small>{/if}
    <button class="icon-btn" onclick={refresh} disabled={busy} aria-label="ตรวจอีกครั้ง"><Icon name="refresh" size={18} /></button>
  </div>

  {#if error}<div class="notice bad">{error}</div>{/if}
  {#if h?.warnings.length}
    <div class="notice warn"><Icon name="warn" size={18} /><div>{#each h.warnings as w (w)}<div>{w}</div>{/each}</div></div>
  {/if}

  <div class="tiles card">
    {#if !h}
      {#each Array(5) as _, i (i)}<div class="tile"><div class="skel" style="width:50%"></div><div class="skel" style="width:80%;height:20px;margin-top:8px"></div></div>{/each}
    {:else}
      {#each tiles as t (t.key)}
        <div class="tile">
          <span class="label">{t.label}</span>
          <b class="value">{t.value}</b>
          {#if t.key === 'disk'}
            <span class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(t.used * 100)} aria-label="ใช้พื้นที่ดิสก์">
              <span class="fill {t.level}" style="transform: scaleX({t.used})"></span>
            </span>
          {/if}
          <span class="note">{t.note}</span>
          <span class="lvl {t.level}"><Icon name={LEVEL[t.level].icon} size={14} stroke={2.2} />{LEVEL[t.level].word}</span>
        </div>
      {/each}
    {/if}
  </div>

  {#if h}
    <dl class="facts">
      <div><dt>ฐานข้อมูล</dt><dd class="num">{bytes(h.database_bytes)}</dd></div>
      <div><dt>ไฟล์เข้ารหัส</dt><dd class="num">{n(h.files)} ไฟล์ · {bytes(h.file_bytes)}</dd></div>
      <div><dt>อุปกรณ์ที่เข้าระบบอยู่</dt><dd class="num">{n(h.sessions)}</dd></div>
      <div><dt><a href="/admin/users">คำขอเข้าใช้งาน</a></dt><dd class="num" class:hot={h.access_requests}>{n(h.access_requests)}</dd></div>
      <div><dt><a href="/documents?status=failed">อ่านเอกสารไม่สำเร็จ</a></dt><dd class="num">{n(h.documents.ocr_failed)}</dd></div>
      {#if links !== null}<div><dt><a href="/admin/shares">ลิงก์แชร์ที่ใช้งานอยู่</a></dt><dd class="num">{n(links)}</dd></div>{/if}
      <div><dt><a href="/admin/trash">ในถังขยะทั้งระบบ</a></dt><dd class="num">{n(h.documents.in_trash)}</dd></div>
      <div><dt>ระบบเริ่มทำงาน</dt><dd>{ago(h.started_at)}</dd></div>
      <div><dt>เวอร์ชัน</dt><dd class="mono ver">Python {h.python} · PostgreSQL {h.postgres.split(' ')[0]}</dd></div>
    </dl>

    {#if h.failed_jobs.length}
      <div class="card failed">
        <h3>งานที่ล้มเหลว</h3>
        <table class="data">
          <thead><tr><th>งาน</th><th>ชนิด</th><th class="r">ลองแล้ว</th><th>ล้มเหลวเมื่อ</th></tr></thead>
          <tbody>
            {#each h.failed_jobs as j (j.id)}
              <tr><td class="mono">#{j.id}</td><td>{j.kind === 'ocr' ? 'อ่านเอกสาร (OCR)' : j.kind}</td><td class="r num">{j.attempts}</td><td class="num">{thDateTime(j.at)}</td></tr>
            {/each}
          </tbody>
        </table>
        <p class="hint">ดูรายละเอียดข้อผิดพลาดใน log ของ worker บนเซิร์ฟเวอร์ (docker compose logs worker)</p>
      </div>
    {/if}
  {/if}
</section>

<style>
  .health { display: flex; flex-direction: column; gap: 12px; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .head h2 { font-size: 20px; }
  .head small { font-size: 12px; }
  .state { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; }
  .state.ok, .lvl.ok { color: var(--ok); }
  .state.warn, .lvl.warn { color: var(--warn); }
  .state.bad, .lvl.bad { color: var(--bad); }
  .lvl.none { color: var(--muted); }

  .tiles { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .tile { display: flex; flex-direction: column; gap: 4px; padding: 16px 20px; border-left: 1px solid var(--border); min-width: 0; }
  .tile:first-child { border-left: 0; }
  .tile .label { font-size: 13px; font-weight: 400; color: var(--muted); }
  .value { font-family: var(--f-display); font-weight: 500; font-size: 20px; line-height: 1.3; }
  .note { font-size: 12px; color: var(--muted); }
  .lvl { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; margin-top: 4px; }
  .meter { display: block; height: 8px; border-radius: 4px; background: var(--subtle); overflow: hidden; margin: 4px 0 2px; }
  .fill { display: block; height: 100%; border-radius: 4px; background: var(--muted); transform-origin: left; transition: transform var(--t-med) var(--ease-out); }
  .fill.warn { background: var(--warn); }
  .fill.bad { background: var(--bad); }

  .facts { display: flex; flex-wrap: wrap; gap: 12px 32px; margin: 0; padding: 4px 4px 0; }
  .facts div { display: flex; flex-direction: column; min-width: 0; }
  .facts dt { font-size: 12px; color: var(--muted); }
  .facts dt a { color: var(--muted); }
  .facts dd { margin: 0; font-size: 15px; }
  .facts dd.hot { color: var(--primary-text); font-weight: 500; }
  .ver { font-size: 12px; }

  .failed { padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
  .failed h3 { font-size: 16px; }
  .r { text-align: right; }

  @media (max-width: 1180px) {
    .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .tile:nth-child(3n + 1) { border-left: 0; }
    .tile:nth-child(n + 4) { border-top: 1px solid var(--border); }
  }
  @media (max-width: 640px) {
    .tiles { grid-template-columns: 1fr 1fr; }
    .tile { padding: 12px 16px; border-top: 1px solid var(--border); }
    .tile:nth-child(3n + 1) { border-left: 1px solid var(--border); }
    .tile:nth-child(odd) { border-left: 0; }
    .tile:nth-child(-n + 2) { border-top: 0; }
    .value { font-size: 17px; }
    .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; }
  }
</style>
