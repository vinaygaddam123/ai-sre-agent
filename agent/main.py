import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:30090")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))

# Alerts that are always on, or caused by our setup. Not real incidents.
IGNORED_ALERTS = {"Watchdog", "PrometheusNotConnectedToAlertmanagers", "InfoInhibitor"}

# Remember which alerts we already analysed so we don't repeat ourselves.
seen = set()


def get_firing_alerts():
    """Ask Prometheus for all alerts and keep the real, firing ones."""
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=10)
    resp.raise_for_status()
    alerts = resp.json()["data"]["alerts"]
    return [
        a for a in alerts
        if a["state"] == "firing"
        and a["labels"].get("alertname") not in IGNORED_ALERTS
    ]


def analyse(alert):
    """Send one alert to Gemini and return its root-cause analysis.
    Retries a few times because Gemini sometimes answers 503 (overloaded)."""
    labels = alert["labels"]
    annotations = alert.get("annotations", {})
    prompt = (
        "You are an SRE assistant. A Kubernetes alert fired.\n"
        f"Alert labels: {labels}\n"
        f"Alert annotations: {annotations}\n"
        "In under 150 words give: 1) likely root cause, "
        "2) how to confirm it, 3) how to fix it."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    for attempt in range(1, 7):
        resp = requests.post(
            url,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        if resp.status_code in (429, 500, 503):
            print(f"Gemini busy (HTTP {resp.status_code}), retry {attempt}/6")
            time.sleep(5 * attempt)
            continue
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError("Gemini still unavailable after 6 tries")


def main():
    if not GEMINI_API_KEY or not GEMINI_MODEL:
        raise SystemExit("Set GEMINI_API_KEY and GEMINI_MODEL in .env")
    print(f"Agent started. Polling {PROMETHEUS_URL} every {POLL_SECONDS}s")
    while True:
        try:
            for alert in get_firing_alerts():
                labels = alert["labels"]
                key = (labels.get("alertname"), labels.get("namespace"), labels.get("pod"))
                if key in seen:
                    continue
                print(f"\n[{datetime.now():%H:%M:%S}] ALERT: {key}")
                print(analyse(alert))
                seen.add(key)
        except Exception as exc:  # keep running even if one poll fails
            print(f"Error: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()