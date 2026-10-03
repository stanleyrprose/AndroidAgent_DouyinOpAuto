# Y700 Android Automation Core

- Mac is build/release only; never add Mac to the runtime path.
- Y700 must run automation independently after driver installation.
- AndroidX UI Automator 2.4.0 is the production semantic UI core.
- KernelSU/root bridge remains the privileged control plane.
- Runtime IPC is durable filesystem-first.
- Instrumentation must not require write access to the root-owned durable job directory.
- One workflow uses one instrumentation session. Do not use per-action instrumentation.
- External/destructive side effects must never be blindly retried.
- Absolute coordinates are last-resort fallback only.
