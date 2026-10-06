#!/usr/bin/env python3
import sys
from offline import main
sys.argv.insert(1, "subjob-provenance")
raise SystemExit(main())
