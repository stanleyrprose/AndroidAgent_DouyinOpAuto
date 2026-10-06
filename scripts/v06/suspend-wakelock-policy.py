#!/usr/bin/env python3
import sys
from empirical import main
sys.argv.insert(1, "suspend-wakelock-policy")
raise SystemExit(main())
