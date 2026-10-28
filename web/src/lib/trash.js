// Move documents to the trash with an undo button, and take them back out.
import { post, errorText } from './api.js';
import { toast, bumpReviewCount } from './state.svelte.js';

const count = (ids) => (ids.length === 1 ? 'เอกสาร' : `${ids.length.toLocaleString('th-TH')} รายการ`);

/** Restore documents from my bin. Returns true when it worked. */
export async function restoreDocs(ids, after) {
  try {
    await post('/documents/trash/restore', { ids });
    bumpReviewCount();
    toast(`กู้คืน${count(ids)}แล้ว (ลิงก์แชร์เดิมยังใช้ไม่ได้)`);
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
