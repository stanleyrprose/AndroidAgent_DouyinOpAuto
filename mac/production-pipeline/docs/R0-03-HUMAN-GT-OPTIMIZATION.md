# R0-03 final human review and recognition remediation

The private R0-03 human review is complete for the OCR candidate text:
36 candidate events, 32 machine texts originally correct, 3 corrected
(#18 飞机耳, #29 生气, #32 实则偷袭), and #28 excluded as a false positive.
Four duplicate groups (#1/2, #11/12, #31/32, #34/35) are resolved.
The visual/spoken 嗯 at 51–52 seconds was originally missed. This yields
32 important canonical visual text targets. The reported event time ranges
are accepted by the user; the 嗯 time is approximate.

ASR #9 was 你笑死我了, not the original model transcript.
The tail-only machine candidate 喔！ was human-rejected as a false positive.
The tail-only 嗯 was confirmed by the user. Source audio spans 54.45 seconds
despite the full-pass ASR ending at 37.57 seconds.

All real visual Chinese subtitles, including short punctuation and callouts,
must be translated into Burmese NORMAL and FUNNY versions. FUNNY does not
authorize changing facts, negations, named entities, source times or plot.
Missing either version fails the two-tone completion contract.

Review adjudication is opt-in via Y700_DYNAMIC_HUMAN_GT_PATH, video-SHA
locked and source-event complete. Raw OCR, original ASR, and the original
machine fusion are retained. Do not hardcode R0-03 corrections into future
videos; that is single-sample overfitting. A video with substantial bbox
motion must not trigger indiscriminate neighboring text deduplication.

ASR tail detection runs bounded overlapping windows when the full-pass
transcript stops early. Window-only results remain machine review candidates,
not canonical speech, preventing false positives like 喔！ from being
automatically translated or published.

Independent complete R0 24+2 corpus acceptance and Burmese-native R2
review remain separate gates. Dynamic subtitle production stays OFF.
No TikTok publish or Y700 mutation is authorized here.
