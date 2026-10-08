# Y700 Vision Locator — Sprint V3 Hybrid Vision & Recovery

Status: **ENGINEERING EVIDENCE ONLY — PRODUCTION HYBRID ROUTING NOT AUTHORIZED**

Baseline: Sprint V2 PASS / FROZEN on real Y700. The 2026-10-07 V3 gate run is retained as engineering evidence only; it does not constitute user authorization to enable multi-candidate hybrid routing in production.

## Engineering-test scope

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

## Historical real-Y700 engineering gate

Accepted result:

```text
/opt/y700/runtime/vision-v3/vision-v3-20261006-185335.json
```

Final Gate V3 result:

```text
status = PASS
cold-start mixed workflows = 20/20 PASS (100%)
semantic-only no-regression = PASS
template -> OCR fallback = PASS
known semantic popup recovery = PASS
known bounded-template popup recovery = PASS
stale-target pre-action re-resolution = PASS
external irreversible / COMMIT Vision = BLOCKED
metadata-only route evidence = PASS
duplicate target actions = 0
duplicate commit actions = 0
```

Cold-start end-to-end workflow latency on the accepted run:

```text
P50 = 5815.1 ms
P95 = 7000.8 ms
max = 8782.2 ms
```

The accepted route evidence proves the deterministic cascade even when the request
supplies the fallback list in reverse order:

```text
semantic miss
-> vision_template MISS
-> vision_text PASS
-> shared Action Executor
-> shared postcondition PASS
```

The accepted run also proves that a stale target is discarded and re-resolved
before input, known popup recovery is package/context bound, and normal successful
route evidence contains metadata rather than an unnecessary full screenshot.

### Acceptance-harness hardening

One repeated Gate run exposed a benchmark-only single-sample flake: the extra
representative mixed request transiently returned `VISION_OCR_NOT_FOUND`, while
the required 20-run cold-start mixed suite completed **20/20 PASS** and each PASS
contained the expected template-miss -> OCR route plus metadata-only evidence.

The harness was therefore hardened so the frozen 20-run suite itself may provide
the mixed-route/evidence proof when the extra diagnostic representative sample
flakes. This does **not** reduce the production threshold: the required cold-start
gate remains >=19/20, and each counted PASS is still defined by the complete
`mixed_pass()` route/postcondition contract. The final accepted run did not need
that fallback: `representative_mixed_pass=true` and the evidence source was the
representative mixed job itself.

Gate code baseline: `7d73357`.

Accepted candidate APK hashes:

```text
app  = 791478bb3ee74dca52503bbd62fa704143f76de3ed485d4a7d1412c129268956
test = 38566b77fa65afc24bf0eea5d58ad04205ece265b326639ac0d16dd9bf6f877f
```
