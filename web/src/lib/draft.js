// Unsaved review forms: a local draft in localStorage plus a session keep-alive while typing.
// Drafts hold only what the user typed (metadata), never file bytes or OCR text.
import { get } from './api.js';

const PREFIX = 'dbr-draft:';
const MAX_AGE = 7 * 24 * 3600 * 1000;
const PING_EVERY = 5 * 60 * 1000; // idle timeout is 60 min; GET /auth/me refreshes last_seen_at
const SAVE_DELAY = 800;

let blocked = false; // set on logout so a closing form cannot write a draft back

function keys() {
  const all = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k?.startsWith(PREFIX)) all.push(k);
  }
  return all;
}

/** Remove every draft of this user (logout) and stop pending writes. */
export function clearDrafts(userId) {
  blocked = true;
  try {
    for (const k of keys()) if (k.startsWith(`${PREFIX}${userId}:`)) localStorage.removeItem(k);
  } catch {
    /* storage unavailable */
  }
}

let lastPing = 0;
function ping() {
  if (Date.now() - lastPing < PING_EVERY) return;
  lastPing = Date.now();
  get('/auth/me', null, { quiet401: true }).catch(() => {}); // best effort; a dead session shows on save
}

/** One form's draft. `stamp` = the document's updated_at, so a draft never meets changed data. */
export function createDraft(userId, docId, stamp) {
  blocked = false;
  const prefix = `${PREFIX}${userId}:${docId}:`;
  const key = prefix + stamp;
  let baseline = null; // serialised form exactly as the server data produced it
  let last = null;
  let timer = null;
  let done = false; // saved: no more drafts, no leave warning
  let offered = false; // a stored draft awaits restore/discard: don't overwrite it

  const remove = () => {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  };
  function write(snap) {
    timer = null;
    if (blocked || done || offered) return;
    try {
      if (snap === baseline) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify({ t: Date.now(), snap }));
    } catch {
      /* storage full or blocked: the draft is a convenience */
    }
  }

  return {
    /** Call once the form is built. Returns the stored draft (serialised) if it differs, else null. */
    init(snap) {
      baseline = last = snap;
      try {
        for (const k of keys()) {
          if (!k.startsWith(prefix)) continue;
          const d = JSON.parse(localStorage.getItem(k) || 'null');
          if (k !== key || !d || Date.now() - d.t > MAX_AGE) localStorage.removeItem(k);
        }
        const d = JSON.parse(localStorage.getItem(key) || 'null');
        if (d && d.snap !== snap) {
          offered = true;
          return d.snap;
        }
      } catch {
        /* unreadable draft: ignore */
      }
      return null;
    },
    /** The user chose: pass the restored snapshot, or null to discard. Drafting resumes. */
    resolve(restoredSnap = null) {
      offered = false;
      if (restoredSnap === null) {
        remove();
        last = baseline;
      } else this.update(restoredSnap);
    },
    /** Call whenever the form changes (idempotent for an unchanged snapshot). */
    update(snap) {
      if (done || snap === last) return;
      last = snap;
      if (snap !== baseline) ping();
      clearTimeout(timer);
      timer = setTimeout(() => write(snap), SAVE_DELAY);
    },
    /** Write now (page closing, e.g. after a 401 sent the user to login). */
    flush() {
      if (timer === null) return;
      clearTimeout(timer);
      write(last);
    },
    isDirty: (snap) => !done && baseline !== null && snap !== baseline,
    /** After a successful save. */
    finish() {
      done = true;
      clearTimeout(timer);
      timer = null;
      remove();
    },
  };
}
