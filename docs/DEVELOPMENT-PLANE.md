# Y700 development plane

## Verified baseline

- Android 16 / aarch64
- locked bootloader
- KernelSU persistent root
- SELinux Enforcing
- Debian GNU/Linux 13 (trixie) chroot
- Node.js, npm, Python, Git and ffmpeg available
- CodexPro running in the chroot
- Cloud ChatGPT can open/read/write/bash the workspace directly

## Filesystem layout

Android host:

```text
/data/local/y700-linux/rootfs
/data/local/y700-agent
```

Inside chroot:

```text
/opt/y700
/opt/y700/workspaces/y700-agent
/opt/y700/jobs
/opt/y700/runtime
```

The host shared directory is bind-mounted to `/opt/y700`.

## Cloud ChatGPT filesystem access

- CodexPro is launched with `/` as an allowed root, so Cloud ChatGPT can open/read/write/tree any non-blocked path in the Debian chroot, not only the canonical project workspace.
- Android host paths are available to CodexPro full-bash through the host init root at `/proc/1/root/...`; for example Android `/data` is reached as `/proc/1/root/data`.
- No recursive host-root bind mount is used. A test bind of the Android root was removed after confirming that child mounts such as `/data` are separate mounts and would not be represented safely by a plain bind.
- CodexPro's built-in sensitive-file blocked globs remain in force for generic file tools. Root-shell access does not relax the project rule against routine mutation of boot-chain or critical system partitions.

## Boot/runtime

The KernelSU autostart module invokes the boot script. The runtime sequence mounts the chroot/shared paths, starts the Android host executor, starts CodexPro + Cloudflare tunnel, starts SSH, then starts the health loop.

## Guardrails

- normal development must not flash partitions;
- disk and thermal guards can block publication work;
- completed filesystem jobs are archived out of the active job directory to keep root-executor latency bounded;
- recovery and boot-chain work is a separate procedure from normal application development.
