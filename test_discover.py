"""Test LAN device discovery"""
import sys, json
from miio.discovery import Discovery

d = Discovery()
print("Testing discover_mdns...")
try:
    results = d.discover_mdns(timeout=3)
    print(f"Results type: {type(results)}")
    if results:
        print(f"Found {len(results)} devices:")
        for r in results:
            print(f"  {r}")
    else:
        print("No devices found (expected if no Xiaomi devices on LAN)")
except Exception as e:
    print(f"discover_mdns error: {type(e).__name__}: {e}")

# Also try the old-style discovery
print("\nTrying manual mDNS query...")
try:
    from miio.miioprotocol import MiIOProtocol
    # Just check if we can import
    print(f"MiIOProtocol available")
except Exception as e:
    print(f"Error: {e}")
