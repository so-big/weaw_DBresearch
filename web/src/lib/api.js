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
  [/^Not authenticated.*$|^Login required.*$|^Not logged in.*$/s, 'กรุณาเข้าสู่ระบบ'],
  [/^Login service unavailable.*$/s, 'ระบบเข้าสู่ระบบของมหาวิทยาลัยใช้งานไม่ได้ชั่วคราว ลองใหม่ภายหลัง'],
  [/^This exact file is in the trash.*$/s, 'ไฟล์นี้อยู่ในถังขยะแล้ว กู้คืนได้จากถังขยะ'],
  [/^This exact file is already stored.*$/s, 'ไฟล์นี้มีอยู่ในระบบแล้ว'],
  [/^Links can last at most (\d+) hours.*$/s, 'ลิงก์อยู่ได้นานสุด $1 ชั่วโมง'],
  [/^No such version.*$/s, 'ไม่พบเวอร์ชันนี้'],
  [/^This link has no password.*$/s, 'ลิงก์นี้ไม่ได้ตั้งรหัสผ่าน'],
  [/^Wrong password.*$/s, 'รหัสผ่านไม่ถูกต้อง'],
  [/^Password required.*$/s, 'ลิงก์นี้ต้องใส่รหัสผ่าน'],
  [/^This link is view-only.*$/s, 'ลิงก์นี้ดูได้อย่างเดียว ดาวน์โหลดไม่ได้'],
  [/^Link not found.*$/s, 'ไม่พบลิงก์นี้'],
  [/^Version not found.*$/s, 'ไม่พบเวอร์ชันนี้'],
  [/^Admin only.*$/s, 'เฉพาะผู้ดูแลระบบเท่านั้น'],
  [/^A cancelled project can't be closed.*$/s, 'โครงการที่ยกเลิกแล้วปิดโครงการไม่ได้'],
  [/^A closed project can't be cancelled.*$/s, 'โครงการที่ปิดแล้วยกเลิกไม่ได้ ให้เปิดโครงการอีกครั้งก่อน'],
  [/^Only proposal grants can be cancelled.*$/s, 'ยกเลิกได้เฉพาะทุนเสนอขอ'],
  [/^Only proposal grants have a timeline.*$/s, 'เฉพาะทุนเสนอขอที่มีลำดับเหตุการณ์'],
  [/^The project is not closed.*$/s, 'โครงการนี้ยังไม่ได้ปิด'],
  [/^The linked contract doesn't exist.*$/s, 'ไม่พบสัญญาที่เชื่อมโยง'],
  [/^Event not found.*$/s, 'ไม่พบเหตุการณ์นี้'],
  [/^Document is not in the trash.*$|^Only documents in the trash can be purged.*$/s, 'เอกสารนี้ไม่อยู่ในถังขยะแล้ว'],
  [/^Another document already has this contract number.*$/s, 'มีเอกสารอื่นใช้เลขที่สัญญานี้แล้ว'],
  [/^Unknown category.*$/s, 'ไม่พบหมวดหมู่ที่เลือก'],
  [/^Only one category can be chosen in group '(.+)'.*$/s, 'เลือกได้เพียงหมวดเดียวในกลุ่ม “$1”'],
  [/^Unknown person.*$/s, 'ไม่พบบุคคลที่เลือก'],
  [/^A person needs a Thai or English name.*$/s, 'บุคคลต้องมีชื่อภาษาไทยหรือภาษาอังกฤษ'],
  [/^Choose the funding source or internal\/external funding.*$/s, 'เลือกแหล่งทุน หรือระบุว่าทุนภายใน/ภายนอก'],
  [/^Proposal fields only apply to proposal-development grants.*$/s, 'ข้อมูลเสนอขอใช้ได้เฉพาะทุนพัฒนาข้อเสนอโครงการ'],
  [/^Category group not found.*$/s, 'ไม่พบกลุ่มหมวดหมู่นี้'],
  [/^Name is empty.*$/s, 'กรุณากรอกชื่อ'],
  [/^User not found.*$/s, 'ไม่พบผู้ใช้นี้'],
  [/^User has no local login.*$/s, 'ผู้ใช้นี้ไม่ได้ใช้การเข้าสู่ระบบในเครื่อง'],
  [/^This request was already decided.*$/s, 'คำขอนี้ได้รับการตัดสินแล้ว'],
  [/^Give both username and password, or neither.*$/s, 'ใส่ทั้งชื่อผู้ใช้และรหัสผ่าน หรือเว้นว่างทั้งคู่ (ผู้ใช้ SSO)'],
  [/^Email, username or university ID already in use.*$/s, 'อีเมล ชื่อผู้ใช้ หรือรหัสมหาวิทยาลัยนี้มีในระบบแล้ว'],
  [/^You can't remove your own admin access.*$/s, 'ถอนสิทธิ์ผู้ดูแลระบบของตัวเองไม่ได้'],
  [/^Use approve or reject for a pending request.*$/s, 'คำขอที่รออนุมัติให้ใช้ปุ่มอนุมัติหรือปฏิเสธ'],
  [/^Not an IP address.*$/s, 'ที่อยู่ IP ไม่ถูกต้อง'],
  [/^Unknown setting.*$/s, 'ไม่พบการตั้งค่านี้'],
  [/^Must be between (\S+) and (\S+).*$/s, 'ต้องอยู่ระหว่าง $1 ถึง $2'],
  [/^Name or key already exists.*$/s, 'ชื่อหรือรหัสนี้มีอยู่แล้ว'],
  [/^Used by (\d+) document\(s\).*$/s, 'ใช้อยู่ใน $1 เอกสาร ให้ปิดใช้งานแทนการลบ'],
  [/^match_rules needs a non-empty 'keywords' list.*$/s, 'กฎการจับคู่ต้องมีรายการคำสำคัญอย่างน้อยหนึ่งคำ'],
  [/^Not found.*$/s, 'ไม่พบข้อมูลนี้'],
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
    return 'ข้อมูลที่กรอกไม่ถูกต้อง';
  }
  if (err.status === 429) return thai(err.detail) || 'ลองใหม่อีกครั้งภายหลัง';
  return typeof err.detail === 'string' ? thai(err.detail) : 'เกิดข้อผิดพลาด ลองอีกครั้ง';
}
