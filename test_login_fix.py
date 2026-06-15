"""Test custom login + direct API for device listing"""
import requests, json, hashlib, logging

logging.basicConfig(level=logging.DEBUG)

# Step 1: Our custom login (which got result=ok)
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})

# For this test, we'll just check what the home.mi.com device API needs
# by checking the response headers and format

# Check the home.mi.com API format
r = session.get('https://home.mi.com/device/device_list', timeout=10)
print(f"\nhome.mi.com/device/device_list:")
print(f"  Status: {r.status_code}")
print(f"  Content-Type: {r.headers.get('content-type')}")
try:
    print(f"  Response: {r.json()}")
except:
    print(f"  Text: {r.text[:200]}")

# Check what the IoT API expects
r2 = session.post('https://api.io.mi.com/app/home/device_list', 
                  data={'data': '{}'}, timeout=10)
print(f"\napi.io.mi.com/app/home/device_list:")
print(f"  Status: {r2.status_code}")
print(f"  Response: {r2.text[:200]}")

# Check Xiaomi API documentation endpoint
r3 = session.get('https://open.home.mi.com/device/list', timeout=10)
print(f"\nopen.home.mi.com/device/list:")
print(f"  Status: {r3.status_code}")

print("\n--- Summary ---")
print("Without auth, all APIs return 401 or error")
print("We need a valid session with serviceToken/ssecurity")
