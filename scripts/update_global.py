"""
更新最新一筆台股資料的全球市場欄位（美股收盤後執行）
每天 UTC 21:00（台灣凌晨 5am）由 GitHub Actions 執行
"""

import json, requests, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone

DATA_PATH   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')
LATEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data-latest.json')

YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

YF_SYMBOLS = {
    'sp500':   '^GSPC',
    'nasdaq':  '^IXIC',
    'vix':     '^VIX',
    'us10y':   '^TNX',
    'gold':    'GC=F',
    'oil':     'CL=F',
    'sox':     '^SOX',
    'usdtwd':  'TWD=X',
    'jpytwd':  'JPYTWD=X',
    'tsm_adr': 'TSM',
    'smh':     'SMH',
    'qqq':     'QQQ',
    'xle':     'XLE',
}

def fetch_yf_quote(symbol):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d'
    try:
        d = requests.get(url, headers=YF_HEADERS, timeout=15).json()
        meta  = d['chart']['result'][0]['meta']
        close = meta.get('regularMarketPrice') or meta.get('previousClose')
        prev  = meta.get('chartPreviousClose') or meta.get('previousClose', close)
        chg_pct = round((close - prev) / prev * 100, 2) if prev else 0
        return round(close, 2), chg_pct
    except Exception:
        return None, None

def fetch_global():
    result = {}
    with ThreadPoolExecutor(max_workers=len(YF_SYMBOLS)) as ex:
        futures = {ex.submit(fetch_yf_quote, sym): key for key, sym in YF_SYMBOLS.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val, chg = fut.result()
            except Exception:
                val, chg = None, None
            if val is not None:
                result[key] = val
                result[f'{key}_chg'] = chg
    return result if result else None

def main():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    if not history:
        print('[跳過] data.json 為空')
        return

    latest_entry = sorted(history, key=lambda x: x['date'])[-1]
    entry_date = date(int(latest_entry['date'][:4]), int(latest_entry['date'][4:6]), int(latest_entry['date'][6:8]))
    days_behind = (date.today() - entry_date).days
    if days_behind > 5:
        print(f'[警告] 最新資料為 {latest_entry["date"]}，距今 {days_behind} 天（可能假期），仍繼續更新')
    print(f'[開始] 更新 {latest_entry["date"]} 的全球市場資料')

    global_data = fetch_global()
    if not global_data:
        print('[失敗] 無法取得全球市場資料')
        return

    sp  = global_data.get('sp500')
    vix = global_data.get('vix')
    jpy = global_data.get('jpytwd')
    print(f'  S&P500={sp}  VIX={vix}  JPY/TWD={jpy}')

    # UTC 21:00 執行時，美股收盤日 = UTC 當日
    us_date = datetime.now(timezone.utc).date()
    us_close_date = f'{us_date.month:02d}/{us_date.day:02d}'

    for entry in history:
        if entry['date'] == latest_entry['date']:
            entry['global'] = global_data
            entry['us_close_date'] = us_close_date
            break

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    latest = sorted(history, key=lambda x: x['date'])[-10:]
    with open(LATEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f'[完成] {latest_entry["date"]} 全球資料已更新（美股 {us_close_date} 收盤）')

if __name__ == '__main__':
    main()
