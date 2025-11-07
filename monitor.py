#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AVAX eUSDt-3 / Euler pool liquidity monitor → Telegram alert (1s-capable)
- Polls Snowtrace USDT balance of the vault address
- When balance increases by >= ALERT_THRESHOLD, sends a Telegram alert
- Supports MAX_RUNTIME_SECONDS to run inside GitHub Actions for ~55min per job
"""
import os
import time
import requests
from datetime import datetime, timezone

VAULT_ADDRESS = os.environ.get("VAULT_ADDRESS", "0xE1A62FDcC6666847d5EA752634E45e134B2F824B").lower()
USDT_TOKEN    = os.environ.get("USDT_TOKEN", "0x9702230A8Ea53601f5Cd2dc00fDBC13d4dF4A8c7").lower()  # AVAX C-Chain USDT
DECIMALS      = int(os.environ.get("DECIMALS", "6"))

SNOWTRACE_API_KEY = os.environ.get("SNOWTRACE_API_KEY", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "").strip()

# 1-second polling supported
POLL_SECONDS     = max(1, int(os.environ.get("POLL_SECONDS", "1")))
ALERT_THRESHOLD  = float(os.environ.get("ALERT_THRESHOLD", "1"))  # in USDT units
ALERT_COOLDOWN_S = int(os.environ.get("ALERT_COOLDOWN", "30"))    # seconds
MAX_RUNTIME_S    = int(os.environ.get("MAX_RUNTIME_SECONDS", "3300"))  # ~55min by default for GH Actions

def now_ts():
    return int(time.time())

def ts_str(ts=None):
    if ts is None:
        ts = now_ts()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def get_token_balance_snowtrace(token_addr, holder_addr, api_key):
    """
    https://snowtrace.io/apis#accounts
    module=account&action=tokenbalance&contractaddress=TOKEN&address=HOLDER&tag=latest&apikey=KEY
    Returns float balance in token units (USDT: 6 decimals on AVAX)
    """
    url = "https://api.snowtrace.io/api"
    params = {
        "module": "account",
        "action": "tokenbalance",
        "contractaddress": token_addr,
        "address": holder_addr,
        "tag": "latest",
        "apikey": api_key
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    raw = data.get("result", "0")
    try:
        val = int(raw)
    except Exception:
        val = 0
    return val / (10 ** DECIMALS)

def tg_send(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[WARN] Telegram not configured; message:\n", text)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("[WARN] Telegram send failed:", r.text[:200])
    except Exception as e:
        print("[WARN] Telegram error:", e)

def fmt(x):
    return f"{x:,.6f}" if abs(x) < 1000 else f"{x:,.2f}"

def main():
    if not SNOWTRACE_API_KEY:
        print("ERROR: missing SNOWTRACE_API_KEY")
        return 1

    start_ts = now_ts()
    last = None
    last_alert_ts = 0

    # Warm-up read
    try:
        bal = get_token_balance_snowtrace(USDT_TOKEN, VAULT_ADDRESS, SNOWTRACE_API_KEY)
        last = bal
        tg_send(
            "🟢 监控已启动 (1s)\n"
            f"Pool: eUSDt-3\nVault: {VAULT_ADDRESS}\n"
            f"当前池子余额: {fmt(bal)} USDT\n时间: {ts_str()}"
        )
    except Exception as e:
        print("Initial read failed:", e)
        return 1

    while True:
        try:
            # Stop gracefully in Actions to avoid 60min hard timeout
            if now_ts() - start_ts >= MAX_RUNTIME_S:
                print("[*] Reached MAX_RUNTIME_SECONDS; exiting gracefully.")
                break

            bal = get_token_balance_snowtrace(USDT_TOKEN, VAULT_ADDRESS, SNOWTRACE_API_KEY)
            if last is None:
                last = bal
            delta = bal - last

            # Positive spike above threshold, and cooldown passed
            if delta >= ALERT_THRESHOLD and (now_ts() - last_alert_ts) >= ALERT_COOLDOWN_S:
                last_alert_ts = now_ts()
                msg = (
                    "🚨 eUSDt-3 流动性补充！\n"
                    f"当前池子余额: {fmt(bal)} USDT\n"
                    f"本次新增: +{fmt(delta)} USDT\n"
                    f"时间: {ts_str()}\n\n"
                    "👉 立刻打开 OKX Web3 → DeFi → 赎回（窗口通常仅数秒到数十秒）"
                )
                print(msg)
                tg_send(msg)
                last = bal  # reset baseline to current

            # If balance dropped (window got drained), move the baseline down
            elif bal < last:
                last = bal

        except Exception as e:
            print("[WARN] loop error:", e)

        time.sleep(POLL_SECONDS)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
