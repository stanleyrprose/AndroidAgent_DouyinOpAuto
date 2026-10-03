# Git SOT policy

## Canonical source

The public GitHub repository `stanleyrprose/AndroidAgent_DouyinOpAuto`, branch `main`, is canonical for:

- Y700 runtime source and scripts;
- non-secret configuration;
- Mac production-pipeline source;
- Mac media-export source;
- architecture/runbooks/checkpoints.

Runtime job state, secrets, downloaded media and recovery binary images are intentionally **not** canonical Git content.

## Migration provenance

The first public snapshot was assembled on 2026-10-03 from:

- Y700 runtime local source at commit `c145f41` (includes roaming SSH work);
- Mac production pipeline at commit `d0c96a0`;
- verified root/recovery records from the 2026-10-02 device recovery workspace.

The public history starts from a scrubbed snapshot rather than publishing the private/local development history. This prevents test screenshots, real sample identifiers and machine-specific data from becoming permanent public Git history.

## Future-change rule

1. Treat GitHub `main` as the expected version.
2. Make a focused branch/commit for code changes.
3. Run minimal affected-path tests.
4. Push/merge.
5. Pull/reconcile the target runtime from `main`.
6. Keep operational state outside Git.
7. Update `CHECKPOINT.md` when an acceptance gate changes.

If a live device contains an emergency fix made directly in place, commit or reproduce that change into this repository immediately after stabilization; do not let the device become a second SOT.
