#!/usr/bin/env python3
import sys
from offline import main
sys.argv.insert(1, "presshome-back-migration")
raise SystemExit(main())
