// Display helpers. Data is Gregorian; the UI shows Buddhist Era (พ.ศ. = ค.ศ. + 543).

export const BE = 543;
const MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];

export const STATUS = {
  processing: 'กำลังอ่านเอกสาร',
  needs_review: 'รอตรวจสอบ',
  ready: 'พร้อมใช้งาน',
  failed: 'อ่านไม่สำเร็จ',
};
export const KIND = { contract: 'สัญญา', grant: 'ทุนวิจัย' };
export const FUNDING = { internal: 'ทุนภายใน', external: 'ทุนภายนอก' };
export const ROLE = {
  owner: 'หัวหน้าโครงการ',
  co_investigator: 'ผู้ร่วมวิจัย',
  party: 'คู่สัญญา',
  signer: 'ผู้ลงนาม',
};
export const LINK_STATE = {
  active: 'ใช้งานได้',
  expired: 'หมดอายุ',
  revoked: 'ยกเลิกแล้ว',
  exhausted: 'ดาวน์โหลดครบแล้ว',
  locked: 'ล็อก (รหัสผิดหลายครั้ง)',
  deleted: 'เอกสารถูกลบ',
};
export const FIELD = {
  title: 'ชื่อเรื่อง',
  title_en: 'ชื่อเรื่อง (อังกฤษ)',
  reference_no: 'เลขที่สัญญา',
  document_date: 'วันที่เอกสาร',
  effective_from: 'วันเริ่มสัญญา',
  effective_to: 'วันสิ้นสุดสัญญา',
  fiscal_year: 'ปีงบประมาณ',
  budget_total: 'งบประมาณรวม',
  owner: 'หัวหน้าโครงการ',
};

/** "2025-09-01" or an ISO datetime → "1 ก.ย. 2568" */
export function thDate(value) {
  if (!value) return '–';
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number);
  if (!y) return '–';
  return `${d} ${MONTHS[m - 1]} ${y + BE}`;
}

export function thDateTime(value) {
  if (!value) return '–';
  const dt = new Date(value);
  const hh = String(dt.getHours()).padStart(2, '0');
  const mm = String(dt.getMinutes()).padStart(2, '0');
  return `${dt.getDate()} ${MONTHS[dt.getMonth()]} ${dt.getFullYear() + BE} ${hh}:${mm} น.`;
}

/** "อีก 3 ชม." / "อีก 2 วัน" / "หมดแล้ว" */
export function timeLeft(value) {
  const ms = new Date(value) - Date.now();
  if (ms <= 0) return 'หมดเวลาแล้ว';
  const h = ms / 36e5;
  if (h < 1) return `อีก ${Math.max(1, Math.round(ms / 6e4))} นาที`;
  if (h < 48) return `อีก ${Math.round(h)} ชม.`;
  return `อีก ${Math.round(h / 24)} วัน`;
}

export function money(value) {
  if (value === null || value === undefined || value === '') return '–';
  const n = Number(value);
  return `${n.toLocaleString('th-TH', { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })} บาท`;
}

export function bytes(n) {
  if (!n && n !== 0) return '–';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

/** Parse "1/9/2568" (พ.ศ.) or "1/9/2025" → "2025-09-01". Returns null if invalid, '' if empty. */
export function parseThaiDate(text) {
  const s = (text || '').trim().replace(/[๐-๙]/g, (c) => '๐๑๒๓๔๕๖๗๘๙'.indexOf(c));
  if (!s) return '';
  const m = s.match(/^(\d{1,2})[/.\-\s](\d{1,2})[/.\-\s](\d{4})$/);
  if (!m) return null;
  let [, d, mo, y] = m.map(Number);
  if (y > 2400) y -= BE;
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

/** "2025-09-01" → "1/9/2568" for editing */
export function toThaiInput(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  return `${d}/${m}/${y + BE}`;
}

/** Escape text, then turn the API's [[match]] markers into <mark>. */
export function snippetHtml(text) {
  const esc = String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  return esc.replace(/\[\[(.+?)\]\]/g, '<mark>$1</mark>');
}

export function personName(p) {
  return [p.prefix_th, p.name_th || p.name_en].filter(Boolean).join('');
}
