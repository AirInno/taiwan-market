"""
台股外資動向追蹤 - 自動資料更新腳本
每個交易日收盤後由 GitHub Actions 執行
資料來源：台灣證券交易所公開 API
"""

import json
import requests
import sys
import os
from datetime import date, timedelta

# ── 設定 ──────────────────────────────────────────────
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.twse.com.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

# ── 警示等級邏輯 ───────────────────────────────────────

def market_alert(foreign_bn, consecutive):
    """整體市場警示（依外資億元 + 連續賣超天數）"""
    if foreign_bn >= -50 and consecutive < 3:
        return '正常'
    elif foreign_bn >= -100 or consecutive < 5:
        return '注意'
    elif foreign_bn >= -200 or consecutive < 8:
        return '高度警戒'
    else:
        return '極度警戒'

def tsmc_alert(net_z):
    """台積電警示（依外資淨買賣超張數）"""
    if net_z >= -15000:
        return '正常'
    elif net_z >= -25000:
        return '注意'
    elif net_z >= -40000:
        return '高度警戒'
    else:
        return '極度警戒'

def etf0050_alert(net_z):
    """0050 警示（依外資淨買賣超張數）"""
    if net_z >= -5000:
        return '正常'
    elif net_z >= -10000:
        return '注意'
    elif net_z >= -25000:
        return '高度警戒'
    else:
        return '極度警戒'

# ── TWSE API 呼叫 ─────────────────────────────────────

def fetch_bfi82u(date_str):
    """三大法人買賣金額統計 → 外資整體、投信整體（億元）"""
    url = f'https://www.twse.com.tw/rwd/zh/fund/bfi82u?date={date_str}&response=json'
    r = requests.get(url, headers=HEADERS, timeout=30)
    d = r.json()
    if d.get('stat') != 'OK' or not d.get('data'):
        return None, None

    foreign_buy = foreign_sell = it_buy = it_sell = 0
    for row in d['data']:
        name = row[0].strip()
        try:
            buy  = float(row[1].replace(',', ''))
            sell = float(row[2].replace(',', ''))
        except (ValueError, IndexError):
            continue
        if '外資及陸資(不含' in name:
            foreign_buy, foreign_sell = buy, sell
        elif name == '投信':
            it_buy, it_sell = buy, sell

    foreign_bn = round((foreign_buy - foreign_sell) / 1e8, 2)
    it_bn      = round((it_buy - it_sell) / 1e8, 2)
    return foreign_bn, it_bn


def fetch_t86(date_str):
    """個股三大法人買賣超 → top5 排行 + 台積電/0050 個別資料"""
    url = f'https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json'
    r = requests.get(url, headers=HEADERS, timeout=30)
    d = r.json()
    if d.get('stat') != 'OK' or not d.get('data'):
        return None

    stocks = []
    for row in d['data']:
        code = row[0].strip()
        name = row[1].strip()
        try:
            # 欄位 4 = 外陸資買賣超股數，欄位 7 = 投信買賣超股數
            f_net = int(row[4].replace(',', '').replace('+', '')) // 1000  # 轉張
            i_net = int(row[7].replace(',', '').replace('+', '')) // 1000
        except (ValueError, IndexError):
            continue
        stocks.append({'code': code, 'name': name, 'f': f_net, 'i': i_net})

    return stocks


def fetch_fmtqik(date_str):
    """大盤每日行情 → 收盤指數、漲跌點數"""
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={date_str}&response=json'
    r = requests.get(url, headers=HEADERS, timeout=30)
    d = r.json()
    if d.get('stat') != 'OK' or not d.get('data'):
        return None, None

    # 轉換民國日期格式
    y_roc = int(date_str[:4]) - 1911
    m, day = int(date_str[4:6]), int(date_str[6:8])
    target = f'{y_roc}/{m:02d}/{day:02d}'

    for row in d['data']:
        if row[0].strip() == target:
            try:
                close  = float(row[4].replace(',', ''))
                change = float(row[5].replace(',', '').replace('+', ''))
                return close, change
            except (ValueError, IndexError):
                pass

    # 找不到特定日期（非交易日）
    return None, None

# ── 主流程 ────────────────────────────────────────────

def get_target_date():
    """取得最近的交易日（週末退回週五）"""
    today = date.today()
    for i in range(7):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def top5(stocks, key, ascending=False):
    filtered = [s for s in stocks if s[key] != 0]
    return sorted(filtered, key=lambda x: x[key], reverse=not ascending)[:5]


def main():
    # 讀取現有資料
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    target = get_target_date()
    existing = {d['date'] for d in history}

    if target in existing:
        print(f'[跳過] {target} 的資料已存在')
        sys.exit(0)

    print(f'[開始] 抓取 {target} 的資料...')

    # 1. 整體外資、投信（億元）
    foreign_bn, it_bn = fetch_bfi82u(target)
    if foreign_bn is None:
        print(f'[跳過] {target} 可能為非交易日（bfi82u 無資料）')
        sys.exit(0)

    # 2. 大盤收盤
    close, change = fetch_fmtqik(target)
    if close is None:
        print(f'[跳過] {target} 無大盤收盤資料')
        sys.exit(0)

    # 3. 個股三大法人
    stocks = fetch_t86(target)
    if stocks is None:
        print(f'[錯誤] 無法取得個股資料')
        sys.exit(1)

    # 衍生欄位計算
    last = history[-1] if history else {}
    prev_consecutive = last.get('連續賣超', 0)
    consecutive = (prev_consecutive + 1) if foreign_bn < 0 else 0

    hedge = round(it_bn / abs(foreign_bn) * 100, 1) if (foreign_bn < 0 and it_bn > 0) else 0

    alert = market_alert(foreign_bn, consecutive)

    # 個股：台積電 (2330) / 0050
    tsmc   = next((s for s in stocks if s['code'] == '2330'), {'f': 0, 'i': 0})
    e0050  = next((s for s in stocks if s['code'] == '0050'), {'f': 0, 'i': 0})

    # Top 5 列表
    fb = top5(stocks, 'f', ascending=False)  # 外資買超
    fs = top5(stocks, 'f', ascending=True)   # 外資賣超
    ib = top5(stocks, 'i', ascending=False)  # 投信買超
    is_ = top5(stocks, 'i', ascending=True)  # 投信賣超

    def fmt_list(items, key):
        return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]

    month, day = target[4:6], target[6:8]

    new_entry = {
        'date':       target,
        'dateLabel':  f'{month}/{day}',
        '外資億元':    foreign_bn,
        '投信億元':    it_bn,
        '收盤':        close,
        '漲跌':        change,
        '連續賣超':    consecutive,
        '警示':        alert,
        'tsmc外資':    tsmc['f'],
        'tsmc投信':    tsmc['i'],
        'tsmc警示':    tsmc_alert(tsmc['f']),
        'etf0050外資': e0050['f'],
        'etf0050投信': e0050['i'],
        'etf0050警示': etf0050_alert(e0050['f']),
        '護盤比':      hedge,
        '外資買超':    fmt_list(fb, 'f'),
        '外資賣超':    fmt_list(fs, 'f'),
        '投信買超':    fmt_list(ib, 'i'),
        '投信賣超':    fmt_list(is_, 'i'),
    }

    history.append(new_entry)

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f'[完成] {target}｜外資 {foreign_bn:+.2f}億｜投信 {it_bn:+.2f}億｜收盤 {close:,.2f}｜{alert}')


if __name__ == '__main__':
    main()
