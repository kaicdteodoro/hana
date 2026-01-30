"""
hana.__main__ — Entry point for python -m hana.
"""

import sys

from hana.cli import main

if __name__ == "__main__":
    sys.exit(main())
