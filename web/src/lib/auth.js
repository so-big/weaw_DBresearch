import { post } from './api.js';
import { session } from './state.svelte.js';
import { navigate, canLeave } from './router.svelte.js';
import { clearDrafts } from './draft.js';

export async function logout(everywhere = false) {
  if (!canLeave()) return; // unsaved edits: let the person decide first
  try {
    await post(everywhere ? '/auth/logout-all' : '/auth/logout');
  } catch {
    /* the session may already be gone */
  }
  if (session.user) clearDrafts(session.user.id);
  session.user = null;
  navigate('/login', { replace: true, force: true });
}
