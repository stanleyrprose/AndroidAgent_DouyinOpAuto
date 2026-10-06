# Y700 Locked-screen PUBLIC Publish Acceptance — 2026-10-06

Status: **PASS**

Scope: unattended Y700 publish leg starting from Android sleep/lock state.

This acceptance is intentionally narrower than the already-frozen Telegram ->
TikTok zero-touch E2E acceptance. The source URL for this run was supplied from
ChatGPT, while the Y700 publication leg itself was executed without manually
unlocking or touching the tablet.

## Acceptance job

- job id: `dy-7686483339214313198`
- aweme id: `7686483339214313198`
- source: Douyin `快乐勇哥` / `#蹦迪 #跳舞 #慢摇`
- route: `speech_candidate`
- content type: `speech`
- visibility: `PUBLIC`
- rendered video SHA-256: `0d7bebeed96d673fa76a46cbaa5b9937a86be0f28dc742faec98f5380cb81b61`

## What the first attempt exposed

The first locked-screen attempt showed a real ordering defect: Android-side
preflight / MediaStore staging happened before secure unlock. While Y700 was
asleep, staging could spend a long time inside Android provider/root operations
before TikTok cold-launch was reached.

The acceptance therefore correctly failed to prove the intended property.
No COMMIT was entered and no irreversible Publish click was dispatched in that
failed DRY_RUN attempt.

## Fix

PR #10 moved secure unlock ahead of Android-side preflight and staging and added
bounded staging root-exec / MediaStore query timeouts.

The effective order is now:

`UNLOCKING -> PREFLIGHT -> STAGING -> TikTok cold-launch -> DRY_RUN -> COMMIT`

TikTok cold-launch still performs its own secure-unlock/keyguard recheck, so the
pre-stage unlock does not weaken the existing fail-closed lock recovery logic.

The fix also added regression coverage that verifies unlock ordering and bounded
staging timeouts. CI isolation was corrected so routing unit tests mock the
publisher command boundary rather than invoking real Y700 secure-unlock on the
GitHub runner.

## Successful locked-screen evidence

Durable Bridge history for the successful run shows:

- `2026-10-05T18:33:31Z`: `KEYCODE_SLEEP` was dispatched.
- `2026-10-05T18:33:55Z`: production `secure-unlock` ran from the publisher path.
- subsequent production bridge jobs performed `KEYCODE_WAKEUP` / keyguard
  dismissal and repeated secure-unlock verification as needed.
- `2026-10-05T18:38:08Z`: durable publisher state reached `PUBLISHED`.

No manual unlock was performed between the test sleep action and publication.

## Publication result

Y700 durable publisher truth:

- status: `PUBLISHED`
- visibility: `PUBLIC`
- `submission.accepted = true`
- confirmation: `generic_commit_dispatched`
- exactly one recorded `commit_workflow_job_id`
- post-publish verification: `verified = true`
- verification method: `generic_profile_public_exact_caption`

The Mac production job was finalized to `VERIFIED` with evidence
`locked_screen_secure_unlock_generic_profile_public_exact_caption` and the
Telegram terminal notification was sent successfully.

## Acceptance conclusion

**PASS:** a normally sleeping/locked Y700 can now receive the publish workflow,
use the enrolled local secure-unlock capability before Android-side preflight and
MediaStore staging, complete TikTok DRY_RUN, cross the exactly-once PUBLIC COMMIT
boundary, and verify the public post without a human unlocking the tablet.

This acceptance does **not** extend to the stronger post-reboot / Direct Boot
case where the device has rebooted and has never been unlocked since boot. That
must be accepted separately.
