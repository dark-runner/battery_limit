"""Module Import Verification Script"""

import sys
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

print("=" * 60)
print("Python Module Import Verification")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Source directory: {SRC_DIR}")
print()

# Test 1: Check system modules
print("[1] Checking system modules...")
try:
    import logging
    print("✓ logging: OK")
except Exception as e:
    print(f"✗ logging: {e}")

try:
    import threading
    print("✓ threading: OK")
except Exception as e:
    print(f"✗ threading: {e}")

try:
    import json
    print("✓ json: OK")
except Exception as e:
    print(f"✗ json: {e}")

print()

# Test 2: Check optional dependencies
print("[2] Checking optional dependencies...")
try:
    import psutil
    print(f"✓ psutil: OK (version {psutil.__version__})")
except Exception as e:
    print(f"✗ psutil: {e}")
    print("  -> Install with: pip install psutil")

try:
    import miio
    print(f"✓ miio: OK")
except Exception as e:
    print(f"✗ miio: {e}")
    print("  -> Install with: pip install python-miio")

try:
    import flask
    print(f"✓ flask: OK (version {flask.__version__})")
except Exception as e:
    print(f"✗ flask: {e}")
    print("  -> Install with: pip install flask")

print()

# Test 3: Check local modules
print("[3] Checking local modules...")

try:
    from config import Config
    print("✓ config: OK")
except Exception as e:
    print(f"✗ config: {e}")

try:
    from battery_manager import BatteryManager
    print("✓ battery_manager: OK")
except ImportError as e:
    if "psutil" in str(e):
        print(f"✗ battery_manager: Missing psutil dependency")
    else:
        print(f"✗ battery_manager: {e}")
except Exception as e:
    print(f"✗ battery_manager: {e}")

try:
    from mihome_controller import MihomeController
    print("✓ mihome_controller: OK")
except ImportError as e:
    if "miio" in str(e):
        print(f"✗ mihome_controller: Missing python-miio dependency")
    else:
        print(f"✗ mihome_controller: {e}")
except Exception as e:
    print(f"✗ mihome_controller: {e}")

try:
    from battery_auto_controller import BatteryAutoController
    print("✓ battery_auto_controller: OK")
except ImportError as e:
    if "miio" in str(e) or "psutil" in str(e):
        print(f"✗ battery_auto_controller: Missing dependencies: {e}")
    else:
        print(f"✗ battery_auto_controller: {e}")
except Exception as e:
    print(f"✗ battery_auto_controller: {e}")

try:
    from api_server import BatteryControlAPI
    print("✓ api_server: OK")
except ImportError as e:
    if "flask" in str(e):
        print(f"✗ api_server: Missing flask dependency")
    else:
        print(f"✗ api_server: {e}")
except Exception as e:
    print(f"✗ api_server: {e}")

print()
print("=" * 60)
print("Verification Complete")
print("=" * 60)
print()
print("To install all dependencies, run:")
print("  pip install -r requirements.txt")
print()
