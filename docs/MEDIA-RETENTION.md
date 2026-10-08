# Video retention: Mac two masters, Y700 gallery only

Scope: Douyin -> Burmese localization -> TikTok, plus Save to Album and Direct Download. This document governs **video payloads**, not tiny manifests, transcripts, Note receipts, or audit evidence.

- **Mac**: keep the downloaded Douyin MP4 under `mac/production-pipeline/runtime/jobs/<job>/source/` and the Burmese H.264 MP4 at `production/video.my.mp4` when localized. Direct Download keeps only original.
- **Mac export**: use a hardlink for MP4 payloads on the same filesystem, which creates an additional path but **no extra video bytes**. A cross-device handoff falls back to a copy. Export capability metadata and TTL remain unchanged. Uncompressed transcription WAV is temporary and removed after transcription.
- **Y700**: `/opt/y700/media/incoming`, `ready`, `published`, and `/opt/y700/runtime/direct-download` are transient process/recovery locations; `/sdcard/Movies/Y700Agent/<job>.mp4` is the sole persistent video location after confirmed success. Keep manifests and publication evidence for deduplication and ambiguous-COMMIT reconciliation.
- **Terminal cleanup**: AUTO_PUBLISH only after profile-verified PUBLISHED; STORE_ALBUM only after MediaStore and Notes success; DIRECT_DOWNLOAD only after MediaStore success. Delete a job MP4 from its work/archive directory only when the Android gallery SHA-256 exactly matches. Errors fail closed (report SKIPPED). DRY_RUN, ambiguous COMMIT, failed/unfinished jobs retain recovery assets.
- **Album policy**: TikTok staging replaces only that job's target filename; it must never wipe the rest of `Y700Agent`.
- **Existing files**: no automatic retroactive deletion in this change. Inventory historical videos and confirm scope separately before irreversible deletion. Mac temporary hardlinks and unrelated media are out of scope for deletion.
- **Rollback**: revert the retention commit. No format migration, daemon, DB, or new dependency.
