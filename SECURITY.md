# Security and public-repository policy

This is a public repository. Never commit credentials or device-private runtime material.

## Must stay outside Git

- SSH private keys and `authorized_keys`
- CodexPro bearer/token contents
- Cloudflare tunnel credential JSON
- cookies/session exports/Douzy bearer data
- per-job capability URLs
- device serial numbers
- raw boot/GPT/efisp/init_boot/partition backups
- firmware images and proprietary vendor tools
- downloaded or rendered user media
- Android screenshots, UI XML dumps and runtime logs

## Configuration pattern

Commit templates, paths and non-secret policy only. Secret values are provisioned locally with restrictive permissions.

The Y700 CodexPro token is read from a local token file; the token contents must never be printed into Git-tracked files.

## Incident rule

If a secret is ever committed, rotate/revoke the secret first, then rewrite the public Git history. Deleting only the latest file is not sufficient.
