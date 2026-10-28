---
name: add-template
description: Add or tune an OCR auto-fill section template (and checkbox category mapping) from a sample PDF bundle — contract or grant, external or internal funding. Use when the user provides a new document layout or auto-fill gets fields/tags wrong.
disable-model-invocation: true
---

# Add an extraction template

Input: `$ARGUMENTS` = path to a sample PDF (plus kind/funding type if the user gave them). Design reference: `docs/DESIGN.md` §6.

1. **Treat the sample as sensitive.** Never commit it. OCR runs on the server: `scp` it to `cs31@100.104.87.92:~/dbresearch/samples/` and run the worker's pipeline there (`docker compose exec worker …`). This machine is too slow.
2. Run `docker compose exec worker python spikes/autofill_smoke.py /samples/<file>.pdf` (add `--json` for everything). It shows sections, extracted fields with confidence, people, checkbox matches, hints and warnings. List the **sections** found and their pages for the user.
3. For each section that has no matching template, ask the user which fields it carries and their values in this sample (title, title_en, reference_no, owner, fiscal year, dates, budget_total, …).
4. Draft one `extraction_templates` row **per section type** (rule format: docstring of `dbresearch/autofill/rules.py`; validate with `validate_rules`). Ship it as a new data migration, like `…_tune_contract_body_rules.py`:
   - `attachment_no`, and `kind` / `funding_type` if the section implies them (e.g. `งบประมาณรายได้คณะ` → internal).
   - `match_rules`: 3–6 keywords/regexes unique to this section + a minimum score. Check they don't match other templates' sections.
   - `field_rules` = `{"rules": [...]}`. One rule per field and label variant. Layouts: `label` (value after a line-start label, or on the next line; `continue` = wrapped lines), `footer` (majority vote over all pages), `sentence` (regex over running text; `words_group` checks amounts written in Thai words), `team` (research-team block). Post-processors: `strip_leaders`, `compact`, `upper`, `be_year`, `thai_date`, `money`, `strip_brackets`.
   - `checkbox_groups = true` if the section has checkbox groups.
5. Checkbox groups: for every heading and option seen (checked **or** unchecked), make sure a `category_groups` / `categories` row exists, or add the variant to `aliases`. Propose these as seed-data changes. **Ask before adding new categories.** Only checked boxes become tags at runtime.
6. Add a unit test in `tests/test_autofill_unit.py` style: synthetic `Page`/`Line` objects with the sample's **layout** but **fake values** (never real names, IDs or amounts). Assert every extracted field and every checked-box suggestion.
7. Run all template tests to confirm the new rules don't steal matches from other templates.
8. Report each field (value, confidence, source page), the checkbox suggestions, any validation warnings, and anything OCR misread.
