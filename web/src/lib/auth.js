import { post } from './api.js';
import { session } from './state.svelte.js';
import { navigate } from './router.svelte.js';

export async function logout() {
  try {
    await post('/auth/logout');
  } catch {
    /* the session may already be gone */
  }
  session.user = null;
  navigate('/login', { replace: true });
}
