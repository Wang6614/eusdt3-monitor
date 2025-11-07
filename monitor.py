#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime, timezone

RPC_URL = "https://api.avax.network/ext/bc/C/rpc"

VAULT = os.environ.get("VAULT_ADDRESS","0xE1A62FDcC6666847d5EA752634E45e134B2F824B")
TOKEN = "0x9702230A8Ea53601f5Cd2dc00fDBC13d4dF4A8c7"  # USDT
DECIMALS = 6

TG_BOT = os.environ.get("TG_BOT_TOKEN","")
TG_CHAT = os.environ.get("TG_CHAT_ID","")

POLL = 1
THRESH = 1
COOLDOWN = 30

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def call(method, params):
    return requests.post(RPC_URL, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=5).json()

def balance(addr):
    data = call("eth_call",[{
        "to": TOKEN,
        "data": "0x70a08231" + addr[2:].rjust(64,"0")
    },"latest"])
    raw = int(data["result"],16)
    return raw/(10**DECIMALS)

def send(msg):
    if not TG_BOT or not TG_CHAT:
        print("[WARN] No Telegram config:", msg); return
    requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
        json={"chat_id":TG_CHAT,"text":msg})

def main():
    last = balance(VAULT)
    send(f"🟢 监控启动\n池子余额: {last:.2f} USDT\n时间: {ts()}")
    last_alert = 0
    while True:
        try:
            now = balance(VAULT)
            diff = now - last
            if diff >= THRESH and time.time()-last_alert>=COOLDOWN:
                send(f"🚨 发现流动性补充！\n当前: {now:.2f} USDT\n增加: +{diff:.2f} USDT\n时间: {ts()}")
                last_alert = time.time()
                last = now
            elif now < last:
                last = now
        except Exception as e:
            print("err",e)
        time.sleep(POLL)

if __name__=="__main__":
    main()
