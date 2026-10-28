// Tiny helpers shared by the hand-built SVG charts (no chart library: keeps the bundle small).

/** Round axis maximum and evenly spaced ticks, e.g. 0, 5, 10, 15. */
export function niceTicks(max, count = 4) {
  if (!max || max <= 0) return { max: 1, ticks: [0, 1] };
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(+v.toFixed(10));
  return { max: top, ticks };
}

/** A bar whose top corners are rounded (data end) and whose base is square. */
export function topRounded(x, y, w, h, r = 4) {
  if (h <= 0) return '';
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

const compact = new Intl.NumberFormat('th-TH', { notation: 'compact', maximumFractionDigits: 1 });
export const short = (n) => compact.format(n);
export const full = (n) => Number(n).toLocaleString('th-TH', { maximumFractionDigits: 2 });

const MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
/** '2026-10' → 'ต.ค. 69' */
export function monthLabel(key) {
  const [y, m] = key.split('-').map(Number);
  return `${MONTHS[m - 1]} ${String(y + 543).slice(2)}`;
}
/** '2026-10-28' → '28 ต.ค.' */
export function dayLabel(key) {
  const [, m, d] = key.split('-').map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}
