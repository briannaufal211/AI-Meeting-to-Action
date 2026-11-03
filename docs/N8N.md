# Running with n8n

First verify the Python application at http://127.0.0.1:8765. The worker's API credentials belong in its local `.env`, not in the public workflow JSON.

## Native Windows

Use the pinned runtime definition in `n8n-runtime-lock.json` with the provided `Pasang-n8n.ps1`, `Siapkan-Workflow-n8n.ps1`, and `Jalankan-n8n.ps1` scripts. Review scripts before running them. Alternatively, install n8n using its supported local installation method, import `n8n-workflow.json` in the editor, and activate/publish it.

The helper scripts keep the n8n user folder under `data/n8n/` and listen on loopback. They may import or update the workflow named `diskusiLocalWorkflow`; use a separate development n8n instance to avoid replacing a workflow with that ID in an existing installation.

Set `N8N_WEBHOOK_URL`, `N8N_RESUME_URL`, and `APP_N8N_JOB_URL` in `.env` to the production webhook URLs matching your imported workflow. Keep **Gunakan n8n lokal** checked only when the workflow is available. Test with synthetic TXT first; AI stages are billed separately.

## Docker Desktop

`docker compose up -d` starts n8n bound to 127.0.0.1:5678. Import `n8n-workflow-docker.json`. Its `host.docker.internal` URLs assume Docker Desktop can reach the host worker. The worker's host/loopback behavior and Docker networking can vary by platform; verify reachability before submitting data. The default local-only worker is not automatically exposed to containers on every OS.

The compose file's `stable` tag follows upstream and is not a reproducibility pin. Pin a version or digest that you have validated for your environment. Do not expose the worker publicly to resolve a connectivity issue.

## Form workflow

`n8n-form-workflow.json` provides the optional n8n form entry point. Inspect its configured URLs and file limits before activating it. Exported files contain workflow definitions only, without credentials, pinned outputs, or execution history.
