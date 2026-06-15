"""Test Mi Cloud login and device listing"""
import logging
import sys

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                    format='%(levelname)s:%(name)s:%(message)s')

try:
    from miio.cloud import CloudInterface, CloudException, AVAILABLE_LOCALES
    print(f"Available locales: {AVAILABLE_LOCALES}")

    ci = CloudInterface('test@test.com', 'wrongpass')
    try:
        devs = ci.get_devices(locale='cn')
        print(f"Devices found: {len(devs)}")
    except CloudException as e:
        print(f"CloudException: {e}")
    except Exception as e:
        print(f"Other error: {type(e).__name__}: {e}")

    print("\n--- Checking micloud directly ---")
    from micloud import MiCloud
    from micloud.micloudexception import MiCloudAccessDenied

    mc = MiCloud('test@test.com', 'wrongpass')
    try:
        result = mc.get_devices(country='cn')
        print(f"micloud result type: {type(result)}")
        if result:
            print(f"Devices count: {len(result)}")
    except MiCloudAccessDenied as e:
        print(f"AccessDenied: {e}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    print(f"Unexpected: {type(e).__name__}: {e}")
