# Y700 Media / Artifact Gateway

Minimal Mac-side pull transport for PRD v0.3 and Android build artifacts.

- Mac remains the content-production and Android build node.
- The server exposes only exact capability URLs and does not list directories.
- Each exported job gets a random per-job capability path with a short expiry.
- Y700 pulls the manifest and files, verifies byte size and SHA-256, then exposes only a completed bundle.
- SSH/CodexPro remains the control plane; large files use the HTTP artifact data plane.

Default local listener: 127.0.0.1:8790
Public base URL: provide Y700_MEDIA_BASE_URL (for example a Cloudflare Tunnel hostname). The public hostname itself is deployment-local.

Media mode remains backward-compatible:

- video.mp4
- caption.txt
- metadata.json
- manifest.json
- .capability (Mac only; never copied into Y700 job)

Generic artifact mode uses repeated --artifact NAME=PATH arguments. Its manifest contains:

- schema_version and job_id
- expiry
- artifact filename
- byte size
- SHA-256 digest
- exact capability URL

Y700 downloads generic bundles with scripts/pull-artifact-bundle.py. Each file is downloaded to a temporary .part file, verified, and only then moved into the completed bundle directory. A partial or hash-mismatched APK is never handed to the Android installer.
