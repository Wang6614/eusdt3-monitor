#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# AVAX eUSDt-3 / USDT 余额监控（1s 轮询、无 API Key）
import os, time, requests
from datetime import datetime, timezone

RPC_URL      = os.environ.get("RPC_URL", "https://api.avax.network/ext/bc/C/rpc").strip()
VAULT        = os.environ.get("VAULT_ADDRESS", "0xE1A62FDcC6666847d5EA752634E45e134B2F824B").lower()
TOKEN        = os.environ.get("USDT_TOKEN",    "0x9702230A8Ea53601f5Cd2dc00fDBC13d4DF4A8c7").lower()
DECIMALS     = int(os.environ.get("DECIMALS", "6"))

POLL         = max(1, int(os.environ.get("POLL_SECONDS", "1")))
THRESH       = float(os.environ.get("ALERT_THRESHOLD", "10"))    # >= 触发提醒的新增 USDT
COOLDOWN     = int(os.environ.get("ALERT_COOLDOWN", "30"))       # 冷却秒
MAX_RUN      = int(os.environ.get("MAX_RUNTIME_SECONDS", "3300"))

TG_BOT       = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT      = os.environ.get("TG_CHAT_ID", "").strip()

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def rpc(method, params):
    r = requests.post(
        RPC_URL,
        json={"jsonrpc":"2.0","id":1,"method":method,"params":params},
        timeout=10,
    )
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j["result"]

def erc20_balance(token, holder):
    # balanceOf(address) -> bytes4 0x70a08231
    data = "0x70a08231" + holder[2:].rjust(64, "0")
    res = rpc("eth_call", [{"to": token, "data": data}, "latest"])
    raw = int(res, 16)
    return raw / (10 ** DECIMALS)

def tg_send(text):
    if not TG_BOT or not TG_CHAT:
        print("[WARN] TG 未配置，消息为：\n", text)
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text},
            timeout=10,
        )
        if r.status_code != 200:
            print("[WARN] TG 发送失败：", r.text[:200])
    except Exception as e:
        print("[WARN] TG 异常：", e)

def fmt(x):
    return f"{x:,.6f}" if abs(x) < 1000 else f"{x:,.2f}"

def main():
    start = time.time()
    last  = erc20_balance(TOKEN, VAULT)
    last_alert = 0
    tg_send(f"🟢 监控启动 (1s)\n池: eUSDt-3\nVault: {VAULT}\n当前池子余额: {fmt(last)} USDT\n时间: {ts()}")

    while True:
        try:
            if time.time() - start >= MAX_RUN:
                print("[*] 达到单次运行上限，正常退出。")
                break

            bal = erc20_balance(TOKEN, VAULT)
            diff = bal - last

            if diff >= THRESH and (time.time() - last_alert) >= COOLDOWN:
                last_alert = time.time()
                msg = (
                    "🚨 eUSDt-3 流动性补充！\n"
                    f"当前池子余额: {fmt(bal)} USDT\n"
                    f"本次新增: +{fmt(diff)} USDT\n"
                    f"时间: {ts()}\n\n"
                    "👉 立刻打开 OKX Web3 → DeFi → 赎回（窗口可能只有几秒）"
                )
                print(msg)
                tg_send(msg)
                last = bal
            elif bal < last:
                last = bal

        except Exception as e:
            print("[WARN] 循环错误：", e)

        time.sleep(POLL)

if __name__ == "__main__":
    main()
