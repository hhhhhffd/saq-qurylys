"""Check the three control scenarios of the case (SPEC 6.6) against a running SAQ QURYLYS stack.

Usage (after `docker compose up -d --build` and `python -m app.seed --demo`):

    python3 scripts/verify_case_scenarios.py [--base-url http://localhost:8000]

Credentials come from the environment (SAQ_USERNAME / SAQ_PASSWORD) or, if absent, from INITIAL_ADMIN_USERNAME /
INITIAL_ADMIN_PASSWORD in ./.env. Uses only the standard library. Exit code 0 = all scenarios match.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# alias of the demo object -> (expected score, expected zone, factor codes that must fire, factor codes that must not)
SCENARIOS = {
    "Сценарий A": (35, "yellow", {"r2_money_offer", "r3_active_ads"}, {"r1_no_legal_basis"}),
    "Сценарий B": (70, "red", {"r1_no_legal_basis", "r2_money_offer", "r3_active_ads"}, set()),
    "Сценарий C": (10, "green", {"r3_active_ads"}, {"r1_no_legal_basis", "r2_money_offer"}),
}


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def request(base_url: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    # The scheme of base_url is restricted to http(s) in main().
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method="POST" if body else "GET")  # noqa: S310
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
        return json.load(response)


def check_scenario(base_url: str, token: str, alias: str) -> list[str]:
    expected_score, expected_zone, must_fire, must_not_fire = SCENARIOS[alias]
    found = request(base_url, "/api/v1/objects?" + urllib.parse.urlencode({"q": alias}), token)["items"]
    if len(found) != 1:
        return [f"{alias}: expected exactly one demo object, found {len(found)} (was `seed --demo` run?)"]
    detail = request(base_url, f"/api/v1/objects/{found[0]['id']}", token)
    score = detail.get("latest_score")
    if score is None:
        return [f"{alias}: object is not scored yet (is the worker running?)"]
    fired = {factor["code"] for factor in score["breakdown"]["factors"] if factor["triggered"]}
    problems = []
    if score["score"] != expected_score or score["zone"] != expected_zone:
        problems.append(f"{alias}: got {score['score']} {score['zone']}, expected {expected_score} {expected_zone}")
    if missing := must_fire - fired:
        problems.append(f"{alias}: factors not triggered: {sorted(missing)}")
    if unexpected := must_not_fire & fired:
        problems.append(f"{alias}: factors must not trigger: {sorted(unexpected)}")
    status = "OK  " if not problems else "FAIL"
    print(f"{status} {alias} «{detail['name']}»: {score['score']} {score['zone']}, factors {sorted(fired)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    if urllib.parse.urlsplit(args.base_url).scheme not in ("http", "https"):
        parser.error("--base-url must be an http(s) URL")
    dotenv = read_dotenv(Path(".env"))
    username = os.environ.get("SAQ_USERNAME") or dotenv.get("INITIAL_ADMIN_USERNAME", "admin")
    password = os.environ.get("SAQ_PASSWORD") or dotenv.get("INITIAL_ADMIN_PASSWORD", "")
    try:
        token = request(args.base_url, "/api/v1/auth/login", body={"username": username, "password": password})[
            "access_token"
        ]
        problems = [problem for alias in SCENARIOS for problem in check_scenario(args.base_url, token, alias)]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as error:
        print(f"Cannot query the API at {args.base_url}: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
