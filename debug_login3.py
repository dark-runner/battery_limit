"""Test: follow notificationUrl after successful login"""
# Since we can't test with real credentials, let's just
# check what the notificationUrl endpoint looks like
import requests

# Check the notification URL endpoint
url = "https://account.xiaomi.com/fe/notification/check"
s = requests.Session()
r = s.get(url)
print(f"Status: {r.status_code}")
print(f"URL: {r.url}")
print(f"Cookies: {list(s.cookies.keys())}")
print()

# Also check: what if we set userId cookie from the login response
# and try the IoT API
s2 = requests.Session()
s2.cookies.set('userId', 'test_user')
s2.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/x-www-form-urlencoded',
})
r2 = s2.post('https://api.io.mi.com/app/home/device_list', 
             data={'data': '{}', 'rc': 'cn'})
print(f"IoT API status: {r2.status_code}")
print(f"Response: {r2.text[:200]}")
