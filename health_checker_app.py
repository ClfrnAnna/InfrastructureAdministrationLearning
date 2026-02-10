import requests
import time
import sys
import os

APP1_URL = os.getenv('APP1_URL', 'http://fastapi-app1:8000/healthy')
APP2_URL = os.getenv('APP2_URL', 'http://fastapi-app2:8000/healthy')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))


def check_app(url, app_name):
    try:
        response = requests.get(url, timeout=5)
        status = response.status_code
        print(f"{app_name}: HTTP {status}")
        return status
    except requests.exceptions.RequestException as e:
        print(f"{app_name}: ERROR - {e}")
        return None


def main():
    print(f"HealthChecker started!. Interval - {CHECK_INTERVAL} seconds.")
    print(f"App1: {APP1_URL}")
    print(f"App2: {APP2_URL}")
    print("-" * 50)

    check_count = 0

    while True:
        check_count += 1
        print(f"\nCheck #{check_count} - {time.ctime()}")

        status1 = check_app(APP1_URL, "App1")
        status2 = check_app(APP2_URL, "App2")

        if status1 == 503 or status2 == 503:
            print("\n CRITICAL: One or more applications returned 503!")
            print(f"   App1: {status1}, App2: {status2}")
            sys.exit(1)

        if status1 == 200 and status2 == 200:
            print("\n OK")
        else:
            print(f"\n WARNING: At least one application has a problem")
            print(f"   App1: {status1}, App2: {status2}")

        print(f"\n Starting interval - {CHECK_INTERVAL} seconds")
        print("-" * 50)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()