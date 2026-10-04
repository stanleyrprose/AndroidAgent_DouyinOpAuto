# Root and recovery

> Public-safe record for Lenovo Legion Y700 / TB323FU. Verified 2026-10-02. Raw device backups and machine-specific identifiers are intentionally excluded.

## Known-good operating baseline

- Android 16, aarch64
- kernel 6.12-class GKI
- bootloader locked
- OEM unlocking setting enabled
- Verified Boot remained green in the verified state
- file-based encryption active
- persistent root works
- KernelSU v3.3.0, LKM mode
- Zygisk Next 1.5.0 installed as a KernelSU module; no Magisk or second root implementation is installed

The operational conclusion is important: **bootloader unlock is not required for the current root/runtime design.**

## Root implementation that was actually used

Root was installed through a Qualcomm EDL/Firehose-capable tooling path rather than normal fastboot flashing.

Observed flow:

1. determine active slot and kernel/GKI baseline;
2. install KernelSU Manager;
3. acquire matching KernelSU LKM/init components;
4. enter Qualcomm EDL 9008;
5. read the stock root-related partitions first;
6. patch the active-slot `init_boot` image for KernelSU;
7. provision the verified PRC GBL runtime in `efisp`;
8. write only the proven root components;
9. reboot and verify persistent uid 0.

The verified root operation wrote:

- active-slot `init_boot`
- `efisp`

The root log did **not** show normal root installation writes to:

- `boot`
- `vendor_boot`
- `vbmeta`
- `abl`
- GPT
- userdata

Those were read/backed up only where needed for recovery evidence.

## Recovery assets

The private recovery set (not committed here) contains, as applicable:

- boot/init_boot for both slots
- vbmeta/vbmeta_system for both slots
- vendor_boot for both slots
- abl for both slots
- independent stock efisp reads
- primary and full backup GPT material for all LUNs
- a manifest with SHA-256 and partition geometry

The private backup was validated for read success, GPT CRC/table consistency, expected dump sizes and repeatable efisp hash.

## Minimal recovery rule

When Android boots and root works: **do nothing**.

If Android boots but root is lost:

1. determine whether the active slot changed;
2. determine whether OTA/recovery changed active `init_boot` or `efisp`;
3. compare against the private known-good hashes;
4. repair only the proven changed root component.

If boot fails after a root-related change, the minimal rollback scope is the root pair that was actually changed:

1. original stock active-slot `init_boot`;
2. original stock `efisp`.

Broader boot-chain or GPT restoration is justified only after independent evidence identifies corruption.

## Hard recovery rules

- BL unlock is not a root-recovery step.
- Do not begin recovery with `fastboot flashing unlock`.
- Do not switch active slots as the first repair action.
- Do not erase userdata for root maintenance.
- Do not blanket-disable AVB/vbmeta.
- Do not mix arbitrary newer/older firmware boot-chain partitions into the verified installation.
- Do not overwrite GPT without proof of GPT corruption.
- Do not overwrite a working efisp.
- Before any future partition write, read the target and hash it.
- Treat OTA as a controlled change until its effect on root/GBL compatibility is understood.

## Limitations

The private recovery set is targeted boot/root recovery material, not a complete physical device clone. RPMB is not backed up, not every firmware partition is captured, and no destructive full-restore drill has been performed.

Therefore recovery remains **minimal and evidence-driven**.

## Public/private boundary

This Git repository stores this procedure and non-secret scripts only. Raw partition images, Firehose/programmer payloads, proprietary vendor tools, exact device serials and private backup manifests stay outside public Git.
