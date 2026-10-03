# Settings Acceptance

## Purpose

Prove the automation core is generic and does not depend on TikTok-specific logic.

## Dark mode reversible acceptance

The acceptance must never use "page contains 深色模式" as the success condition.

Required state transitions:

1. Read initial state:
   - dark_mode_white_check.checked = true
   - dark_mode_black_check.checked = false
2. Select dark.
3. Assert:
   - dark_mode_black_check.checked = true
   - dark_mode_white_check.checked = false
4. Restore light.
5. Assert:
   - dark_mode_white_check.checked = true
   - dark_mode_black_check.checked = false

This prevents false-positive postconditions caused by the left search pane continuing
to contain the text 深色模式 on a two-pane tablet layout.

## Real-device result

2026-10-03:

- workflow actions: 8/8 PASS
- switch-to-dark verified by checked state
- restore-to-light verified by checked state
- final device state restored to light
- evidence screenshots captured for dark and restored states
