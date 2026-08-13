import sys
import urllib.error
import urllib.request


def main() -> int:
    path = (
        "/health/ready"
        if len(sys.argv) < 2 or sys.argv[1] == "ready"
        else "/health/live"
    )
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:8000{path}", timeout=2
        ) as response:
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, TimeoutError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
