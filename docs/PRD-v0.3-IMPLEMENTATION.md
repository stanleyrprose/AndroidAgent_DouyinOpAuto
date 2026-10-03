# PRD v0.3 implementation truth

This file is the runtime implementation summary for PRD v0.3.

Key decisions:
- BL unlock is not a runtime requirement; stable KernelSU root + recoverability is.
- Android Host IPC is filesystem-first; /opt/y700/jobs is canonical durable state.
- One repo: /opt/y700/workspaces/y700-agent.
- Cloudflare Named Tunnel is the only production remote path unless field evidence proves a fallback is needed.
- Full Android privilege is preserved while dedicated tool surface stays minimal.
- A real TikTok publish is a distinct commit action; probe/recovery flows stop at POST_CONFIG.

Implementation status must be updated in CHECKPOINT.md after every accepted gate.
