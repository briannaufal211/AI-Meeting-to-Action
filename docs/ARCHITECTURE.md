# Architecture and privacy

The browser posts a local-token-protected upload to FastAPI. A single Python worker processes queued jobs. n8n can coordinate the five stages: `transcribe`, `summarize`, `quality`, `plan`, and `render`.

Each job has its own directory under `data/jobs/`. Transcript evidence, structured responses, review reports, and document outputs are persisted there. Completed stages and response caches can be reused after interruption. A lost/uncertain API response may still have incurred charges; local accounting cannot guarantee a complete provider invoice.

Source references connect report claims (`Fxxxx`) with transcript segments (`Sxxxxx`). Literal quotation checks improve traceability but do not prove that the transcript matches the original audio. Speaker labels and quoted conclusions still need human review.

Summary-only mode bypasses recommendation planning and PowerPoint/Excel. Extended mode adds proposed planning outputs. An n8n `Succeeded` status describes execution, not substantive approval of every result.

## Public packaging

The code was copied into a separate public release directory. The running personal installation was not modified. Personal source templates and images were excluded. Neutral Word/PPT layouts and an openpyxl exporter remove dependencies on the desktop environment used during development.

`examples/meeting-demo/` contains invented participants, an invented inventory discussion, saved source-linked outputs, and an editorially revised plan. Unknown scheduling and effort fields remain blank in the editorial example. This example must not be represented as a fresh successful AI planning audit.

## Network boundaries

- UI and worker: local loopback, default port 8765.
- Native n8n: local loopback, default port 5678.
- AI calls: provider API over the internet, configured with your own key.
- Optional local speech recognition may download model weights on first use.
- TXT import and local document rendering do not themselves need AI calls.

The worker is a local prototype. Any public hosting requires a separate security design; changing a bind address is not sufficient.
