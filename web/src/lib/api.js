// Thin fetch wrapper for the FastAPI backend under /api.
// Every request carries the CSRF header the backend requires on state-changing calls.

const CSRF = { 'X-Requested-With': 'dbresearch' };

export class ApiError extends Error {
  constructor(status, detail, data) {
    super(typeof detail === 'string' ? detail : 'Request failed');
    this.status = status;
    this.detail = detail;
    this.data = data;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

function query(params) {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => sp.append(key, v));
    else sp.append(key, value);
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export async function api(path, { method = 'GET', body, params, quiet401 = false } = {}) {
  const headers = { ...CSRF };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(`/api${path}${query(params)}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง');
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && !quiet401) onUnauthorized();
    throw new ApiError(res.status, data?.detail ?? res.statusText, data);
  }
  return data;
}

export const get = (path, params, opts) => api(path, { params, ...opts });
export const post = (path, body) => api(path, { method: 'POST', body });
export const put = (path, body) => api(path, { method: 'PUT', body });
export const patch = (path, body) => api(path, { method: 'PATCH', body });
export const del = (path) => api(path, { method: 'DELETE' });

/** Upload with progress (fetch can't report upload progress). Resolves {status, data};
 * status -1 = cancelled. `onStart` receives the request so the caller can abort it. */
export function uploadFile(path, file, onProgress, onStart, fields = {}) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    onStart?.(xhr);
    xhr.onabort = () => resolve({ status: -1, data: null });
    xhr.open('POST', `/api${path}`);
    xhr.setRequestHeader('X-Requested-With', 'dbresearch');
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status === 401) onUnauthorized();
      resolve({ status: xhr.status, data: xhr.response });
    };
    xhr.onerror = () => resolve({ status: 0, data: null });
    const form = new FormData();
    form.append('file', file);
    for (const [key, value] of Object.entries(fields)) if (value != null && value !== '') form.append(key, value);
    xhr.send(form);
  });
}

export const fileUrl = (id, { inline = false, version, closure, paper } = {}) =>
  `/api/documents/${id}/file${query({ inline: inline || undefined, version, closure, paper })}`;

/** Several documents as one zip, built by the server. */
export const zipUrl = (ids) => `/api/documents/zip${query({ id: ids })}`;

/** Start a download without leaving the page (the browser streams it to disk). */
export function downloadUrl(url) {
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.append(a);
  a.click();
  a.remove();
}

// The API speaks English; show people Thai for the messages we know.
const THAI = [
  [/^Only PDF files can be uploaded.*$/s, 'รับเฉพาะไฟล์ PDF'],
  [/^The PDF is damaged or password-protected.*$/s, 'ไฟล์ PDF เสียหายหรือตั้งรหัสผ่านไว้ ให้สแกนหรือบันทึกไฟล์ใหม่'],
  [/^The PDF has no pages.*$/s, 'ไฟล์ PDF ไม่มีหน้าเอกสาร'],
  [/^File is larger than (\d+) MB.*$/s, 'ไฟล์ใหญ่เกิน $1 MB'],
  [/^Upload too large.*$/s, 'ไฟล์ใหญ่เกินกำหนด'],
  [/^Wrong username or password.*$/s, 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'],
  [/^Too many failed logins.*$/s, 'ใส่รหัสผิดหลายครั้ง กรุณารอ 15 นาทีแล้วลองใหม่'],
  [/^Only the uploader or an admin.*$/s, 'เฉพาะผู้อัปโหลดหรือผู้ดูแลระบบเท่านั้นที่ทำรายการนี้ได้'],
  [/^Document not found.*$/s, 'ไม่พบเอกสารนี้ อาจถูกลบไปแล้ว'],
  [/^Not in the trash.*$/s, 'เอกสารนี้ไม่อยู่ในถังขยะแล้ว'],
  [/^Only the person who deleted it or an admin.*$/s, 'กู้คืนได้เฉพาะผู้ที่ลบหรือผู้ดูแลระบบ'],
  [/^Another live document has the same contract number \((.+)\).*$/s, 'กู้คืนไม่ได้: มีเอกสารเลขที่สัญญา $1 อยู่ในระบบแล้ว'],
  [/^Another live document has the same contract number.*$/s, 'กู้คืนไม่ได้: มีเอกสารเลขที่สัญญาเดียวกันอยู่ในระบบแล้ว'],
  [/^This link is invalid or has expired.*$/s, 'ลิงก์นี้ใช้ไม่ได้หรือหมดอายุแล้ว'],
  [/^Not authenticated.*$|^Login required.*$/s, 'กรุณาเข้าสู่ระบบ'],
];
export function thai(detail) {
  if (typeof detail !== 'string') return detail;
  for (const [re, text] of THAI) if (re.test(detail)) return detail.replace(re, text);
  return detail;
}

/** Human message for an error, in Thai where we know the case. */
export function errorText(err) {
  if (!(err instanceof ApiError)) return 'เกิดข้อผิดพลาด ลองอีกครั้ง';
  if (err.status === 0) return err.detail;
  if (err.status === 403) return 'คุณไม่มีสิทธิ์ทำรายการนี้';
  if (err.status === 404) return 'ไม่พบข้อมูลนี้ อาจถูกลบไปแล้ว';
  if (err.status === 413) return 'ไฟล์ใหญ่เกินกำหนด';
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join(' · ');
  }
  if (err.status === 429) return thai(err.detail) || 'ลองใหม่อีกครั้งภายหลัง';
  return typeof err.detail === 'string' ? thai(err.detail) : 'เกิดข้อผิดพลาด ลองอีกครั้ง';
}
