# Telegram MP4 handoff

Intent-marked DIRECT_DOWNLOAD, STORE_ALBUM and AUTO_PUBLISH jobs send the
finished Mac MP4 before exporting a capability and before the supported Y700
pull entrances. DIRECT_DOWNLOAD sends the original Douzy MP4; the other two
send production/video.my.mp4. sendDocument uploads the original bytes without
re-encoding. Status notifications remain best effort; this media delivery is a
mandatory gate. Delivery failure retains Mac media and blocks pull.

Configure deployment-local runtime/env.local with Y700_TG_CHAT_ID (the exact
numeric Y700_automation ingress chat), and Y700_TG_BOT_TOKEN or
TELEGRAM_BOT_TOKEN for that dedicated bot. Never commit these values. A job's
runtime state.json telegram_chat_id may bind its ingress destination instead;
record that value at ingress for installations serving multiple chats. No
implicit `telegram` target or alternate chat is accepted. Persist workflow
intent before export. Unmarked non-Telegram exports retain existing behavior.

An existing media-capable Hermes installation can instead supply
Y700_TG_MEDIA_SENDER: an executable adapter accepting --chat-id <id>
--document <absolute MP4>. It must upload bytes as a document and emit the
Telegram API JSON envelope containing ok, result.message_id and result.chat.id.
Text-only Hermes send is insufficient. The adapter must not internally retry
ambiguous sends. No bot or Hermes service is installed or modified here.

The conservative cloud upload ceiling is 49,000,000 bytes, optionally lowered
by Y700_TG_MEDIA_MAX_BYTES. Oversize files block: no compression, splitting,
capability-link substitution or Y700 pull. The adapter uses this same ceiling.
Explicit API rejection (429 or selected server errors) permits at most three
attempts per invocation, each with bounded delay (maximum 30 seconds); an
explicit retry_after over the bound blocks until a later resume.

export/telegram-media-receipt.json is fsynced and protected by a per-job lock.
SENT binds job, intent, destination hash, MP4 size/SHA-256 and Telegram message
id. Resume reuses a matching receipt; changed bytes/chat block. REJECTED or
BLOCKED_SIZE can be retried after fixing the cause via the existing Resume Task
controller or pipeline.sh telegram-media <job>. SENDING at crash, transport
failure, invalid reply or wrong chat means UNCERTAIN: pull stays blocked and
resume does not resend. Telegram has no client idempotency key: an operator
must reconcile chat evidence before repairing that private receipt, recording
the confirmed message id and exact identity. Never blindly delete an uncertain
receipt to retry. No publication state or COMMIT reconciliation is changed.

R0/R2 subtitle quality gates and experimental-mode restrictions remain intact;
this feature does not authorize R0-04 acceptance, public subtitle rollout,
TikTok COMMIT or deployment. Tests use only synthetic files and mocked senders.
