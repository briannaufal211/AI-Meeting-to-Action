# Public edition validation

Validated locally on 3 November 2026 with Python 3.12 and Node.js 22-compatible dependencies.

- **126 tests passed** in 9.44 seconds. AI responses were mocked; no paid model requests were made.
- The synthetic example was exported successfully to editable Word, PowerPoint and Excel using `python export_example.py` with an empty API key.
- Presentation tests verify long-text preservation, native editable tables, every planned task, and slide geometry bounds.
- Workbook tests verify five sheets, editable formulas, blank unconfirmed schedules and capacity, editorial status, and formula-injection escaping.
- Endpoint tests cover upload limits, token checks, filename traversal, download restrictions and queue limits.
- Local test dependencies were reused from the development environment; a fresh installation is exercised by the included GitHub Actions workflow. A local pass does not establish a remote CI pass.

The saved meeting is fictional. Its final content was reviewed editorially against the saved transcript. This is **not** evidence of a new automated AI audit passing. Schedules and effort that were not confirmed remain blank. The offline exporter explicitly supports this saved editorial example separately from the stricter schema for newly generated AI proposals.

The public edition uses neutral templates and an openpyxl workbook exporter. Private recordings, credentials, local job history and personal reference templates are excluded. Real provider availability, billing, model quality and GPU performance were not re-tested for this publication.
