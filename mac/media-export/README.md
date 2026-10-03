# Y700 Media Export

Minimal Mac-side artifact transfer for PRD v0.3.

- Mac remains the content-production node.
- The server exposes only exact capability URLs.
- It does not list directories.
- Each exported job gets a random per-job capability path.
- Y700 pulls manifest + files, verifies SHA-256, then moves the job to ready.
- The capability URL is a short-lived transport capability, not a permanent account credential.

Default local listener: 127.0.0.1:8790
Public base URL: provide `Y700_MEDIA_BASE_URL` (for example a Cloudflare Tunnel hostname). The public hostname itself is deployment-local and is not committed.

Files per job:
- video.mp4
- caption.txt
- metadata.json
- manifest.json
- .capability (Mac only; never copied into Y700 job)
