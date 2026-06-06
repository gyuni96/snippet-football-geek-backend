"""X 로그인 세션을 Playwright storage state 파일로 저장합니다."""

import argparse
from importlib import import_module


def main() -> None:
    parser = argparse.ArgumentParser(description="X 로그인 세션을 storage state 파일로 저장합니다.")
    parser.add_argument("--output", default="x_storage_state.json")
    parser.add_argument("--login-url", default="https://x.com/login")
    args = parser.parse_args()

    sync_playwright = _load_sync_playwright()
    with sync_playwright as playwright:
        with playwright.chromium.launch(headless=False) as browser:
            with browser.new_context() as context:
                page = context.new_page()
                page.goto(args.login_url, wait_until="domcontentloaded", timeout=60000)
                input("브라우저에서 X 로그인을 완료한 뒤 Enter를 누르면 세션을 저장합니다: ")
                context.storage_state(path=args.output)
                print(f"X storage_state saved to {args.output}")


def _load_sync_playwright():
    try:
        playwright_module = import_module("playwright.sync_api")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "playwright is required. Install it with `python3 -m pip install playwright` "
            "and run `python3 -m playwright install chromium`."
        ) from error
    return playwright_module.sync_playwright()


if __name__ == "__main__":
    main()
