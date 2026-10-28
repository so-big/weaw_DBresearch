// App-wide state: session, toasts, review count, theme, screen size.
import { get } from './api.js';

export const session = $state({ user: null, checked: false });

export const isAdmin = () => session.user?.role === 'admin';

// ───────── Toasts ─────────
export const toasts = $state([]);
let toastId = 0;
export function toast(text, kind = 'ok', ms = 3200) {
  const id = ++toastId;
  toasts.push({ id, text, kind });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, ms);
}

// ───────── Review queue count (badge on the รอตรวจสอบ tab) ─────────
export const review = $state({ count: 0 });
let reviewTimer;
export async function refreshReviewCount() {
  if (!session.user) return;
  clearTimeout(reviewTimer);
  try {
    const res = await get('/documents', {
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
export const ui = $state({ searchFocus: 0 });
