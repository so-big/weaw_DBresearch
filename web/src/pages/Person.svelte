<script>
  // Researcher page: everything one person has in the system (live documents only).
  import { get, errorText } from '../lib/api.js';
  import { KIND, FUNDING_SOURCE, PROJECT_STATE, ROLE, docPath, money, personName } from '../lib/format.js';

  let { id } = $props();

  let data = $state(null);
  let error = $state('');

  async function load() {
    error = '';
    try {
      data = await get(`/people/${id}`);
    } catch (err) {
      error = err?.status === 404 ? 'ไม่พบบุคคลนี้' : errorText(err);
    }
  }
  load();

  const name = $derived(data ? personName(data.person) : '');
  const sections = $derived(
    data
      ? [
          ['สัญญาทุนวิจัย', data.contracts],
          ['ทุนพัฒนาข้อเสนอ', data.proposals],
        ]
      : [],
  );
  const roleText = (d) => `${ROLE[d.role] || d.role}${d.share_pct != null ? ` · ${Number(d.share_pct)}%` : ''}`;
  const stateText = (d) => (d.state ? PROJECT_STATE[d.state] : d.project === 'closed' ? 'ปิดโครงการแล้ว' : d.project === 'open' ? 'ดำเนินการอยู่' : '');
  const stateClass = (d) => (d.state ? `st-${d.state}` : d.project === 'closed' ? 'closed' : 'st-active');
</script>

<div class="person">
  {#if error}
    <div class="notice bad">{error} <a href="/documents">กลับไปรายการเอกสาร</a></div>
  {:else if !data}
    <div class="skel head-skel" style="width:50%"></div>
    <div class="skel head-skel" style="width:30%;height:14px"></div>
    <div class="card strip">
      {#each [0, 1, 2, 3] as i (i)}<div class="stat"><div class="skel" style="width:60%"></div><div class="skel" style="width:40%;height:22px;margin-top:8px"></div></div>{/each}
    </div>
    <div class="card list">
      {#each [0, 1, 2] as i (i)}
        <div class="item"><div class="skel" style="width:75%;height:14px"></div><div class="skel" style="width:45%;margin-top:8px"></div></div>
      {/each}
    </div>
  {:else}
    <header>
      <h1>{name}</h1>
      {#if data.person.name_th && data.person.name_en}<p class="muted en">{data.person.name_en}</p>{/if}
      {#if data.units.length}<p class="muted">{data.units.join(' · ')}</p>{/if}
    </header>

    <div class="card strip">
      <div class="stat"><span class="lab">โครงการทั้งหมด</span><b>{data.total.count.toLocaleString('th-TH')}</b></div>
      <div class="stat"><span class="lab">งบประมาณรวม</span><b>{money(data.total.budget)}</b></div>
      <div class="stat"><span class="lab">เป็นหัวหน้าโครงการ</span><b>{data.as_owner.toLocaleString('th-TH')}</b></div>
      <div class="stat"><span class="lab">เป็นผู้ร่วมวิจัย</span><b>{data.as_member.toLocaleString('th-TH')}</b></div>
    </div>

    {#if data.total.count}
      <div class="tables">
        <section class="card pad">
          <h3>แยกตามปีงบประมาณ</h3>
          <table class="data">
            <thead><tr><th>ปีงบ (พ.ศ.)</th><th class="num">โครงการ</th><th class="num">งบประมาณ</th></tr></thead>
            <tbody>
              {#each data.by_year as y (y.fiscal_year ?? 'none')}
                <tr><td>{y.fiscal_year_be ?? 'ไม่ระบุ'}</td><td class="num">{y.count}</td><td class="num">{money(y.budget)}</td></tr>
              {/each}
            </tbody>
          </table>
        </section>
        <section class="card pad">
          <h3>แยกตามแหล่งทุน</h3>
          <table class="data">
            <thead><tr><th>แหล่งทุน</th><th class="num">โครงการ</th><th class="num">งบประมาณ</th></tr></thead>
            <tbody>
              {#each data.by_source as s (s.funding_source ?? 'none')}
                <tr><td>{s.funding_source ? FUNDING_SOURCE[s.funding_source] : 'ไม่ระบุ'}</td><td class="num">{s.count}</td><td class="num">{money(s.budget)}</td></tr>
              {/each}
            </tbody>
          </table>
        </section>
      </div>
    {/if}

    {#each sections as [title, items] (title)}
      <h2>{title} <span class="muted n">{items.length}</span></h2>
      {#if items.length}
        <div class="card list">
          {#each items as d (d.id)}
            <a class="item" href={docPath(d)}>
              <div class="grow">
                <div class="topline">
                  {#if d.reference_no}<span class="cno">{d.reference_no}</span>{/if}
                  {#if d.request_ref}<span class="kind">ที่ {d.request_ref}</span>{/if}
                  {#if d.kind && d.kind !== 'proposal_dev'}<span class="kind">{KIND[d.kind]}</span>{/if}
                </div>
                <div class="t">{d.title}</div>
                <div class="meta">
                  <span>{roleText(d)}</span>
                  {#if d.fiscal_year_be}<span>ปีงบ {d.fiscal_year_be}</span>{/if}
                  {#if d.funding_source}<span>{FUNDING_SOURCE[d.funding_source]}</span>{/if}
                  {#if d.budget_total}<span>{money(d.budget_total)}</span>{/if}
                </div>
              </div>
              <div class="side">
                {#if d.status !== 'ready'}<span class="badge neutral">ยังไม่พร้อมใช้งาน</span>
                {:else if stateText(d)}<span class="badge {stateClass(d)}">{stateText(d)}</span>{/if}
              </div>
            </a>
          {/each}
        </div>
      {:else}
        <p class="muted none">ไม่มีรายการ</p>
      {/if}
    {/each}

    {#if data.similar.length}
      <section class="similar muted">
        <h3>อาจเป็นบุคคลเดียวกัน</h3>
        <ul>
          {#each data.similar as p (p.id)}<li><a href="/people/{p.id}">{personName(p)}</a></li>{/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>

<style>
  .person { display: flex; flex-direction: column; gap: 16px; max-width: 1000px; }
  .head-skel { height: 26px; }
  h1 { font-size: 26px; line-height: 1.3; overflow-wrap: anywhere; }
  header p { margin: 2px 0 0; }
  h2 { font-size: 17px; margin-top: 8px; }
  h2 .n { font-size: 14px; font-weight: 400; margin-left: 4px; }
  h3 { font-size: 14px; margin: 0 0 8px; }
  .pad { padding: 14px 16px; }
  .strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .stat { padding: 14px 16px; border-left: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .stat:first-child { border-left: 0; }
  .lab { font-size: 12.5px; color: var(--muted); }
  .stat b { font-size: 19px; font-weight: 600; overflow-wrap: anywhere; }
  .tables { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .num { text-align: right; white-space: nowrap; }
  .list { overflow: hidden; }
  .item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; padding: 13px 16px; border-top: 1px solid var(--border); color: inherit; text-decoration: none; transition: background var(--t-fast); }
  .item:first-child { border-top: 0; }
  a.item:hover { background: var(--subtle); }
  .grow { min-width: 0; }
  .topline { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; font-size: 12px; }
  .kind { color: var(--muted); }
  .t { font-weight: 500; font-size: 15px; line-height: 1.45; overflow-wrap: anywhere; }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; color: var(--muted); margin-top: 4px; }
  .side { display: flex; align-items: flex-start; }
  .none { margin: 0; font-size: 14px; }
  .similar { font-size: 13px; }
  .similar h3 { font-weight: 500; }
  .similar ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 14px; }
  @media (max-width: 720px) {
    .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stat:nth-child(odd) { border-left: 0; }
    .stat:nth-child(n + 3) { border-top: 1px solid var(--border); }
    .tables { grid-template-columns: minmax(0, 1fr); }
    h1 { font-size: 22px; }
  }
</style>
