<script>
  import { onMount } from 'svelte';
  import { route, match, navigate } from './lib/router.svelte.js';
  import { get, setUnauthorizedHandler } from './lib/api.js';
  import { session, screen, refreshReviewCount, toast } from './lib/state.svelte.js';
  import { uploads, openUpload, addFiles } from './lib/uploads.svelte.js';
  import TopNav from './components/TopNav.svelte';
  import MobileNav from './components/MobileNav.svelte';
  import UploadModal from './components/UploadModal.svelte';
  import Toasts from './components/Toasts.svelte';
  import Login from './pages/Login.svelte';
  import Guest from './pages/Guest.svelte';
  import Documents from './pages/Documents.svelte';
  import DocumentDetail from './pages/DocumentDetail.svelte';
  import ReviewForm from './pages/ReviewForm.svelte';
  import ReviewQueue from './pages/ReviewQueue.svelte';
  import Shares from './pages/Shares.svelte';
  import Account from './pages/Account.svelte';
  import Admin from './pages/admin/Admin.svelte';
  import NotFound from './pages/NotFound.svelte';

  const guestToken = $derived(match('/s/:token')?.token);

  setUnauthorizedHandler(() => {
    if (guestToken || !session.user) return;
    session.user = null;
    navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
  });

  onMount(async () => {
    if (guestToken) {
      session.checked = true;
      return;
    }
    try {
      session.user = await get('/auth/me', null, { quiet401: true });
      refreshReviewCount();
    } catch {
      session.user = null;
    }
    session.checked = true;
  });

  // Send people to the right place once we know whether they are logged in.
  $effect(() => {
    if (!session.checked || guestToken) return;
    if (!session.user && route.path !== '/login') {
      const next = route.path === '/' ? '' : `?next=${encodeURIComponent(route.path + location.search)}`;
      navigate(`/login${next}`, { replace: true });
    } else if (session.user && (route.path === '/' || route.path === '/login')) {
      navigate(route.query.get('next') || '/documents', { replace: true });
    }
  });

  const page = $derived.by(() => {
    const p = route.path;
    if (p === '/documents') return { C: Documents };
    if (p === '/review') return { C: ReviewQueue };
    if (p === '/shares') return { C: Shares };
    if (p === '/account') return { C: Account };
    if (p === '/admin' || p.startsWith('/admin/')) return { C: Admin, props: { section: p.split('/')[2] || 'overview' } };
    let m;
    if ((m = match('/documents/:id/review'))) return { C: ReviewForm, props: { id: m.id }, key: `r${m.id}` };
    if ((m = match('/documents/:id'))) return { C: DocumentDetail, props: { id: m.id }, key: `d${m.id}` };
    return { C: NotFound };
  });

  // Drop files anywhere on the app to upload them. Browsers and file managers announce files
  // differently ('Files', Firefox's x-moz-file, or only a file:// uri-list on some Linux
  // desktops), so accept all of them, but ignore drags that start inside the page (links, text).
  let innerDrag = false;
  const types = (e) => Array.from(e.dataTransfer?.types || []);
  const isFileDrag = (e) => {
    if (innerDrag) return false;
    const t = types(e);
    return t.includes('Files') || t.includes('application/x-moz-file') || t.includes('text/uri-list');
  };
  const editable = (el) => el?.closest?.('input, textarea, [contenteditable]');
  function dragEnter(e) {
    if (!session.user || !isFileDrag(e) || editable(e.target)) return;
    e.preventDefault();
    if (!uploads.open) openUpload();
  }
  function dragOver(e) {
    if (!session.user || !isFileDrag(e) || editable(e.target)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }
  function dropFiles(e) {
    if (!session.user || innerDrag || e.defaultPrevented || editable(e.target)) return;
    const files = e.dataTransfer?.files;
    if (!files?.length && !types(e).includes('text/uri-list')) return;
    e.preventDefault(); // never let the browser open the PDF in place of the app
    if (files?.length) addFiles(files);
    else toast('ลากไฟล์จากโฟลเดอร์ในเครื่องมาวาง หรือกดปุ่ม “เลือกไฟล์”', 'bad', 4500);
  }
</script>

<svelte:window
  ondragenter={dragEnter}
  ondragover={dragOver}
  ondrop={dropFiles}
  ondragstart={() => (innerDrag = true)}
  ondragend={() => (innerDrag = false)}
/>

{#if guestToken}
  <Guest token={guestToken} />
{:else if !session.checked}
  <div class="boot"><span class="spin"></span></div>
{:else if !session.user}
  <Login />
{:else}
  {#if screen.wide}<TopNav />{:else}<MobileNav />{/if}
  <main class:phone={!screen.wide}>
    {#key page.key ?? page.C}
      <div class="page enter">
        <page.C {...page.props} />
      </div>
    {/key}
  </main>
  <UploadModal />
{/if}
<Toasts />

<style>
  .boot { min-height: 100vh; display: grid; place-items: center; }
  main {
    max-width: 1440px; margin: 0 auto;
    padding: 20px max(20px, env(safe-area-inset-right)) 48px max(20px, env(safe-area-inset-left));
  }
  main.phone {
    padding: 14px max(12px, env(safe-area-inset-right)) calc(var(--bottom-h) + env(safe-area-inset-bottom) + 24px) max(12px, env(safe-area-inset-left));
  }
  .page { min-width: 0; }
</style>
