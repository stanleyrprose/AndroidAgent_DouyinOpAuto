#!/usr/bin/env python3
import sys
from empirical import main
sys.argv.insert(1, "runtime-permissions")
raise SystemExit(main())
