// Move documents to the trash with an undo button, and take them back out.
import { post, errorText } from './api.js';
import { toast, bumpReviewCount, ui } from './state.svelte.js';
import { navigate } from './router.svelte.js';

const count = (ids) => (ids.length === 1 ? 'เอกสาร' : `${ids.length.toLocaleString('th-TH')} รายการ`);

/** Text for the links the deletion revoked ('' when there were none). */
export const revokedNote = (ids, revoked) =>
  revoked ? `ลิงก์แชร์เดิมของเอกสาร${ids.length === 1 ? 'นี้' : 'เหล่านี้'}ถูกยกเลิกแล้ว` : '';

/** Toast after a restore. `res.revoked_links` > 0 adds the notice; one document also offers a new link. */
export function restoredToast(ids, res) {
  const note = revokedNote(ids, res?.revoked_links);
  const text = `กู้คืน${count(ids)}แล้ว`;
  if (!note) return toast(text);
  const open = () => {
    ui.shareDoc = ids[0];
    navigate(`/documents/${ids[0]}`); // proposal-type documents are redirected by their page
  };
  toast(`${text} ${note}`, 'ok', 9000, ids.length === 1 ? { label: 'สร้างลิงก์ใหม่', run: open } : null);
}

/** Restore documents from my bin. Returns true when it worked. */
export async function restoreDocs(ids, after) {
  try {
    const res = await post('/documents/trash/restore', { ids });
    bumpReviewCount();
    restoredToast(ids, res);
    after?.();
    return true;
  } catch (err) {
    toast(errorText(err), 'bad', 5000);
    return false;
  }
}

/** Move to the trash (all or none). The toast offers undo; `after` runs after either. */
export async function trashDocs(ids, after) {
  await post('/documents/trash', { ids });
  bumpReviewCount();
  toast(`ย้าย${count(ids)}ไปถังขยะแล้ว`, 'ok', 8000, { label: 'เลิกทำ', run: () => restoreDocs(ids, after) });
}
