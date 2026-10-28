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

/** Upload with progress (fetch can't report upload progress). Resolves {status, data}. */
export function uploadFile(path, file, onProgress) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
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
    xhr.send(form);
  });
}

export const fileUrl = (id, { inline = false, version } = {}) =>
  `/api/documents/${id}/file${query({ inline: inline || undefined, version })}`;

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
  return typeof err.detail === 'string' ? err.detail : 'เกิดข้อผิดพลาด ลองอีกครั้ง';
}
