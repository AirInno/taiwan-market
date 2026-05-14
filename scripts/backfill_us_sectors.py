"""
補填歷史 global 資料中缺少的美股產業指標（TSM ADR / SMH / QQQ / XLE）
"""
import sys, io, json, requests
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

DATA_PATH = 'data.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
NEW_SYMBOLS = {'tsm_adr': 'TSM', 'smh': 'SMH', 'qqq': 'QQQ', 'xle': 'XLE'}

def tw_to_us_date(tw_date_str):
    dt = datetime.strptime(tw_date_str, '%Y%m%d')
    sub = 3 if dt.weekday() == 0 else 1  # 台灣週一 → 美股上週五
    return (dt - timedelta(days=sub)).strftime('%Y-%m-%d')

def fetch_hist(symbol, start_dt, end_dt):
    start_ts = int(start_dt.replace(tzinfo=timezone.utc).timestamp())
    end_ts   = int(end_dt.replace(tzinfo=timezone.utc).timestamp()) + 86400
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&period1={start_ts}&period2={end_ts}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=30).json()
        result = r['chart']['result'][0]
        tss    = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        prices, prev = {}, None
        for ts, c in zip(tss, closes):
            if c is None:
                continue
            d   = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
            chg = round((c - prev) / prev * 100, 2) if prev else 0
            prices[d] = (round(c, 2), chg)
            prev = c
        return prices
    except Exception as e:
        print(f'  [WARN] {symbol} 抓取失敗：{e}')
        return {}

def main():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    to_fill = [e for e in history if e.get('global', {}).get('sp500') and 'smh' not in e.get('global', {})]
    if not to_fill:
        print('[完成] 所有資料都已有美股指標，無需補填')
        return
    print(f'[開始] 需補填 {len(to_fill)} 筆')

    us_dates = [tw_to_us_date(e['date']) for e in to_fill]
    start_dt = datetime.strptime(min(us_dates), '%Y-%m-%d') - timedelta(days=5)
    end_dt   = datetime.strptime(max(us_dates), '%Y-%m-%d') + timedelta(days=2)

    all_prices = {}
    for key, sym in NEW_SYMBOLS.items():
        print(f'  抓取 {sym} ({start_dt.date()} ~ {end_dt.date()})...')
        all_prices[key] = fetch_hist(sym, start_dt, end_dt)

    filled, skipped = 0, 0
    for entry in history:
        if not (entry.get('global', {}).get('sp500') and 'smh' not in entry.get('global', {})):
            continue
        us_date = tw_to_us_date(entry['date'])
        if all(us_date in all_prices[k] for k in NEW_SYMBOLS):
            for key in NEW_SYMBOLS:
                price, chg = all_prices[key][us_date]
                entry['global'][key]            = price
                entry['global'][f'{key}_chg']   = chg
            filled += 1
        else:
            skipped += 1

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f'[完成] 補填 {filled} 筆，跳過 {skipped} 筆（美股無對應交易日）')

if __name__ == '__main__':
    main()
