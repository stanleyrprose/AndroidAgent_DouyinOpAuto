#!/usr/bin/env python3
import sys
from empirical import main
sys.argv.insert(1, "admission-lock-load")
raise SystemExit(main())
