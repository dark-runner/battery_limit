"""MiCloud V2 API 登录助手 - 从小米云端获取设备真实 Token

基于 Xiaomi-cloud-tokens-extractor v1.5.1 的实现方式：
- 使用 V2 API (/v2/homeroom/gethome → /v2/home/home_device_list)
- RC4 加密通信
- 支持验证码和 2FA 邮箱验证
"""

import hashlib
import json
import logging
import os
import random
import re
import base64
import threading
import time
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import parse_qs, urlparse

import requests

try:
    from Crypto.Cipher import ARC4
except ModuleNotFoundError:
    from Cryptodome.Cipher import ARC4

logger = logging.getLogger(__name__)

SERVERS = ["cn", "de", "us", "ru", "tw", "sg", "in", "i2"]


class XiaomiCloudConnector:
    """小米云连接器 - 使用 V2 API + RC4 加密"""

    def __init__(self):
        self._agent = self._generate_agent()
        self._device_id = self._generate_device_id()
        self._session = requests.session()
        self._ssecurity: Optional[str] = None
        self.userId: Optional[str] = None
        self._serviceToken: Optional[str] = None
        self._sign: Optional[str] = None
        self._cUserId: Optional[str] = None
        self._passToken: Optional[str] = None
        self._location: Optional[str] = None
        self._code: Optional[str] = None

        # 回调（GUI 用）
        self.on_captcha: Optional[Callable[[bytes], str]] = None
        self.on_2fa: Optional[Callable[[], str]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    # ── 公开方法 ────────────────────────────────────────

    def login(self, username: str, password: str,
              captcha_callback: Optional[Callable[[bytes], str]] = None,
              twfa_callback: Optional[Callable[[], str]] = None,
              status_callback: Optional[Callable[[str], None]] = None) -> bool:
        """登录小米云

        Args:
            username: 小米账号
            password: 密码
            captcha_callback: 验证码回调，接收图片 bytes，返回验证码文本
            twfa_callback: 2FA 回调，无参数，返回用户输入的验证码
            status_callback: 状态回调，更新登录进度

        Returns:
            bool: 登录是否成功
        """
        self.on_captcha = captcha_callback
        self.on_2fa = twfa_callback
        self.on_status = status_callback
        self._username = username
        self._password = password

        self._update_status("正在登录...")

        self._session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="mi.com")
        self._session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="xiaomi.com")
        self._session.cookies.set("deviceId", self._device_id, domain="mi.com")
        self._session.cookies.set("deviceId", self._device_id, domain="xiaomi.com")

        if not self._login_step1():
            self._update_status("❌ 登录第一步失败")
            return False

        if not self._login_step2():
            self._update_status("❌ 登录失败，请检查账号密码或处理验证")
            return False

        if self._location and not self._serviceToken and not self._login_step3():
            self._update_status("❌ 获取服务 Token 失败")
            return False

        self._update_status("✅ 登录成功")
        return True

    # ── 二维码登录 ──────────────────────────────────────

    def login_qrcode(self,
                     qrcode_callback: Callable[[bytes, str], None],
                     status_callback: Optional[Callable[[str], None]] = None,
                     timeout: int = 120) -> bool:
        """使用二维码登录小米云

        Args:
            qrcode_callback: 二维码回调，接收 (图片bytes, 备选登录URL)
            status_callback: 状态回调
            timeout: 等待扫码超时秒数

        Returns:
            bool: 登录是否成功
        """
        self.on_status = status_callback
        self._update_status("正在获取二维码...")

        self._session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="mi.com")
        self._session.cookies.set("sdkVersion", "accountsdk-18.8.15", domain="xiaomi.com")
        self._session.cookies.set("deviceId", self._device_id, domain="mi.com")
        self._session.cookies.set("deviceId", self._device_id, domain="xiaomi.com")

        # Step 1: 获取二维码 URL 和长轮询 URL
        url = "https://account.xiaomi.com/longPolling/loginUrl"
        params = {
            "_qrsize": "480",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "callback": "https://sts.api.io.mi.com/sts",
            "_hasLogo": "false",
            "sid": "xiaomiio",
            "serviceParam": "",
            "_locale": "en_GB",
            "_dc": str(int(time.time() * 1000))
        }
        try:
            resp = self._session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                self._update_status("❌ 获取二维码失败")
                return False
            data = self._to_json(resp.text)
            qr_url = data.get("qr", "")
            login_url = data.get("loginUrl", "")
            lp_url = data.get("lp", "")
            lp_timeout = data.get("timeout", 120)
            if not qr_url:
                self._update_status("❌ 获取二维码 URL 失败")
                return False
        except Exception as e:
            self._update_status(f"❌ 获取二维码出错: {e}")
            return False

        # Step 2: 下载二维码图片
        try:
            img_resp = self._session.get(qr_url, timeout=10)
            if img_resp.status_code != 200:
                self._update_status("❌ 下载二维码失败")
                return False

            # 显示二维码
            timeout = min(timeout, lp_timeout)
            self._update_status(f"📱 请用米家 App 扫描二维码 ({timeout}秒内)")
            qrcode_callback(img_resp.content, login_url)
        except Exception as e:
            self._update_status(f"❌ 下载二维码出错: {e}")
            return False

        # Step 3: 长轮询等待扫码
        start_time = time.time()
        while True:
            try:
                poll_resp = self._session.get(lp_url, timeout=10)
                if poll_resp.status_code == 200:
                    break
            except requests.exceptions.Timeout:
                if time.time() - start_time > timeout:
                    self._update_status("❌ 扫码超时，请重试")
                    return False
                continue
            except Exception as e:
                self._update_status(f"❌ 长轮询出错: {e}")
                return False

            if time.time() - start_time > timeout:
                self._update_status("❌ 扫码超时，请重试")
                return False

        # 扫码成功，解析结果
        try:
            poll_data = self._to_json(poll_resp.text)
            self.userId = poll_data["userId"]
            self._ssecurity = poll_data["ssecurity"]
            self._cUserId = poll_data["cUserId"]
            self._passToken = poll_data["passToken"]
            self._location = poll_data["location"]
        except (KeyError, json.JSONDecodeError) as e:
            self._update_status(f"❌ 解析登录结果失败: {e}")
            return False

        # Step 4: 获取 serviceToken
        if not self._location:
            self._update_status("❌ 缺少登录跳转地址")
            return False

        try:
            loc_resp = self._session.get(self._location, headers={
                "content-type": "application/x-www-form-urlencoded"
            }, timeout=10)
            if loc_resp.status_code != 200:
                self._update_status("❌ 获取 serviceToken 失败")
                return False
            self._serviceToken = loc_resp.cookies.get("serviceToken")
            if not self._serviceToken:
                self._update_status("❌ 未获取到 serviceToken")
                return False
        except Exception as e:
            self._update_status(f"❌ 获取 serviceToken 出错: {e}")
            return False

        self._update_status("✅ 二维码登录成功")
        return True

    def get_devices(self, country: str = "cn") -> List[Dict[str, Any]]:
        """获取设备列表（V2 API）

        Args:
            country: 服务器区域

        Returns:
            设备列表，每项包含 localip, token, model, name, mac, did
        """
        all_devices: List[Dict[str, Any]] = []

        # 1. 获取家庭列表
        homes_data = self._get_homes(country)
        if not homes_data:
            logger.warning(f"区域 {country} 无家庭数据")
            return []

        homes = []
        result = homes_data.get("result", {})
        for h in result.get("homelist", []):
            homes.append({"home_id": h["id"], "home_owner": self.userId})

        # 共享家庭
        dev_cnt = self._get_dev_cnt(country)
        if dev_cnt:
            for h in dev_cnt.get("result", {}).get("share", {}).get("share_family", []):
                homes.append({"home_id": h["home_id"], "home_owner": h["home_owner"]})

        # 2. 每个家庭获取设备
        for home in homes:
            devices_data = self._get_devices(country, home["home_id"], home["home_owner"])
            if devices_data:
                device_info = devices_data.get("result", {}).get("device_info", [])
                for device in device_info:
                    all_devices.append(device)

        logger.info(f"从区域 {country} 获取到 {len(all_devices)} 个设备")
        return all_devices

    @staticmethod
    def extract_device_info(device: Dict[str, Any]) -> Dict[str, str]:
        return {
            "ip": device.get("localip", ""),
            "token": device.get("token", ""),
            "model": device.get("model", ""),
            "name": device.get("name", device.get("model", "未知设备")),
            "mac": device.get("mac", ""),
            "did": device.get("did", ""),
        }

    def fetch_devices_by_region(
        self, region: str,
        status_cb: Optional[Callable[[str], None]] = None,
        result_cb: Optional[Callable[[List[Dict[str, str]]], None]] = None
    ):
        """登录后按区域获取设备（后台线程）

        Args:
            region: 服务器区域 (cn, de, us, 等)
            status_cb: 状态回调
            result_cb: 结果回调，接收 [{ip, token, model, name}]
        """
        self.on_status = status_cb

        def _run():
            if status_cb:
                status_cb(f"⏳ 正在查询区域 {region}...")
            try:
                devices = self.get_devices(country=region)
                results = []
                seen = set()
                for d in (devices or []):
                    info = self.extract_device_info(d)
                    key = f"{info['ip']}|{info['token']}"
                    if info["ip"] and info["token"] and key not in seen:
                        seen.add(key)
                        results.append(info)
                if status_cb:
                    status_cb(f"✅ 找到 {len(results)} 个设备" if results
                              else "⚠ 该区域未找到设备")
                if result_cb:
                    result_cb(results)
            except Exception as e:
                logger.error(f"区域 {region} 查询失败: {e}")
                if status_cb:
                    status_cb(f"❌ 查询区域 {region} 失败: {e}")
                if result_cb:
                    result_cb([])

        threading.Thread(target=_run, daemon=True).start()

    # ── 内部方法 ────────────────────────────────────────

    def _update_status(self, msg: str):
        logger.info(msg)
        if self.on_status:
            self.on_status(msg)

    def _login_step1(self) -> bool:
        url = "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true"
        headers = {
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        cookies = {"userId": self._username}
        try:
            response = self._session.get(url, headers=headers, cookies=cookies, timeout=15)
            json_resp = self._to_json(response.text)

            if response.status_code == 200:
                if "_sign" in json_resp:
                    self._sign = json_resp["_sign"]
                    return True
                elif "ssecurity" in json_resp:
                    self._ssecurity = json_resp["ssecurity"]
                    self.userId = json_resp["userId"]
                    self._cUserId = json_resp["cUserId"]
                    self._passToken = json_resp["passToken"]
                    self._location = json_resp["location"]
                    self._code = json_resp["code"]
                    return True
            return False
        except Exception as e:
            logger.error(f"login_step1 失败: {e}")
            return False

    def _login_step2(self) -> bool:
        url = "https://account.xiaomi.com/pass/serviceLoginAuth2"
        headers = {
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        fields = {
            "sid": "xiaomiio",
            "hash": hashlib.md5(self._password.encode()).hexdigest().upper(),
            "callback": "https://sts.api.io.mi.com/sts",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": self._username,
            "_sign": self._sign,
            "_json": "true"
        }

        try:
            response = self._session.post(url, headers=headers, params=fields,
                                          allow_redirects=False, timeout=10)

            if response.status_code != 200:
                return False

            json_resp = self._to_json(response.text)

            # 处理验证码
            if "captchaUrl" in json_resp and json_resp.get("captchaUrl"):
                if self.on_captcha:
                    self._update_status("需要验证码验证")
                    captcha_url = json_resp["captchaUrl"]
                    if captcha_url.startswith("/"):
                        captcha_url = "https://account.xiaomi.com" + captcha_url
                    try:
                        img_resp = self._session.get(captcha_url, timeout=15)
                        if img_resp.status_code == 200:
                            code = self.on_captcha(img_resp.content)
                            if code:
                                fields["captCode"] = code
                                response = self._session.post(
                                    url, headers=headers, params=fields,
                                    allow_redirects=False, timeout=10)
                                if response.status_code == 200:
                                    json_resp = self._to_json(response.text)
                                else:
                                    return False
                            else:
                                return False
                        else:
                            return False
                    except Exception as e:
                        logger.error(f"验证码处理失败: {e}")
                        return False
                else:
                    logger.warning("需要验证码但无回调")
                    return False

            # 检查登录结果
            if "ssecurity" in json_resp and len(str(json_resp["ssecurity"])) > 4:
                self._ssecurity = json_resp["ssecurity"]
                self.userId = json_resp.get("userId", self.userId)
                self._cUserId = json_resp.get("cUserId", self._cUserId)
                self._passToken = json_resp.get("passToken", self._passToken)
                self._location = json_resp.get("location", self._location)
                self._code = json_resp.get("code", self._code)
                return True
            else:
                # 2FA 验证
                if "notificationUrl" in json_resp:
                    self._update_status("需要邮箱验证码（2FA）")
                    if self.on_2fa:
                        return self._do_2fa(json_resp["notificationUrl"])
                    else:
                        logger.warning("需要 2FA 但无回调")
                        return False

            return False
        except Exception as e:
            logger.error(f"login_step2 失败: {e}")
            return False

    def _login_step3(self) -> bool:
        headers = {
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        try:
            response = self._session.get(self._location, headers=headers, timeout=10)
            if response.status_code == 200:
                self._serviceToken = response.cookies.get("serviceToken")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"login_step3 失败: {e}")
            return False

    def _do_2fa(self, notification_url: str) -> bool:
        """处理邮箱 2FA 验证"""
        headers = {
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            # 1. 打开 notificationUrl (authStart)
            r = self._session.get(notification_url, headers=headers, timeout=10)
            context = parse_qs(urlparse(notification_url).query).get("context", [""])[0]
            if not context:
                logger.error("无法获取 2FA context")
                return False

            # 2. 获取 identity list
            list_params = {"sid": "xiaomiio", "context": context, "_locale": "en_US"}
            self._session.get("https://account.xiaomi.com/identity/list",
                              params=list_params, headers=headers, timeout=10)

            # 3. 发送邮箱验证码
            send_data = {
                "retry": "0", "icode": "", "_json": "true",
                "ick": self._session.cookies.get("ick", "")
            }
            send_params = {
                "_dc": str(int(time.time() * 1000)),
                "sid": "xiaomiio", "context": context,
                "mask": "0", "_locale": "en_US"
            }
            self._session.post("https://account.xiaomi.com/identity/auth/sendEmailTicket",
                               params=send_params, data=send_data, headers=headers, timeout=10)

            # 4. 询问用户验证码
            self._update_status("📧 验证码已发送到邮箱，请输入")
            if not self.on_2fa:
                return False
            code = self.on_2fa()
            if not code:
                return False

            # 5. 验证
            verify_params = {
                "_flag": "8", "_json": "true", "sid": "xiaomiio",
                "context": context, "mask": "0", "_locale": "en_US"
            }
            verify_data = {
                "_flag": "8", "ticket": code, "trust": "false",
                "_json": "true", "ick": self._session.cookies.get("ick", "")
            }
            r = self._session.post("https://account.xiaomi.com/identity/auth/verifyEmail",
                                   params=verify_params, data=verify_data,
                                   headers=headers, timeout=10)

            if r.status_code != 200:
                return False

            # 6. 获取 finish location
            finish_loc = None
            try:
                jr = r.json()
                finish_loc = jr.get("location")
            except Exception:
                finish_loc = r.headers.get("Location")
                if not finish_loc and r.text:
                    m = re.search(r'https://account\.xiaomi\.com/identity/result/check\?[^"\']+', r.text)
                    if m:
                        finish_loc = m.group(0)

            if not finish_loc:
                return False

            # 7. 调用 identity/result/check
            if "identity/result/check" in finish_loc:
                r = self._session.get(finish_loc, headers=headers, allow_redirects=False, timeout=10)
                end_url = r.headers.get("Location")
            else:
                end_url = finish_loc

            if not end_url:
                return False

            # 8. Auth2/end 获取 ssecurity
            r = self._session.get(end_url, headers=headers, allow_redirects=False, timeout=10)
            if r.status_code == 200 and "Xiaomi Account - Tips" in r.text:
                r = self._session.get(end_url, headers=headers, allow_redirects=False, timeout=10)

            ext_prag = r.headers.get("extension-pragma")
            if ext_prag:
                try:
                    ep_json = json.loads(ext_prag)
                    ssec = ep_json.get("ssecurity")
                    if ssec:
                        self._ssecurity = ssec
                except Exception:
                    pass

            if not self._ssecurity:
                return False

            # 9. STS 获取 serviceToken
            sts_url = r.headers.get("Location")
            if not sts_url and r.text:
                idx = r.text.find("https://sts.api.io.mi.com/sts")
                if idx != -1:
                    end = r.text.find('"', idx)
                    sts_url = r.text[idx:end] if end != -1 else r.text[idx:idx + 300]

            if not sts_url:
                return False

            r = self._session.get(sts_url, headers=headers, allow_redirects=True, timeout=10)
            self._serviceToken = self._session.cookies.get("serviceToken", domain=".sts.api.io.mi.com")

            # 镜像 serviceToken 到 API 域名
            for d in [".api.io.mi.com", ".io.mi.com", ".mi.com"]:
                self._session.cookies.set("serviceToken", self._serviceToken, domain=d)
                self._session.cookies.set("yetAnotherServiceToken", self._serviceToken, domain=d)

            self.userId = self.userId or self._session.cookies.get("userId", domain=".xiaomi.com")
            return bool(self._serviceToken)

        except Exception as e:
            logger.error(f"2FA 处理失败: {e}")
            return False

    # ── API 调用 ────────────────────────────────────────

    def _get_homes(self, country):
        url = self._get_api_url(country) + "/v2/homeroom/gethome"
        params = {"data": '{"fg": true, "fetch_share": true, "fetch_share_dev": true, "limit": 300, "app_ver": 7}'}
        return self._execute_encrypted(url, params)

    def _get_devices(self, country, home_id, owner_id):
        url = self._get_api_url(country) + "/v2/home/home_device_list"
        params = {
            "data": '{"home_owner": ' + str(owner_id) +
                    ', "home_id": ' + str(home_id) +
                    ', "limit": 200, "get_split_device": true, "support_smart_home": true}'
        }
        return self._execute_encrypted(url, params)

    def _get_dev_cnt(self, country):
        url = self._get_api_url(country) + "/v2/user/get_device_cnt"
        params = {"data": '{"fetch_own": true, "fetch_share": true}'}
        return self._execute_encrypted(url, params)

    def _execute_encrypted(self, url, params):
        """执行加密 API 调用（V2 API RC4 加密）"""
        if not self._serviceToken or not self._ssecurity:
            logger.error("未登录或缺少 serviceToken")
            return None

        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self.userId),
            "yetAnotherServiceToken": str(self._serviceToken),
            "serviceToken": str(self._serviceToken),
            "locale": "en_GB",
            "timezone": "GMT+02:00",
            "is_daylight": "1",
            "dst_offset": "3600000",
            "channel": "MI_APP_STORE"
        }

        millis = round(time.time() * 1000)
        nonce = self._generate_nonce(millis)
        signed_nonce = self._signed_nonce(nonce)
        fields = self._generate_enc_params(url, "POST", signed_nonce, nonce, params, self._ssecurity)

        try:
            response = self._session.post(url, headers=headers, cookies=cookies,
                                          params=fields, timeout=15)
            if response.status_code == 200:
                decoded = self._decrypt_rc4(self._signed_nonce(fields["_nonce"]), response.text)
                return json.loads(decoded)
        except Exception as e:
            logger.error(f"API 调用失败: {e}")

        return None

    # ── 加密工具 ────────────────────────────────────────

    @staticmethod
    def _get_api_url(country):
        return "https://" + ("" if country == "cn" else (country + ".")) + "api.io.mi.com/app"

    def _signed_nonce(self, nonce):
        hash_obj = hashlib.sha256(base64.b64decode(self._ssecurity) + base64.b64decode(nonce))
        return base64.b64encode(hash_obj.digest()).decode("utf-8")

    @staticmethod
    def _generate_nonce(millis):
        nonce_bytes = os.urandom(8) + (int(millis / 60000)).to_bytes(4, byteorder="big")
        return base64.b64encode(nonce_bytes).decode()

    @staticmethod
    def _generate_agent():
        agent_id = "".join(chr(random.randint(65, 69)) for _ in range(13))
        random_text = "".join(chr(random.randint(97, 122)) for _ in range(18))
        return f"{random_text}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"

    @staticmethod
    def _generate_device_id():
        return "".join(chr(random.randint(97, 122)) for _ in range(6))

    @staticmethod
    def _generate_enc_signature(url, method, signed_nonce, params):
        sig_params = [str(method).upper(), url.split("com")[1].replace("/app/", "/")]
        for k, v in params.items():
            sig_params.append(f"{k}={v}")
        sig_params.append(signed_nonce)
        sig_string = "&".join(sig_params)
        return base64.b64encode(hashlib.sha1(sig_string.encode("utf-8")).digest()).decode()

    @staticmethod
    def _generate_enc_params(url, method, signed_nonce, nonce, params, ssecurity):
        params["rc4_hash__"] = XiaomiCloudConnector._generate_enc_signature(url, method, signed_nonce, params)
        for k, v in params.items():
            params[k] = XiaomiCloudConnector._encrypt_rc4(signed_nonce, v)
        params.update({
            "signature": XiaomiCloudConnector._generate_enc_signature(url, method, signed_nonce, params),
            "ssecurity": ssecurity,
            "_nonce": nonce,
        })
        return params

    @staticmethod
    def _encrypt_rc4(password, payload):
        r = ARC4.new(base64.b64decode(password))
        r.encrypt(bytes(1024))
        return base64.b64encode(r.encrypt(payload.encode())).decode()

    @staticmethod
    def _decrypt_rc4(password, payload):
        r = ARC4.new(base64.b64decode(password))
        r.encrypt(bytes(1024))
        return r.encrypt(base64.b64decode(payload))

    @staticmethod
    def _to_json(response_text):
        return json.loads(response_text.replace("&&&START&&&", ""))
