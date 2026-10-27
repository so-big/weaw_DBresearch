---
name: add-template
description: Add or tune an OCR auto-fill extraction template from a sample scanned PDF (contract or grant, external or internal funding). Use when the user provides a new document layout or auto-fill gets fields wrong.
disable-model-invocation: true
---

# Add an extraction template

Input: `$ARGUMENTS` = path to a sample PDF (plus the expected kind/funding type if the user gave them).

1. **Treat the sample as sensitive.** Work on a copy in the scratchpad or a tmpfs path. Never commit the original PDF.
2. OCR it the same way the worker does: `ocrmypdf -l tha+eng --sidecar out.txt --force-ocr in.pdf out.pdf`. Then normalise the text: NFC, Thai digits → Arabic, collapse whitespace.
3. Ask the user which value each target field should have in this sample: title, reference_no, owner (person), document_date, effective_from/to, plus extras such as budget and agency.
4. Draft the template as a row for `extraction_templates`:
   - `match_rules`: 3–6 keywords/regexes that identify this layout (e.g. `สัญญารับทุน`, agency name) + a minimum score. They must not match other existing templates.
   - `field_rules`: per field, an anchor keyword + regex + post-processing (`date_be`, `thai_digits`, `money`, `person_name`).
   - For the agency, prefer matching `categories.aliases` over hard-coding names.
5. Create a **redacted** text fixture in `tests/fixtures/templates/<name>.txt`: replace real names, IDs, and amounts with fake ones but keep the layout. Add a test that asserts every extracted field.
6. Run all template tests to make sure the new rules don't steal matches from existing templates.
7. Report each field's extracted value and confidence, and anything the OCR misread.
