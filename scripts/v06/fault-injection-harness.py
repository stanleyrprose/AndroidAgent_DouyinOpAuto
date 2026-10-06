#!/usr/bin/env python3
import sys
from empirical import main
sys.argv.insert(1, "fault-injection-harness")
raise SystemExit(main())
