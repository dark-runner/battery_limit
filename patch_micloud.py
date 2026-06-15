"""Test monkey-patching micloud to handle new Xiaomi API"""
import hashlib, json, logging

logging.basicConfig(level=logging.DEBUG)

# Import and patch
from micloud import MiCloud
import micloud.micloud as mc_module

original_step2 = MiCloud._login_step2

def patched_step2(self, sign):
    """Patched _login_step2 that handles missing fields"""
    logging.debug("Xiaomi login step 2 (patched)")
    url = "https://account.xiaomi.com/pass/serviceLoginAuth2"
    post_data = {
        'sid': "xiaomiio",
        'hash': hashlib.md5(self.password.encode()).hexdigest().upper(),
        'callback': "https://sts.api.io.mi.com/sts",
        'qs': '%3Fsid%3Dxiaomiio%26_json%3Dtrue',
        'user': self.username,
        '_json': 'true'
    }
    if sign:
        post_data['_sign'] = sign

    response = self.session.post(url, data=post_data)
    response_json = json.loads(response.text.replace("&&&START&&&", ""))
    
    logging.debug(f"Step2 result: {response_json.get('result')}")
    logging.debug(f"Step2 keys: {list(response_json.keys())}")
    
    if response_json.get("result") != "ok":
        from micloud.micloudexception import MiCloudAccessDenied
        raise MiCloudAccessDenied(
            "Access denied. Did you set the correct api key and/or username?"
        )
    
    # New API: result=ok but missing userId/ssecurity
    # Use default/empty values - the session cookies might still work
    self.user_id = response_json.get('userId', '') or ''
    self.ssecurity = response_json.get('ssecurity', '') or ''
    self.cuser_id = response_json.get('cUserId', '') or ''
    self.pass_token = response_json.get('passToken', '') or ''
    
    location = response_json.get('location', '') or ''
    code = response_json.get('code', 0)
    
    logging.debug(f"userId={self.user_id}, ssecurity={'set' if self.ssecurity else 'missing'}")
    logging.debug(f"location={'set' if location else 'missing'}")
    
    if location:
        return location
    
    # If no location but result=ok, the session might have auth cookies
    # Check cookies
    cookies = {c.name: c.value for c in self.session.cookies}
    logging.debug(f"Cookies: {list(cookies.keys())}")
    
    if 'serviceToken' in cookies:
        self.service_token = cookies['serviceToken']
        return "https://sts.api.io.mi.com/sts"  # dummy location
    
    raise MiCloudException("Login succeeded but no location URL or serviceToken found")

# Apply patch
MiCloud._login_step2 = patched_step2

from micloud.micloudexception import MiCloudException

# Test with dummy creds (will fail at step 1 or 2, but we can see the flow)
print("Patch applied. Testing...")
try:
    mc = MiCloud("test@test.com", "wrongpass")
    ok = mc.login()
    print(f"Login result: {ok}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
