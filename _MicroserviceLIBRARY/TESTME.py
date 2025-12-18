import sys
import os

print("--- 🔌 SYSTEM BOOT CHECK ---")

try:
    print("1. Loading Base Service...", end=" ")
    from base_service import BaseService
    print("✅ OK")

    print("2. Loading Cartridge Service...", end=" ")
    from __CartridgeServiceMS import CartridgeServiceMS
    print("✅ OK")

    print("3. Loading Scanner Service...", end=" ")
    from __ScannerMS import ScannerMS
    print("✅ OK")

    print("4. Loading Intake Service (The one you just fixed)...", end=" ")
    from __IntakeServiceMS import IntakeServiceMS
    print("✅ OK")

    print("\n🎉 SUCCESS: All microservices linked and loaded correctly!")

except ImportError as e:
    print(f"\n❌ FAIL: Import Error detected.\n   {e}")
except Exception as e:
    print(f"\n❌ FAIL: Runtime Error detected.\n   {e}")