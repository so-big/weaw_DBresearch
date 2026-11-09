import { post } from './api.js';
import { session } from './state.svelte.js';
import { navigate } from './router.svelte.js';

export async function logout(everywhere = false) {
  try {
    await post(everywhere ? '/auth/logout-all' : '/auth/logout');
  } catch {
    /* the session may already be gone */
  }
  session.user = null;
  navigate('/login', { replace: true });
}
