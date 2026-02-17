import requests
import time
import sys
import os

APP1_URL = os.getenv('APP1_URL', 'http://fastapi-app1:8000')
APP2_URL = os.getenv('APP2_URL', 'http://fastapi-app2:8000')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 60))


def main():
    print(f"HealthChecker started! Interval - {CHECK_INTERVAL} seconds.")
    print(f"App1: {APP1_URL}/healthy")
    print(f"App2: {APP2_URL}/healthy")
    print("-" * 50)

    check_count = 0

    while True:
        check_count += 1
        print(f"\nCheck #{check_count} - {time.ctime()}")
        try:
            resp1 = requests.get(f"{APP1_URL}/healthy", timeout=5)
            print(f"App1: HTTP {resp1.status_code} - {resp1.json().get('status', 'unknown')}")
            status1 = resp1.status_code
        except Exception as e:
            print(f"App1: ERROR - {e}")
            status1 = 503

        try:
            resp2 = requests.get(f"{APP2_URL}/healthy", timeout=5)
            print(f"App2: HTTP {resp2.status_code} - {resp2.json().get('status', 'unknown')}")
            status2 = resp2.status_code
        except Exception as e:
            print(f"App2: ERROR - {e}")
            status2 = 503

        if status1 == 503 and status2 == 503:
            print("\n CRITICAL: Both applications are down!")
            sys.exit(1)

        if status1 == 200 or status2 == 200:
            print("\n OK: At least one application is healthy")
        else:
            print("\n  WARNING: Mixed status")

        print(f"\nSleeping for {CHECK_INTERVAL} seconds...")
        print("-" * 50)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
