<script>
  import { get, errorText } from '../../lib/api.js';
  import { bytes } from '../../lib/format.js';

  let data = $state(null);
  let gaps = $state(null);
  let error = $state('');

  Promise.all([get('/admin/reports/overview'), get('/admin/reports/missing-numbers')])
    .then(([o, m]) => {
      data = o;
      gaps = m;
    })
    .catch((err) => (error = errorText(err)));

  const tiles = $derived(
    data
      ? [
          ['พร้อมใช้งาน', data.documents.ready, '/documents?status=ready'],
          ['รอตรวจสอบ', data.documents.needs_review, '/documents?status=needs_review'],
          ['กำลังอ่านเอกสาร', data.documents.processing, '/documents?status=processing'],
          ['อ่านไม่สำเร็จ', data.documents.failed, '/documents?status=failed'],
          ['ในถังขยะ', data.in_trash, '/admin/trash'],
          ['ลิงก์ที่ใช้งานอยู่', data.active_share_links, '/admin/shares'],
          ['ผู้ใช้', data.users, '/admin/users'],
          ['พื้นที่ไฟล์ (เข้ารหัส)', bytes(data.stored_bytes), null],
        ]
      : [],
  );
</script>

<div class="stack">
  <h1>ภาพรวม</h1>
  {#if error}<div class="notice bad">{error}</div>{/if}
  <div class="tiles">
    {#if !data}
      {#each Array(8) as _, i (i)}<div class="card tile"><div class="skel" style="width:50%"></div><div class="skel" style="width:30%;height:22px;margin-top:8px"></div></div>{/each}
    {:else}
      {#each tiles as [label, value, href] (label)}
        {#if href}
          <a class="card tile link" {href}><span class="muted">{label}</span><b class="num">{typeof value === 'number' ? value.toLocaleString('th-TH') : value}</b></a>
        {:else}
          <div class="card tile"><span class="muted">{label}</span><b class="num">{value}</b></div>
        {/if}
      {/each}
    {/if}
  </div>

  <section class="card pad stack">
    <h3>เลขที่สัญญาที่ขาดหาย</h3>
    <p class="hint">เลขที่ยังไม่มีไฟล์ในระบบ นับตั้งแต่เลข 001 ถึงเลขสูงสุดที่มีของแต่ละปีและแต่ละชุด (E = ทุนภายใน, A = ทุนภายนอก)</p>
    {#if gaps === null}
      <div class="skel" style="width:60%"></div>
    {:else if !gaps.length}
      <p class="muted">ยังไม่มีเอกสารที่มีเลขที่สัญญา</p>
    {:else}
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>ปี (พ.ศ.)</th><th>ชุด</th><th>มีแล้ว / เลขสูงสุด</th><th>เลขที่ขาด</th></tr></thead>
          <tbody>
            {#each gaps as g (g.year_be + g.series)}
              <tr>
                <td class="num">{g.year_be}</td>
                <td>{g.series === 'E' ? 'E · ภายใน' : g.series === 'A' ? 'A · ภายนอก' : g.series}</td>
                <td class="num">{g.stored} / {g.highest}</td>
                <td>{#if g.missing.length}<span class="mono miss">{g.missing.join(', ')}</span>{:else}<span class="badge ready">ครบ</span>{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>

<style>
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
  .tile { padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; text-decoration: none; color: var(--text); }
  .tile span { font-size: 13px; }
  .tile b { font-family: var(--f-display); font-weight: 500; font-size: 26px; }
  .tile.link { transition: border-color var(--t-fast); }
  .tile.link:hover { border-color: var(--primary); }
  .miss { color: var(--warn); overflow-wrap: anywhere; }
</style>
