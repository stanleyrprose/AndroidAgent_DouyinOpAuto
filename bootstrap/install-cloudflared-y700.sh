#!/bin/bash
set -e
codexpro install-cloudflared --headless
~/.codexpro/bin/cloudflared --version
