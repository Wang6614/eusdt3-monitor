#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AVAX eUSDt-3 / Euler pool liquidity monitor → Telegram alert (1s)
- 无需 Snowtrace API Key
- 直接通过 Avalanche C-Chain RPC 调用 USDT.balanceOf(vault)
- 余额上涨(=补流动性)达到阈值时推送 Telegram
"""

import os
import time
import requests
from datetime import datetime, timezone

# 目标池子（你的 vault）
VAULT_ADDRESS = os.environ.get(
    "VAULT_ADDRESS",
    "0xE1A62FDcC6666847d5EA752634E45e134B2F824B"
).lower()

# AVAX C-Chain USDT 合约 & 小数
USDT_TOKEN = os.environ.get(
    "USDT_TOKEN",
    "0x9702230A8Ea53601f5Cd2dc00fDBC13d4dF4A8c7"
).lower()
DECIMALS = int(os.environ.get("DECIMALS", "6"))

# 公共 RPC（官方主网）
AVAX_RPC = os.environ.get(
    "AVAX_RPC",
    "https://api.avax.network/ext/bc/C/rpc"
).strip()

# Telegram
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "").strip()

# 轮询与告警参数
POLL_SECONDS     = max(1, int(os.environ.get("POLL_SECONDS", "1")))   # 1 秒
ALERT_THRESHOLD  = float(os.environ.get("ALERT_THRESHOLD", "1"))      # 阈值(USDT)
ALERT_COOLDOWN_S = int(os.environ.get("ALERT_COOLDOWN", "30"))        # 冷却(秒)
MAX_RUNTIME_S    = int(os.environ.get("MAX_RUNTIME_SECONDS", "3300")) # ~55 分钟

def now_ts():
    return int(time.time())

def ts_str(ts=None):
    if ts is None:
        ts = now_ts()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def pad32(hex_without_0x: str) -> str:
    return hex_without_0x.rjust(64, "0")

def addr_to_abi_word(addr: str) -> str:
    # 0x + 24个字节填充 + 20字节地址
    a = addr.lower().replace("0x", "")
    return pad32(a)

def encode_balance_of(holder: str) -> str:
    # function balanceOf(address) -> selector 0x70a08231
    selector = "70a08231"
    return "0x" + selector + addr_to_abi_word(holder)

def rpc_eth_call(contract: str, data: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": contract, "data": data},
            "latest"
        ]
    }
    r = requests.post(AVAX_RPC, json=payload, timeout=10)
    r.raise_for_status()
    j = r.json()
    if "result" not in j:
        raise RuntimeError(f"eth_call no result: {j}")
    return j["result"]  # 0x...

def get_erc20_balance_via_rpc(token_addr: str, holder_addr: str, decimals: int) -> float:
    data = encode_balance_of(holder_addr)
    res_hex = rpc_eth_call(token_addr, data)  # e.g. 0x000...1234
    val = int(res_hex, 16)
    return val / (10 ** decimals)

def tg_send(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[WARN] Telegram 未配置，消息如下：\n", text)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("[WARN] Telegram 发送失败:", r.text[:200])
    except Exception as e:
        print("[WARN] Telegram 异常:", e)

def fmt(x):
    return f"{x:,.6f}" if abs(x) < 1000 else f"{x:,.2f}"

def main():
    start_ts = now_ts()
    last = None
    last_alert_ts = 0

    try:
        bal = get_erc20_balance_via_rpc(USDT_TOKEN, VAULT_ADDRESS, DECIMALS)
        last = bal
        tg_send(
            "🟢 监控已启动 (1s, RPC)\n"
            f"Pool: eUSDt-3\nVault: {VAULT_ADDRESS}\n"
            f"当前池子余额: {fmt(bal)} USDT\n时间: {ts_str()}"
        )
    except Exception as e:
        print("初次读取失败:", e)
        return 1

    while True:
        try:
            if now_ts() - start_ts >= MAX_RUNTIME_S:
                print("[*] 达到 MAX_RUNTIME_SECONDS，正常退出。")
                break

            bal = get_erc20_balance_via_rpc(USDT_TOKEN, VAULT_ADDRESS, DECIMALS)
            if last is None:
                last = bal
            delta = bal - last

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
                last = bal
            elif bal < last:
                # 窗口被抢走，基线下移
                last = bal

        except Exception as e:
            print("[WARN] 循环异常:", e)

        time.sleep(POLL_SECONDS)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
