<script>
  import { get, errorText } from '../../lib/api.js';
  import { bytes, STATUS } from '../../lib/format.js';
  import ChartCard from '../../components/charts/ChartCard.svelte';
  import Columns from '../../components/charts/Columns.svelte';
  import Trend from '../../components/charts/Trend.svelte';
  import StatusMeter from '../../components/charts/StatusMeter.svelte';
  import RankBars from '../../components/charts/RankBars.svelte';
  import NumberGrid from '../../components/charts/NumberGrid.svelte';
  import { monthLabel, dayLabel, short, full } from '../../components/charts/scale.js';

  let data = $state(null);
  let charts = $state(null);
  let gaps = $state(null);
  let error = $state('');
  let group = $state('research_type');

  Promise.all([get('/admin/reports/overview'), get('/admin/reports/charts'), get('/admin/reports/missing-numbers')])
    .then(([o, c, m]) => {
      data = o;
      charts = c;
      gaps = m;
      if (!c.categories.some((g) => g.key === group) && c.categories[0]) group = c.categories[0].key;
    })
    .catch((err) => (error = errorText(err)));

  const FUND = [
    { key: 'internal', label: 'ทุนภายใน', color: 'var(--c-internal)' },
    { key: 'external', label: 'ทุนภายนอก', color: 'var(--c-external)' },
    { key: 'unset', label: 'ยังไม่ระบุ', color: 'var(--c-unset)' },
  ];
  const fundSeries = $derived(FUND.filter((f) => charts?.by_year.some((y) => y[f.key] > 0)));
  const budgetSeries = $derived(FUND.filter((f) => charts?.by_year.some((y) => y[`budget_${f.key}`] > 0)));
  const total = $derived(data ? Object.values(data.documents).reduce((a, b) => a + b, 0) : 0);
  const views30 = $derived(charts ? charts.activity_by_day.reduce((s, d) => s + d.view + d.download, 0) : 0);
  const budgetAll = $derived(charts ? charts.by_year.reduce((s, y) => s + y.budget_internal + y.budget_external + y.budget_unset, 0) : 0);
  const currentGroup = $derived(charts?.categories.find((g) => g.key === group));
  const baht = (n) => `${full(n)} บาท`;
</script>

{#if error}<div class="notice bad">{error}</div>{/if}

{#if !data || !charts}
  <div class="grid">
    {#each Array(4) as _, i (i)}<div class="card skeleton-card"><div class="skel" style="width:40%"></div><div class="skel" style="width:90%;height:120px;margin-top:14px"></div></div>{/each}
  </div>
{:else}
  <section class="hero card">
    <div class="lead">
      <span class="muted">เอกสารในคลังทั้งหมด</span>
      <b class="big num">{total.toLocaleString('th-TH')}</b>
      <span class="muted sub">งบประมาณที่บันทึกไว้รวม {short(budgetAll)} บาท</span>
    </div>
    <div class="meter">
      <StatusMeter
        parts={[
          { key: 'ready', label: STATUS.ready, count: data.documents.ready, color: 'var(--ok)', href: '/documents?status=ready' },
          { key: 'needs_review', label: STATUS.needs_review, count: data.documents.needs_review, color: 'var(--warn)', href: '/documents?status=needs_review' },
          { key: 'processing', label: STATUS.processing, count: data.documents.processing, color: 'var(--info)', href: '/documents?status=processing' },
          { key: 'failed', label: STATUS.failed, count: data.documents.failed, color: 'var(--bad)', href: '/documents?status=failed' },
        ]}
      />
    </div>
    <dl class="facts">
      <div><dt>เปิดดูและดาวน์โหลด 30 วัน</dt><dd class="num">{views30.toLocaleString('th-TH')}</dd></div>
      <div><dt><a href="/admin/shares">ลิงก์แชร์ที่ใช้งานอยู่</a></dt><dd class="num">{data.active_share_links}</dd></div>
      <div><dt><a href="/admin/users">ผู้ใช้</a></dt><dd class="num">{data.users}</dd></div>
      <div><dt><a href="/admin/trash">ในถังขยะ</a></dt><dd class="num">{data.in_trash}</dd></div>
      <div><dt>พื้นที่ไฟล์ (เข้ารหัส)</dt><dd class="num">{bytes(data.stored_bytes)}</dd></div>
    </dl>
  </section>

  <div class="grid">
    <ChartCard
      title="เอกสารตามปีงบประมาณ"
      note={charts.no_fiscal_year ? `ไม่นับ ${charts.no_fiscal_year} ฉบับที่ยังไม่ระบุปีงบ` : 'แยกตามประเภทเงินทุน'}
      legend={fundSeries}
    >
      {#if charts.by_year.length}
        <Columns data={charts.by_year.map((y) => ({ label: `${y.fiscal_year_be}`, tip: `ปีงบ ${y.fiscal_year_be}`, values: y }))} series={fundSeries} unit=" ฉบับ" />
      {:else}<p class="empty muted">ยังไม่มีเอกสารที่ระบุปีงบประมาณ</p>{/if}
      {#snippet table()}
        <table class="data"><thead><tr><th>ปีงบ</th>{#each fundSeries as s (s.key)}<th class="r">{s.label}</th>{/each}</tr></thead>
          <tbody>{#each charts.by_year as y (y.fiscal_year)}<tr><td>{y.fiscal_year_be}</td>{#each fundSeries as s (s.key)}<td class="r num">{y[s.key]}</td>{/each}</tr>{/each}</tbody></table>
      {/snippet}
    </ChartCard>

    <ChartCard title="งบประมาณตามปีงบประมาณ" note="ผลรวมงบประมาณจากสัญญาที่ตรวจแล้ว (บาท)" legend={budgetSeries}>
      {#if budgetSeries.length}
        <Columns
          data={charts.by_year.map((y) => ({ label: `${y.fiscal_year_be}`, tip: `ปีงบ ${y.fiscal_year_be}`, values: Object.fromEntries(FUND.map((f) => [f.key, y[`budget_${f.key}`]])) }))}
          series={budgetSeries}
          format={(n) => full(n)}
          unit=" บาท"
        />
      {:else}<p class="empty muted">ยังไม่มีสัญญาที่บันทึกงบประมาณ</p>{/if}
      {#snippet table()}
        <table class="data"><thead><tr><th>ปีงบ</th>{#each budgetSeries as s (s.key)}<th class="r">{s.label}</th>{/each}</tr></thead>
          <tbody>{#each charts.by_year as y (y.fiscal_year)}<tr><td>{y.fiscal_year_be}</td>{#each budgetSeries as s (s.key)}<td class="r num">{baht(y[`budget_${s.key}`])}</td>{/each}</tr>{/each}</tbody></table>
      {/snippet}
    </ChartCard>

    <ChartCard title="อัปโหลดรายเดือน" note="จำนวนไฟล์ที่อัปโหลด รวมฉบับแก้ไข (12 เดือนล่าสุด)">
      <Trend
        data={charts.uploads_by_month.map((m) => ({ label: monthLabel(m.month), values: { count: m.count } }))}
        series={[{ key: 'count', label: 'ไฟล์', color: 'var(--c-internal)' }]}
      />
      {#snippet table()}
        <table class="data"><thead><tr><th>เดือน</th><th class="r">ไฟล์</th></tr></thead>
          <tbody>{#each charts.uploads_by_month as m (m.month)}<tr><td>{monthLabel(m.month)}</td><td class="r num">{m.count}</td></tr>{/each}</tbody></table>
      {/snippet}
    </ChartCard>

    <ChartCard
      title="การเปิดดูและดาวน์โหลด"
      note="รวมผู้ใช้และผู้มีลิงก์แชร์ (30 วันล่าสุด)"
      legend={[{ label: 'ดาวน์โหลด', color: 'var(--c-internal)' }, { label: 'เปิดดู', color: 'var(--c-external)' }]}
    >
      <Trend
        data={charts.activity_by_day.map((d) => ({ label: dayLabel(d.day), values: d }))}
        series={[{ key: 'download', label: 'ดาวน์โหลด', color: 'var(--c-internal)' }, { key: 'view', label: 'เปิดดู', color: 'var(--c-external)' }]}
      />
      {#snippet table()}
        <table class="data"><thead><tr><th>วันที่</th><th class="r">ดาวน์โหลด</th><th class="r">เปิดดู</th></tr></thead>
          <tbody>{#each charts.activity_by_day as d (d.day)}<tr><td>{dayLabel(d.day)}</td><td class="r num">{d.download}</td><td class="r num">{d.view}</td></tr>{/each}</tbody></table>
      {/snippet}
    </ChartCard>

    <ChartCard title="หมวดหมู่ที่ใช้มากที่สุด" note="นับจากเอกสารที่ตรวจแล้ว">
      {#if charts.categories.length}
        <div class="chips">
          {#each charts.categories as g (g.key)}<button class="chip" aria-pressed={group === g.key} onclick={() => (group = g.key)}>{g.name}</button>{/each}
        </div>
        <RankBars items={(currentGroup?.items || []).map((i) => ({ ...i, href: `/documents?category=${i.id}` }))} />
      {:else}<p class="empty muted">ยังไม่มีเอกสารที่ติดหมวดหมู่</p>{/if}
    </ChartCard>

    <ChartCard title="เลขที่สัญญาในระบบ" note="ช่องทึบ = มีไฟล์แล้ว (กดเพื่อค้นหา) · ช่องเส้นประ = ยังไม่มีไฟล์ นับจาก 001 ถึงเลขสูงสุดของแต่ละปี" wide>
      <NumberGrid rows={gaps || []} />
      {#snippet table()}
        <table class="data"><thead><tr><th>ปี (พ.ศ.)</th><th>ชุด</th><th class="r">มีแล้ว / เลขสูงสุด</th><th>เลขที่ขาด</th></tr></thead>
          <tbody>{#each gaps || [] as g (g.year_be + g.series)}<tr><td class="num">{g.year_be}</td><td>{g.series}</td><td class="r num">{g.stored} / {g.highest}</td><td class="cno">{g.missing.join(', ') || 'ครบ'}</td></tr>{/each}</tbody></table>
      {/snippet}
    </ChartCard>
  </div>
{/if}

<style>
  .hero {
    display: grid; grid-template-columns: minmax(180px, auto) minmax(0, 1fr); gap: 14px 32px; align-items: center;
    padding: 22px 24px; margin-bottom: 16px; position: relative; overflow: hidden;
  }
  .hero::after {
    /* the faculty site's soft circle, kept to one corner */
    content: ''; position: absolute; right: -60px; top: -80px; width: 220px; height: 220px; border-radius: 50%;
    background: var(--primary-soft); z-index: 0; pointer-events: none;
  }
  .hero > * { position: relative; z-index: 1; }
  .lead { display: flex; flex-direction: column; }
  .lead span { font-size: 13.5px; }
  .big { font-family: var(--f-display); font-weight: 600; font-size: 56px; line-height: 1.05; color: var(--primary-text); font-variant-numeric: proportional-nums; }
  .sub { font-size: 12.5px !important; }
  .facts { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 8px 28px; margin: 4px 0 0; padding-top: 14px; border-top: 1px solid var(--border); }
  .facts div { display: flex; flex-direction: column; }
  .facts dt { font-size: 12.5px; color: var(--muted); }
  .facts dt a { color: var(--muted); }
  .facts dd { margin: 0; font-family: var(--f-display); font-weight: 500; font-size: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 16px; }
  .skeleton-card { padding: 18px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .empty { padding: 30px 0; text-align: center; font-size: 13.5px; }
  .r { text-align: right; }
  @media (max-width: 640px) {
    .hero { grid-template-columns: 1fr; padding: 18px; }
    .big { font-size: 46px; }
  }
</style>
