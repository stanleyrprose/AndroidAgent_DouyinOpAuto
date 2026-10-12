# Y700 Antigravity CLI (agy-bkk) — Verified Device Baseline

**Accepted:** 2026-10-11 (device observations from 2026-10-10)  
**Status:** PASS — interactive use confirmed on the physical Y700 by the owner  
**Scope:** Independent, on-demand Google Antigravity CLI access from Y700's Debian chroot through an existing Bangkok VPS egress. This is **not** a TikTok, Vision, Android Automation Core, or publisher acceptance gate.

## Facts verified on Y700

- Device/runtime: Lenovo Y700 (TB323FU), Android 16, Debian 13 `aarch64` chroot, existing KernelSU root / Termux entry point.
- Official Antigravity CLI: `agy 1.3.3`; version invocation completed successfully. `pi` and its existing ChatGPT OAuth installation were not replaced.
- Google OAuth was completed by the device owner; credentials remain local and are not committed.
- On-device, dedicated SSH key authentication to the Bangkok VPS **succeeded**; SOCKS listener at `127.0.0.1:1088` and Privoxy listener at `127.0.0.1:8118` were observed.
- An HTTP proxy request to an external egress-IP echo service resolved to the intended Bangkok VPS public IP, while a direct request resolved to a different IP. The actual addresses are deliberately excluded from public Git.
- `agy-bkk --version` returned `1.3.3`. A real model request through `agy-bkk`, with `gemini-3.8-flash-low`, returned the expected literal `Y700_BKK_GEMINI_OK` and exited successfully.
- The owner subsequently confirmed that interactive `agy-bkk` use on Y700 was successful.
- The fail-closed launcher checks expected proxy egress before invoking the official binary; before the proxy existed, it refused to launch (exit 70). This does not prove packet-level enforcement against every possible network path once the CLI has started.

## Verified runtime topology

```text
Y700 Termux
  -> existing root/chroot entrypoint
  -> Debian /usr/local/bin/agy-bkk
  -> local Privoxy HTTP proxy (127.0.0.1:8118)
  -> local SSH SOCKS5 (127.0.0.1:1088; autossh supervision)
  -> existing Bangkok VPS (restricted forwarding-only account)
  -> Google Antigravity/Cloud Code endpoints
```

- The VPS proxy account uses a dedicated Y700 SSH key. No Mac mini key was copied to Y700.
- This chain does **not** require Mac mini or USB connection during routine use. Network connectivity from the tablet to the VPS and an authorized Google account/service remain prerequisites.
- Only the `agy-bkk` process environment is configured for this proxy; the Android-wide network, existing Cloudflare tunnel, Pi, and TikTok publishing plane were not modified.
- `autossh` is on-demand and reconnects while its process remains alive. **No unconditional reboot/autostart persistence is claimed.**

## Operator entrypoint

From Y700's installed Termux:

```bash
su -c '/data/local/y700-linux/exec.sh /usr/local/bin/agy-bkk'
```

Or enter Debian first and use `agy-bkk`. The original `agy` executable remains available separately; for region-dependent use, the launcher with an egress check is the validated entrypoint.

Non-secret device-local inventory (not Git deployment artifacts):

| Runtime path | Role |
| --- | --- |
| `/usr/local/bin/agy` | Original official CLI |
| `/usr/local/bin/agy-bkk` | Proxy-checking on-demand launcher |
| `/etc/privoxy/agy-bkk.config` | Local HTTP-to-SOCKS bridge |
| `/root/.ssh/id_ed25519_agy_bkk` | Sensitive private key; **never commit or display** |
| `/root/.ssh/known_hosts` | Pinned SSH host trust |
| Pi/agy OAuth stores | Sensitive authentication state; **never commit** |

The working launcher and Privoxy configuration currently exist on the device. This entry is an **observed runtime baseline**, not a claim that their device-specific file bytes are reproducibly deployed from Git. Preserve a sanitized, reviewed source/config template separately before any rebuild or destructive reinstall.

## Not yet accepted / limits

- Reboot-then-run, long device sleep/Android background-kill, long-lived token renewal, and Wi-Fi ↔ hotspot changes have **not** been accepted as tested recovery scenarios.
- `autossh` reconnects an existing running process, but it is not proof of Android power-management survival or post-reboot autostart.
- Verified connection and model response do not establish compliance/entitlement for all Google accounts, regions, quotas, or service terms. Future availability is service-dependent.
- A VPS outage, blocked SSH connection, changed egress or failed Google entitlement may render `agy-bkk` unavailable; fail-closed is preferable to unexpected direct egress.
- The baseline does not authorize changes to Android partitions, SSH server policy, publisher COMMIT, production deployment, or CI lifecycle.

## Minimal operational diagnosis

If `agy-bkk` fails, inspect the local `autossh`/SSH and Privoxy process/listening state and verify the HTTP proxy's actual egress before retrying. Do not copy OAuth refresh tokens, private keys, authorization URLs/codes, raw account IDs, or VPS-specific endpoints into Git or support messages. Do not disable the egress check just to make the CLI start.

**Provenance:** Physical-Y700 checks through CodexPro_Y700 plus the owner's direct interactive success confirmation, 2026-10-10/11. Evidence is summarized here in public-safe form. This baseline is operationally accepted only for the enumerated behaviors.
