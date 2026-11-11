<script>
  // Home: everyone's start page. Search and upload first, then what is waiting for me
  // (reviews, overdue grants, share links about to expire), my latest uploads and what
  // others added to the library lately. The system overview (ภาพรวม) is for admins only.
  import { get, errorText } from '../lib/api.js';
  import Icon from '../components/Icon.svelte';
  import { navigate } from '../lib/router.svelte.js';
  import { session, isAdmin, screen, ui } from '../lib/state.svelte.js';
  import { openUpload } from '../lib/uploads.svelte.js';
  import { STATUS, KIND, FUNDING, thDate, timeLeft, docPath } from '../lib/format.js';

  let q = $state('');
  let input = $state();
  let mine = $state(null); // my documents waiting for review / being read
  let overdue = $state(null); // proposal grants past their KPI due date
  let links = $state(null); // my share links
  let recentMine = $state(null);
  let recent = $state(null); // the library, newest first
  let error = $state('');

  const SOON = 48 * 36e5; // a link "expires soon" within 48 hours

  Promise.all([
    get('/documents', { section: 'all', status: ['processing', 'needs_review', 'failed'], mine: true, sort: 'oldest', page_size: 20 }),
    get('/documents', { section: 'proposals', state: ['overdue'], page_size: 5 }),
    get('/shares', { active_only: true }),
    get('/documents', { section: 'all', mine: true, sort: 'newest', page_size: 5 }),
    get('/documents', { section: 'all', sort: 'newest', page_size: 12 }),
  ])
    .then(([m, o, l, rm, r]) => {
      mine = m;
      overdue = o;
      links = l;
      recentMine = rm;
      recent = r;
    })
    .catch((err) => (error = errorText(err)));

  const loaded = $derived(mine && overdue && links && recentMine && recent);
  const toReview = $derived((mine?.items || []).filter((d) => d.status !== 'processing'));
  const reading = $derived((mine?.items || []).filter((d) => d.status === 'processing'));
  const activeLinks = $derived((links || []).filter((s) => s.state === 'active'));
  const expiring = $derived(activeLinks.filter((s) => new Date(s.expires_at) - Date.now() < SOON));
  const others = $derived((recent?.items || []).filter((d) => d.uploaded_by !== session.user?.id).slice(0, 6));
  const taskCount = $derived(toReview.length + (overdue?.total || 0) + expiring.length);

  const today = new Date().toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  function submit(e) {
    e.preventDefault();
    const text = q.trim();
    navigate(text ? `/documents?q=${encodeURIComponent(text)}` : '/documents');
  }

  // The "/" key and the phone's search button focus this box while on the home page.
  let lastFocus = ui.searchFocus;
  $effect(() => {
    if (ui.searchFocus !== lastFocus) {
      lastFocus = ui.searchFocus;
      input?.focus();
    }
  });

  const reviewPath = (d) => `${docPath(d)}/review`;
  const n = (v) => (v ?? 0).toLocaleString('th-TH');
</script>

<div class="home" class:phone={!screen.wide}>
  <header class="head">
    <div class="title">
      <h1>{today}</h1>
      <p class="muted">{session.user?.display_name} · {isAdmin() ? 'ผู้ดูแลระบบ' : 'เจ้าหน้าที่งานวิจัย'}</p>
    </div>
    <div class="actions">
      <form class="search" role="search" onsubmit={submit}>
        <Icon name="search" size={18} />
        <input
          bind:this={input}
          bind:value={q}
          type="search"
          placeholder={screen.wide ? 'ชื่อเรื่อง เลขที่สัญญา หรือข้อความในเอกสาร' : 'ค้นหาเอกสาร'}
          aria-label="ค้นหาเอกสาร"
          enterkeyhint="search"
        />
      </form>
    </div>
  </header>

  {#if error}<div class="notice bad">{error}</div>{/if}

  <dl class="figs">
    <a class="fig" href="/review">
      <dt>รอคุณตรวจสอบ</dt>
      <dd class="num" class:hot={loaded && toReview.length > 0}>{loaded ? n(toReview.length) : '–'}</dd>
    </a>
    <a class="fig" href="/proposals?project=overdue">
      <dt>ทุนพัฒนาเกินกำหนด</dt>
      <dd class="num">{loaded ? n(overdue.total) : '–'}</dd>
    </a>
    <a class="fig" href="/shares">
      <dt>ลิงก์แชร์ที่เปิดอยู่</dt>
      <dd class="num">{loaded ? n(activeLinks.length) : '–'}</dd>
    </a>
    <a class="fig" href="/documents?mine=true">
      <dt>เอกสารที่ฉันอัปโหลด</dt>
      <dd class="num">{loaded ? n(recentMine.total) : '–'}</dd>
    </a>
  </dl>

  <div class="grid">
    <div class="col">
    <section class="card tasks" aria-labelledby="h-tasks">
      <div class="sec-head">
        <h2 id="h-tasks">งานที่ต้องทำ</h2>
        {#if loaded && taskCount}<span class="muted num">{n(taskCount)} รายการ</span>{/if}
        <span class="spacer"></span>
        <a class="more" href="/review">รอตรวจสอบทั้งหมด</a>
      </div>

      {#if !loaded}
        {#each Array(3) as _, i (i)}<div class="row"><div class="skel" style="width:60%"></div></div>{/each}
      {:else if !taskCount && !reading.length}
        <div class="clear">
          <Icon name="check" size={24} />
          <p>ไม่มีงานค้าง</p>
          <small class="muted">เอกสารที่คุณอัปโหลดตรวจสอบครบแล้ว</small>
        </div>
      {:else}
        <ul class="list">
          {#each toReview.slice(0, 6) as d (d.id)}
            <li class="row task">
              <span class="dot warn" aria-hidden="true"></span>
              <div class="body">
                <a class="t" href={docPath(d)}>{d.title}</a>
                <span class="meta">
                  {#if d.reference_no}<span class="cno">{d.reference_no}</span>{/if}
                  <span>{STATUS[d.status]}</span>
                  <span>อัปเดต {thDate(d.updated_at)}</span>
                </span>
              </div>
              <a class="btn small soft" href={reviewPath(d)}>ตรวจสอบ</a>
            </li>
          {/each}
          {#if toReview.length > 6}
            <li class="row rest"><a href="/review">อีก {n(toReview.length - 6)} ฉบับรอตรวจสอบ</a></li>
          {/if}
          {#each overdue.items as d (d.id)}
            <li class="row task">
              <span class="dot bad" aria-hidden="true"></span>
              <div class="body">
                <a class="t" href={docPath(d)}>{d.title}</a>
                <span class="meta">
                  <span>ทุนพัฒนาข้อเสนอ เกินกำหนดส่งผลงาน {thDate(d.kpi_due)}</span>
                  {#if d.owners?.length}<span>{d.owners[0]}</span>{/if}
                </span>
              </div>
              <a class="btn small ghost" href={docPath(d)}>เปิด</a>
            </li>
          {/each}
          {#if overdue.total > overdue.items.length}
            <li class="row rest"><a href="/proposals?project=overdue">ทุนเกินกำหนดอีก {n(overdue.total - overdue.items.length)} โครงการ</a></li>
          {/if}
          {#each expiring as s (s.id)}
            <li class="row task">
              <span class="dot info" aria-hidden="true"></span>
              <div class="body">
                <a class="t" href="/documents/{s.document_id}">{s.document_title}</a>
                <span class="meta"><span>ลิงก์แชร์หมดอายุ{timeLeft(s.expires_at)}</span>{#if s.note}<span>{s.note}</span>{/if}</span>
              </div>
              <a class="btn small ghost" href="/shares">จัดการ</a>
            </li>
          {/each}
          {#each reading as d (d.id)}
            <li class="row task quiet">
              <span class="spin" aria-hidden="true"></span>
              <div class="body">
                <a class="t" href={docPath(d)}>{d.title}</a>
                <span class="meta"><span>ระบบกำลังอ่านเอกสาร จะขึ้นในรายการรอตรวจสอบเมื่อเสร็จ</span></span>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {@render shortcuts()}
    </div>
    <div class="col">
    <section class="card recent" aria-labelledby="h-recent">
      <div class="sec-head">
        <h2 id="h-recent">เพิ่งเข้าคลัง</h2>
        <span class="spacer"></span>
        <a class="more" href="/documents?sort=newest">ทั้งหมด</a>
      </div>
      {#if !loaded}
        {#each Array(4) as _, i (i)}<div class="row"><div class="skel" style="width:70%"></div></div>{/each}
      {:else if !others.length}
        <p class="empty muted">ยังไม่มีเอกสารจากคนอื่น</p>
      {:else}
        <ul class="list">
          {#each others as d (d.id)}
            {@render docRow(d)}
          {/each}
        </ul>
      {/if}
    </section>

    <section class="card mine" aria-labelledby="h-mine">
      <div class="sec-head">
        <h2 id="h-mine">ที่ฉันอัปโหลดล่าสุด</h2>
        <span class="spacer"></span>
        <a class="more" href="/documents?mine=true&sort=newest">ทั้งหมด</a>
      </div>
      {#if !loaded}
        {#each Array(3) as _, i (i)}<div class="row"><div class="skel" style="width:70%"></div></div>{/each}
      {:else if !recentMine.items.length}
        <div class="clear">
          <p>ยังไม่ได้อัปโหลดเอกสาร</p>
          <button class="btn small ghost" onclick={() => openUpload()}><Icon name="upload" size={16} />อัปโหลดไฟล์แรก</button>
        </div>
      {:else}
        <ul class="list">
          {#each recentMine.items as d (d.id)}
            {@render docRow(d, true)}
          {/each}
        </ul>
      {/if}
    </section>

    </div>
  </div>
</div>

{#snippet shortcuts()}
    <nav class="card shortcuts" aria-label="ทางลัด">
      <a href="/proposals"><Icon name="bulb" size={18} /><span>ทุนพัฒนาข้อเสนอ</span><Icon name="chevron" size={16} /></a>
      <a href="/shares"><Icon name="link" size={18} /><span>ลิงก์แชร์ของฉัน</span><Icon name="chevron" size={16} /></a>
      <a href="/trash"><Icon name="trash" size={18} /><span>ถังขยะของฉัน</span><Icon name="chevron" size={16} /></a>
      {#if isAdmin()}
        <a href="/overview"><Icon name="server" size={18} /><span>ภาพรวมระบบ</span><Icon name="chevron" size={16} /></a>
      {/if}
    </nav>
{/snippet}

{#snippet docRow(d, withStatus = false)}
  <li class="row doc">
    <span class="ftile sm f-{d.funding_type || 'unset'}" title={d.funding_type ? FUNDING[d.funding_type] : 'ยังไม่ระบุประเภทเงินทุน'} aria-hidden="true">
      {d.fiscal_year_be ? String(d.fiscal_year_be).slice(2) : '–'}
    </span>
    <div class="body">
      <a class="t" href={docPath(d)}>{d.title}</a>
      <span class="meta">
        {#if d.reference_no}<span class="cno">{d.reference_no}</span>{:else if d.kind}<span>{KIND[d.kind]}</span>{/if}
        {#if withStatus && d.status !== 'ready'}<span class="badge {d.status}">{STATUS[d.status]}</span>{/if}
        <span>{thDate(d.updated_at)}</span>
      </span>
    </div>
  </li>
{/snippet}

<style>
  .home { max-width: 1240px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }

  .head { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 560px); gap: 16px 32px; align-items: end; }
  .title h1 { font-size: 24px; }
  .title p { font-size: 14px; margin-top: 4px; }
  .actions { display: flex; gap: 8px; }
  .search {
    flex: 1; display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; min-width: 0;
    background: var(--surface); border: 1px solid var(--border-strong); border-radius: 10px; color: var(--muted);
    transition: border-color var(--t-fast);
  }
  .search:focus-within { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
  .search input { flex: 1; min-width: 0; border: 0; background: none; outline: none; font-size: 15px; color: var(--text); }

  /* four figures: a label and a number, each a way into its list */
  .figs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
  .fig { display: flex; flex-direction: column; gap: 4px; padding: 16px 20px; text-decoration: none; color: inherit; border-left: 1px solid var(--border); transition: background var(--t-fast); }
  .fig:first-child { border-left: 0; border-radius: var(--radius) 0 0 var(--radius); }
  .fig:last-child { border-radius: 0 var(--radius) var(--radius) 0; }
  @media (hover: hover) { .fig:hover { background: var(--subtle); } }
  .fig dt { font-size: 13px; color: var(--muted); }
  .fig dd { margin: 0; font-family: var(--f-display); font-weight: 500; font-size: 32px; line-height: 1.1; }
  .fig dd.hot { color: var(--primary-text); }

  .grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; align-items: start; }
  .col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .card { min-width: 0; }
  .sec-head { display: flex; align-items: baseline; gap: 8px; padding: 16px 20px 8px; }
  .sec-head h2 { font-size: 16px; }
  .sec-head .muted { font-size: 13px; }
  .more { font-size: 13px; text-decoration: none; white-space: nowrap; }
  .more:hover { text-decoration: underline; }

  .list { list-style: none; margin: 0; padding: 0 0 8px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 12px 20px; border-top: 1px solid var(--border); min-width: 0; }
  .list .row:first-child { border-top: 0; }
  .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .t { color: var(--text); text-decoration: none; font-size: 14px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  @media (hover: hover) { .t:hover { color: var(--primary-text); } }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 12px; color: var(--muted); }
  .meta .cno { font-size: 12px; }
  .meta .badge { font-size: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; align-self: flex-start; margin-top: 8px; }
  .dot.warn { background: var(--warn); }
  .dot.bad { background: var(--bad); }
  .dot.info { background: var(--info); }
  .task .btn { flex: none; }
  .task.quiet .t { color: var(--muted); }
  .task .spin { align-self: flex-start; margin-top: 4px; width: 12px; height: 12px; }
  .rest { font-size: 13px; padding-left: 40px; }
  .rest a { text-decoration: none; }

  .ftile.sm { width: 32px; height: 38px; font-size: 14px; padding-bottom: 6px; border-radius: 4px 8px 4px 4px; flex: none; align-self: flex-start; }

  .clear { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 32px 20px 40px; text-align: center; color: var(--ok); }
  .clear p { color: var(--text); }
  .clear small { font-size: 13px; }
  .mine .clear { color: var(--muted); padding: 24px 20px 28px; }
  .empty { padding: 16px 20px 24px; font-size: 14px; }

  .shortcuts { display: flex; flex-direction: column; padding: 8px; }
  .shortcuts a { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 8px; color: var(--text); text-decoration: none; font-size: 14px; transition: background var(--t-fast); }
  .shortcuts a:hover { background: var(--subtle); }
  .shortcuts a span { flex: 1; }
  .shortcuts a :global(svg) { color: var(--muted); }

  @media (max-width: 1080px) {
    .head { grid-template-columns: 1fr; }
    .grid { grid-template-columns: minmax(0, 1fr); }
  }

  /* phone: figures in a 2×2 block, everything in one column */
  .phone { gap: 16px; }
  .phone .title h1 { font-size: 20px; }
  .phone .title p { font-size: 13px; }
  .phone .figs { grid-template-columns: 1fr 1fr; }
  .phone .fig { padding: 12px 16px; }
  .phone .fig:nth-child(odd) { border-left: 0; }
  .phone .fig:nth-child(n + 3) { border-top: 1px solid var(--border); }
  .phone .fig:first-child { border-radius: var(--radius) 0 0 0; }
  .phone .fig:nth-child(2) { border-radius: 0 var(--radius) 0 0; }
  .phone .fig:nth-child(3) { border-radius: 0 0 0 var(--radius); }
  .phone .fig:last-child { border-radius: 0 0 var(--radius) 0; }
  .phone .fig dd { font-size: 24px; }
  .phone .sec-head { padding: 12px 16px 4px; }
  .phone .row { padding: 12px 16px; }
  .phone .rest { padding-left: 36px; }
  .phone .shortcuts { display: none; } /* the account page has these on phones */
</style>
