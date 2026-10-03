# Bootstrap helpers

These are the public, non-secret helpers used to establish or inspect the Y700 Debian development plane.

- `chroot-install-base.sh`: install the minimum Linux toolchain inside the Debian rootfs.
- `y700-mount.sh`: bind Android host resources and the shared Y700 directory into the chroot.
- `y700-exec.sh`: execute a command in the chroot.
- `chroot-status.sh` / `chroot-verify.sh`: status and verification helpers.
- `install-cloudflared-y700.sh`: install the Cloudflare client used by CodexPro.
- `restart-cloudflared-y700.sh`: restart the local named-tunnel process.

Device root itself is documented in `docs/ROOT-AND-RECOVERY.md`. Raw partition images, vendor tools, programmer binaries and device identifiers are deliberately not stored in this public repository.
