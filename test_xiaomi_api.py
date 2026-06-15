"""Test Xiaomi login API - output to file"""
import requests, json, sys

# Step 1: Get login sign
url = 'https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true'
s = requests.Session()
s.cookies.update({'userId': 'test'})
r = s.get(url)
data = json.loads(r.text.replace('&&&START&&&', ''))
print(f"Step 1 - Status: {r.status_code}")
print(f"Step 1 - Code: {data.get('code')}")
print(f"Step 1 - Desc: {data.get('description')}")
print(f"Step 1 - Has _sign: {'_sign' in data}")
print(f"Step 1 - Keys: {list(data.keys())}")
print(f"Step 1 - Result: {data.get('result')}")
print()

# Try with proper headers
s2 = requests.Session()
s2.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
})
r2 = s2.get(url)
data2 = json.loads(r2.text.replace('&&&START&&&', ''))
print(f"Step 1 (with UA) - Status: {r2.status_code}")
print(f"Step 1 (with UA) - Code: {data2.get('code')}")
print(f"Step 1 (with UA) - Desc: {data2.get('description')}")
print(f"Step 1 (with UA) - Has _sign: {'_sign' in data2}")
print(f"Step 1 (with UA) - Result: {data2.get('result')}")

# Check if there's a captchaUrl
captcha = data2.get('captchaUrl')
print(f"Captcha URL: {captcha}")

# Save full response
with open('xiaomi_api_response.json', 'w', encoding='utf-8') as f:
    json.dump(data2, f, indent=2, ensure_ascii=False)
print("\nFull response saved to xiaomi_api_response.json")
