"""Use the existing tikin-setup environment, including complete Skills-only installations."""
from pathlib import Path
import sys
from _runtime_bootstrap import ensure_runtime

PACKAGE = Path(__file__).resolve().parent.parent
ensure_runtime('TIKIN_SETUP_BOOTSTRAP_REEXEC', project=PACKAGE)
sys.path.insert(0, str(PACKAGE / 'ui'))
from launcher import main

if __name__ == '__main__':
    main(PACKAGE, 'tikin-social')
