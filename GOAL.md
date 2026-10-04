# Goal

Make the Lenovo Y700 an independent Cloud ChatGPT development and Android automation node, with the Mac mini as the content-production and recovery plane, while keeping all source/config/documentation changes under one GitHub SOT.

## Runtime architecture

```text
Cloud ChatGPT or dedicated Telegram bot
-> douyin-tiktok-publish orchestration
-> Mac production plane and/or CodexPro-Y700
-> filesystem-first durable jobs
-> Android host root executor
-> Android / TikTok
```

Content path:

```text
Douyin URL
-> Mac authenticated ingest
-> evidence-based analysis
-> Myanmar localization/render
-> capability-based handoff
-> Y700 pull + checksum
-> TikTok DRY_RUN
-> standing one-URL authorization or current-turn explicit approval
-> exactly one COMMIT attempt
-> profile verification/reconciliation
-> Telegram status receipt when Telegram is the ingress
```

## Current product constraints

1. Keep the architecture minimal and recoverable.
2. Keep the bootloader locked while persistent KernelSU root is stable.
3. Keep secrets and runtime artifacts outside public Git.
4. Use GitHub `main` as code/config/docs SOT.
5. Do not auto-retry ambiguous publication commits.
6. Keep Telegram as a thin, allowlisted control/notification plane; do not expose arbitrary shell/root operations through the bot.
