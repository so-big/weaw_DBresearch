// Upload queue shared by the whole app: survives closing the window and changing pages.
// Every row can be cancelled: waiting rows leave the queue, running ones are aborted, and a
// finished upload is undone by moving its new document to the trash.
import { uploadFile, thai, del } from './api.js';
import { bumpReviewCount } from './state.svelte.js';

const PARALLEL = 2;
const MAX_MB = 100;

export const uploads = $state({ open: false, items: [] });
let nextId = 0;
let running = 0;
const requests = new Map(); // row id -> XMLHttpRequest (kept outside the reactive state)

const active = (i) => i.state === 'wait' || i.state === 'up';
export const busyCount = () => uploads.items.filter(active).length;
export const doneOk = () => uploads.items.filter((i) => i.state === 'ok');

export function openUpload() {
  uploads.open = true;
}
export function closeUpload() {
  uploads.open = false;
}

/** Clear finished rows (after "review later" / "review now"). Rows still uploading stay. */
export function clearFinished() {
  uploads.items = uploads.items.filter(active);
}

function isPdf(file) {
  return file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
}

export function addFiles(fileList) {
  for (const file of Array.from(fileList || [])) {
    const item = { id: ++nextId, file, name: file.name, size: file.size, progress: 0, state: 'wait', message: '', docId: null };
    if (!isPdf(file)) {
      item.state = 'bad';
      item.message = 'รับเฉพาะไฟล์ PDF';
    } else if (file.size > MAX_MB * 1024 * 1024) {
      item.state = 'bad';
      item.message = `ไฟล์ใหญ่เกิน ${MAX_MB} MB`;
    }
    uploads.items.push(item);
  }
  pump();
}

function pump() {
  while (running < PARALLEL) {
    const item = uploads.items.find((i) => i.state === 'wait');
    if (!item) return;
    running++;
    send(item.id);
  }
}

const rowOf = (id) => uploads.items.find((i) => i.id === id);

async function send(id) {
  const row = rowOf(id);
  row.state = 'up';
  const { status, data } = await uploadFile(
    '/documents',
    row.file,
    (p) => (row.progress = p),
    (xhr) => requests.set(id, xhr),
  );
  requests.delete(id);
  running--;
  const current = rowOf(id);
  if (status === -1 || !current) {
    // Cancelled while uploading: nothing was stored.
    uploads.items = uploads.items.filter((i) => i.id !== id);
  } else {
    finish(current, status, data);
  }
  pump();
}

function finish(row, status, data) {
  row.progress = 1;
  if (status === 201 || status === 409) row.file = null; // done: let the browser free it
  if (status === 201) {
    row.state = 'ok';
    row.docId = data.id;
    bumpReviewCount();
  } else if (status === 409) {
    row.state = 'dup';
    row.docId = data?.document_id ?? null;
    row.message = 'มีไฟล์นี้ในระบบแล้ว';
  } else {
    row.state = 'bad';
    row.retryable = status === 0 || status >= 500;
    row.message =
      status === 0 ? 'อัปโหลดไม่สำเร็จ (เชื่อมต่อไม่ได้)'
      : status === 413 ? 'ไฟล์ใหญ่เกินกำหนด'
      : status === 401 ? 'หมดเวลาเข้าสู่ระบบ'
      : data?.detail && typeof data.detail === 'string' ? thai(data.detail)
      : 'อัปโหลดไม่สำเร็จ';
  }
}

export function retry(id) {
  const row = rowOf(id);
  if (row?.file && row.retryable) {
    row.retryable = false;
    row.state = 'wait';
    row.progress = 0;
    pump();
  }
}

/** Cancel one row, whatever stage it is in. */
export async function cancel(id) {
  const row = rowOf(id);
  if (!row) return;
  if (row.state === 'up') {
    requests.get(id)?.abort(); // send() removes the row once the abort lands
    return;
  }
  if (row.state === 'ok' && row.docId) {
    // Already stored: undo by moving the new document to the trash.
    row.state = 'undoing';
    try {
      await del(`/documents/${row.docId}`);
      row.state = 'undone';
      row.message = 'ยกเลิกแล้ว (ย้ายไปถังขยะ)';
      bumpReviewCount();
    } catch {
      row.state = 'ok';
      row.message = 'ยกเลิกไม่สำเร็จ ลองอีกครั้ง';
    }
    return;
  }
  uploads.items = uploads.items.filter((i) => i.id !== id);
}

/** Cancel everything still waiting or uploading. */
export function cancelAll() {
  for (const row of uploads.items.filter(active)) cancel(row.id);
}
