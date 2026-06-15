"""Debug Xiaomi login - follow notificationUrl after successful login"""
import requests, json, hashlib, logging

logging.basicConfig(level=logging.DEBUG)

# Simulate a login to check the notificationUrl
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})

# Step 1
r1 = session.get(
    'https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true'
)
data1 = json.loads(r1.text.replace('&&&START&&&', ''))
sign = data1.get('_sign', '')
print(f"Step1: _sign={'yes' if sign else 'no'}")

# Check what NOT returning from the new API
# In the old API, after result=ok, we'd get userId, ssecurity, location
# In the new API, we got notificationUrl instead

# Let's check if the notificationUrl can be used
print(f"notificationUrl in response: {'notificationUrl' in data1}")

# Check if the locale/country matters for the login
print(f"\nKeys in response: {list(data1.keys())}")

# Also check the homepage API
r_home = session.get('https://home.mi.com', timeout=10)
print(f"\nhome.mi.com status: {r_home.status_code}")
print(f"Cookies after home.mi.com:")
for c in session.cookies:
    print(f"  {c.name}")

# Check the IoT API directly
try:
    r_iot = session.get('https://api.io.mi.com/app/device/list', timeout=10)
    print(f"\nIoT API status: {r_iot.status_code}")
except Exception as e:
    print(f"\nIoT API error: {e}")
