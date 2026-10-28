// Upload queue shared by the whole app: survives closing the window and changing pages.
import { uploadFile, thai } from './api.js';
import { bumpReviewCount } from './state.svelte.js';

const PARALLEL = 2;
const MAX_MB = 100;

export const uploads = $state({ open: false, items: [] });
let nextId = 0;
let running = 0;

export const busyCount = () => uploads.items.filter((i) => i.state === 'wait' || i.state === 'up').length;
export const doneOk = () => uploads.items.filter((i) => i.state === 'ok');

export function openUpload() {
  uploads.open = true;
}
export function closeUpload() {
  uploads.open = false;
}

/** Clear finished rows (after "review later" / "review now"). Rows still uploading stay. */
export function clearFinished() {
  uploads.items = uploads.items.filter((i) => i.state === 'wait' || i.state === 'up');
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
    send(item);
  }
}

async function send(item) {
  // Work on the proxied row so the UI updates as progress arrives.
  const row = uploads.items.find((i) => i.id === item.id);
  row.state = 'up';
  const { status, data } = await uploadFile('/documents', row.file, (p) => (row.progress = p));
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
  running--;
  pump();
}

export function retry(id) {
  const row = uploads.items.find((i) => i.id === id);
  if (row?.file && row.retryable) {
    row.retryable = false;
    row.state = 'wait';
    row.progress = 0;
    pump();
  }
}

export function remove(id) {
  uploads.items = uploads.items.filter((i) => i.id !== id || i.state === 'up');
}
