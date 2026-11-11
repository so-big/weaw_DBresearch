// Small history router: path + query as reactive state, same-origin link interception.

function read() {
  return { path: location.pathname, query: new URLSearchParams(location.search) };
}

export const route = $state(read());

const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function apply() {
  const next = read();
  route.path = next.path;
  route.query = next.query;
}

// A page with unsaved edits can register a guard: it returns false to stay (it asks the user).
let leaveGuard = null;
/** Returns an unregister function. */
export function setLeaveGuard(fn) {
  leaveGuard = fn;
  return () => {
    if (leaveGuard === fn) leaveGuard = null;
  };
}
/** True when it is fine to leave the current page. */
export const canLeave = () => !leaveGuard || leaveGuard();

/** Go to a page. `replace` keeps history clean for filter changes. `force` skips the leave guard. */
export function navigate(url, { replace = false, scroll = true, force = false } = {}) {
  const target = new URL(url, location.origin);
  const same = target.pathname === location.pathname;
  if (!same && !force && !canLeave()) return;
  const change = () => {
    history[replace ? 'replaceState' : 'pushState'](null, '', target.pathname + target.search + target.hash);
    apply();
    if (scroll && !same) window.scrollTo(0, 0);
  };
  // Cross-fade between pages where the browser supports it; filters just swap.
  if (!same && document.startViewTransition && !reduceMotion()) document.startViewTransition(change);
  else change();
}

/** Update the query string of the current page without a history entry. */
export function setQuery(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.append(k, v);
  }
  const s = sp.toString();
  history.replaceState(null, '', location.pathname + (s ? `?${s}` : ''));
  route.query = new URLSearchParams(location.search);
}

export function startRouter() {
  addEventListener('popstate', () => {
    if (location.pathname !== route.path && !canLeave()) {
      // Back/forward already moved the URL: put it back (costs one extra history entry).
      history.pushState(null, '', route.path + (route.query.size ? `?${route.query}` : ''));
      return;
    }
    apply();
  });
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a');
    if (!a || a.target || a.hasAttribute('download') || a.origin !== location.origin) return;
    if (a.pathname.startsWith('/api/')) return; // files and downloads go to the server
    e.preventDefault();
    navigate(a.pathname + a.search + a.hash);
  });
}

/** Match "/documents/:id/review" style patterns. Returns params or null. */
export function match(pattern, path = route.path) {
  const p = pattern.split('/').filter(Boolean);
  const s = path.split('/').filter(Boolean);
  if (p.length !== s.length) return null;
  const params = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(':')) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}
