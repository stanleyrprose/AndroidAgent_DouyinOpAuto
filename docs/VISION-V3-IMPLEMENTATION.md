# Y700 Vision Locator — Sprint V3 Hybrid Vision & Recovery

Status: **IN PROGRESS**

Baseline: Sprint V2 PASS / FROZEN on real Y700. V3 is explicitly authorized by the user on 2026-10-06.

## Frozen scope

Implement only the PRD V3 scope:

- semantic -> template -> OCR fallback policy;
- screen / effective-ROI change fingerprint;
- stale-target detection with bounded pre-action re-resolution;
- known popup recovery hooks;
- cache invalidation;
- Vision evidence policy.

Do not introduce a second workflow engine, daemon, MQ, socket protocol, per-frame
Bridge jobs, object detector, VLM, or high-FPS capture.

## Safety invariants

1. Semantic resolution remains first and bypasses Vision when unique.
2. Mixed fallback order is deterministic: template before OCR.
3. Template ambiguity remains fail-closed; it is not silently bypassed.
4. A stale/rotation mismatch before action may re-resolve once because no input
   side effect has occurred yet.
5. After any click/input side effect, a postcondition failure must not cascade to
   another locator and risk a duplicate action.
6. External irreversible / COMMIT Vision remains denied by default.
7. Known-popup recovery is package/context bound and never performs a global
   arbitrary X-like click.
8. Request ROI remains the acceptance boundary; caches are invalidated on
   geometry/package/fingerprint/model/template changes.

## Gate V3

Acceptance must prove on the real Y700:

- mixed semantic + template + OCR workflows;
- 20 cold-start regression runs;
- >=95% workflow PASS;
- zero duplicate commit/action;
- semantic-only workflows do not regress;
- stale target re-resolves instead of reusing old coordinates;
- popup recovery follows semantic dismiss -> bounded template dismiss -> workflow failure;
- Vision evidence records route attempts/recovery without persisting unnecessary
  full screenshots on normal success.
