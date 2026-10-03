# Mac plane

The Mac plane is responsible for content production and artifact handoff, not normal Android runtime control.

## Production flow

```text
Douyin URL
-> mac/production-pipeline
-> authenticated ingest
-> analysis/evidence
-> Myanmar localization
-> render
-> mac/media-export
-> HTTPS capability URL
-> Y700 pull + SHA-256
```

Run the production pipeline from `mac/production-pipeline`. By default it resolves the media-export component to the sibling directory `mac/media-export`; override with `Y700_MEDIA_EXPORT_ROOT` when deploying elsewhere.

The media gateway requires `Y700_MEDIA_BASE_URL` or `--base-url`. The real hostname and Cloudflare credential JSON remain deployment-local.

The full orchestration contract is in `mac/production-pipeline/docs/CLOUD_GPT_RUNBOOK.md`.
