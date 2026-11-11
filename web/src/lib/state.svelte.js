// App-wide state: session, toasts, review count, theme, screen size.
import { get } from './api.js';

export const session = $state({ user: null, checked: false });

export const isAdmin = () => session.user?.role === 'admin';

// ───────── Toasts ─────────
export const toasts = $state([]);
let toastId = 0;
/** Show a short message. `action` = { label, run } adds a button (e.g. undo a delete). */
export function toast(text, kind = 'ok', ms = 3200, action = null) {
  const id = ++toastId;
  toasts.push({ id, text, kind, action });
  setTimeout(() => dismissToast(id), action ? Math.max(ms, 7000) : ms);
}
export function dismissToast(id) {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}

// ───────── Review queue count (badge on the รอตรวจสอบ tab) ─────────
export const review = $state({ count: 0 });
let reviewTimer;
export async function refreshReviewCount() {
  if (!session.user) return;
  clearTimeout(reviewTimer);
  try {
    const res = await get('/documents', {
      section: 'all',
      status: ['needs_review', 'failed'],
      mine: isAdmin() ? undefined : true,
      page_size: 1,
    });
    review.count = res.total;
  } catch {
    /* badge is best effort */
  }
}
/** Debounced refresh for bursts of uploads. */
export function bumpReviewCount() {
  clearTimeout(reviewTimer);
  reviewTimer = setTimeout(refreshReviewCount, 600);
}

// ───────── Access requests (count on the admin ผู้ใช้ menu) ─────────
export const access = $state({ requests: 0 });
export async function refreshAccessRequests() {
  if (!isAdmin()) return;
  try {
    access.requests = (await get('/admin/users/requests')).length;
  } catch {
    /* badge is best effort */
  }
}

// ───────── Theme ─────────
export const theme = $state({ value: 'system' });
export function initTheme() {
  try {
    theme.value = localStorage.getItem('theme') || 'system';
  } catch {
    theme.value = 'system';
  }
  applyTheme();
}
export function setTheme(value) {
  theme.value = value;
  try {
    localStorage.setItem('theme', value);
  } catch {
    /* private mode: theme just won't persist */
  }
  applyTheme();
}
function applyTheme() {
  const root = document.documentElement;
  if (theme.value === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme.value);
}

// ───────── Screen size (PC/tablet ≥ 768px gets the header tabs) ─────────
const wide = matchMedia('(min-width: 768px)');
export const screen = $state({ wide: wide.matches });
wide.addEventListener('change', (e) => (screen.wide = e.matches));

/** Motion helper: 0 when the user asked for reduced motion. */
export const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
export const ms = (n) => (reduced() ? 0 : n);

// Phone: the center search button asks the documents page to focus its search box.
// `bar`: a bottom action bar is showing (select mode), so toasts sit above it.
// `shareDoc`: a document id whose share dialog its page should open on arrival (after a restore).
export const ui = $state({ searchFocus: 0, bar: false, shareDoc: null });
