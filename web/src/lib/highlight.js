// Highlight a search query inside a title the way the server matches it (search_text.compact):
// NFC, Thai digits ๐–๙ → 0–9, all whitespace dropped, lowercased. The marked range is mapped
// back to the original text, so it covers the spaces inside the match.

const squash = (ch) =>
  ch
    .normalize('NFC')
    .replace(/[๐-๙]/g, (d) => String(d.charCodeAt(0) - 0x0e50))
    .replace(/\s+/g, '')
    .toLowerCase();

export function compact(text) {
  return squash(String(text ?? ''));
}

/** → [{ text, hit }] segments covering `text`; no match gives one segment, hit false. */
export function highlightSegments(text, query) {
  text = String(text ?? '');
  const needle = compact(query);
  if (!needle) return [{ text, hit: false }];
  // One entry per code point of the original: its compacted form, so offsets map back.
  let squashed = '';
  const owner = []; // owner[k] = [start, end) in `text` of the character that produced squashed[k]
  let at = 0;
  for (const ch of text) {
    const c = squash(ch);
    for (let k = 0; k < c.length; k++) owner.push([at, at + ch.length]);
    squashed += c;
    at += ch.length;
  }
  const out = [];
  let last = 0;
  let from = 0;
  for (;;) {
    const i = squashed.indexOf(needle, from);
    if (i < 0) break;
    const start = owner[i][0];
    const end = owner[i + needle.length - 1][1];
    if (start > last) out.push({ text: text.slice(last, start), hit: false });
    out.push({ text: text.slice(start, end), hit: true });
    last = end;
    from = i + needle.length;
  }
  if (last < text.length) out.push({ text: text.slice(last), hit: false });
  return out.length ? out : [{ text, hit: false }];
}
