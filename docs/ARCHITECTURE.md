# Architecture

## Planes

### 1. Y700 development/control plane

```text
Cloud ChatGPT
  -> authenticated CodexPro endpoint
  -> Debian ARM64 chroot
  -> /opt/y700/workspaces/y700-agent
  -> filesystem-first job contract
  -> Android-host root executor
  -> Android UI / package / filesystem controls
```

The chroot provides normal Linux tooling while privileged Android actions are executed in the Android host namespace through a deliberately small bridge.

### 2. SSH plane

A local OpenSSH server runs inside the chroot on port 2222 with public-key-only root login. It is intended for changing Wi-Fi / phone-hotspot networks. The repository contains only the server configuration and lifecycle scripts, never authorized keys.

### 3. Mac content-production plane

```text
Douyin share URL
  -> authenticated downloader
  -> analysis/transcription/contact sheet
  -> evidence-grounded localization.json
  -> Burmese render
  -> 1080x1920 artifact
  -> short-lived capability URL
```

### 4. Media handoff plane

The Mac media server exposes only exact random per-job capability paths. Y700 pulls manifest/files over HTTPS, verifies SHA-256, and moves the job to ready state. No permanent public media library or directory listing is required.

### 5. TikTok publisher plane

State-driven UI:

```text
HOME -> CREATE -> GALLERY -> EDIT -> POST_CONFIG
                                     |
                                     +-- DRY_RUN hard stop
                                     +-- explicit COMMIT -> verification
```

Ambiguous COMMIT results are reconciled from TikTok Profile/durable state before retry.

## Why filesystem-first

The workload is single-device and low-throughput. Files provide durable, inspectable state and simplify recovery. MQ/socket infrastructure would add failure modes without solving a measured requirement.
