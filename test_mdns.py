"""Test what discovery methods actually work"""
import logging
logging.basicConfig(level=logging.DEBUG)

# Method 1: mDNS discovery
print("=== Method 1: mDNS Discovery ===")
from miio.discovery import Discovery
try:
    results = Discovery.discover_mdns(timeout=3)
    print(f"mDNS found: {results}")
except Exception as e:
    print(f"mDNS error: {e}")

# Method 2: Manual UDP broadcast
print("\n=== Method 2: UDP Broadcast ===")
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.settimeout(3)
try:
    # Xiaomi hello message
    msg = bytes.fromhex('21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff')
    sock.sendto(msg, ('255.255.255.255', 54321))
    print("Hello sent, waiting for response...")
    try:
        data, addr = sock.recvfrom(1024)
        print(f"Response from {addr}: {data.hex()}")
    except socket.timeout:
        print("No response (timeout)")
except Exception as e:
    print(f"Error: {e}")
finally:
    sock.close()

print("\nDone")
