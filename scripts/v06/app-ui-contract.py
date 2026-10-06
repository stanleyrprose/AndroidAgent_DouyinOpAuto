#!/usr/bin/env python3
import sys
from empirical import main
sys.argv.insert(1, "app-ui-contract")
raise SystemExit(main())
