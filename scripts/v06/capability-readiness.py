#!/usr/bin/env python3
import sys
from offline import main
sys.argv.insert(1, "capability-readiness")
raise SystemExit(main())
