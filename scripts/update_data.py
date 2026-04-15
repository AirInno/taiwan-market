"""
台股外資動向追蹤 - 自動資料更新腳本
每個交易日收盤後由 GitHub Actions 執行

資料來源優先順序：
  台股資料：TWSE（主）→ FinMind（備）
  全球市場：Yahoo Finance（自動）
"""

import json, requests, sys, os, urllib3
from datetime import date, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_PATH    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')
LATEST_PATH  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data-latest.json')
FINMIND_TOKEN = os.environ.get('FINMIND_TOKEN', '')   # 選填，不設定則跳過 FinMind

TWSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.twse.com.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}
YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# ── 警示邏輯 ──────────────────────────────────────────

def market_alert(f, c):
    if f >= -50 and c < 3:   return '正常'
    elif f >= -100 or c < 5: return '注意'
    elif f >= -200 or c < 8: return '高度警戒'
    else:                     return '極度警戒'

def tsmc_alert(n):
    return '正常' if n>=-15000 else '注意' if n>=-25000 else '高度警戒' if n>=-40000 else '極度警戒'

def etf0050_alert(n):
    return '正常' if n>=-5000 else '注意' if n>=-10000 else '高度警戒' if n>=-25000 else '極度警戒'

# ── TWSE API ──────────────────────────────────────────

def fetch_bfi82u(date_str):
    """三大法人整體買賣超（億元）"""
    url = f'https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={date_str}&response=json'
    try:
        d = requests.get(url, headers=TWSE_HEADERS, timeout=30, verify=False).json()
    except Exception:
        return None, None
    if d.get('stat') != 'OK' or not d.get('data'):
        return None, None
    fb=fs=ib=is_=0
    for row in d['data']:
        name = row[0].strip()
        try:
            buy, sell = float(row[1].replace(',','')), float(row[2].replace(',',''))
        except Exception:
            continue
        if '外資及陸資(不含' in name: fb, fs = buy, sell
        elif name == '投信':          ib, is_ = buy, sell
    return round((fb-fs)/1e8, 2), round((ib-is_)/1e8, 2)


def fetch_t86(date_str):
    """個股三大法人買賣超"""
    url = f'https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json'
    try:
        d = requests.get(url, headers=TWSE_HEADERS, timeout=30, verify=False).json()
    except Exception:
        return None
    if d.get('stat') != 'OK' or not d.get('data'):
        return None
    stocks = []
    for row in d['data']:
        try:
            f_net = int(row[4].replace(',','').replace('+','')) // 1000
            i_net = int(row[10].replace(',','').replace('+','')) // 1000
        except Exception:
            continue
        stocks.append({'code': row[0].strip(), 'name': row[1].strip(), 'f': f_net, 'i': i_net})
    return stocks


def fetch_fmtqik(date_str):
    """大盤收盤、漲跌、成交金額億"""
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={date_str}&response=json'
    try:
        d = requests.get(url, headers=TWSE_HEADERS, timeout=30, verify=False).json()
    except Exception:
        return None, None, None
    if d.get('stat') != 'OK' or not d.get('data'):
        return None, None, None
    y_roc = int(date_str[:4]) - 1911
    target = f'{y_roc}/{int(date_str[4:6]):02d}/{int(date_str[6:8]):02d}'
    for row in d['data']:
        if row[0].strip() == target:
            try:
                return (float(row[4].replace(',','')),
                        float(row[5].replace(',','').replace('+','')),
                        round(float(row[2].replace(',',''))/1e8, 2))
            except Exception:
                pass
    return None, None, None

# ── FinMind 備援 ──────────────────────────────────────

def fetch_bfi82u_finmind(date_str):
    """FinMind 備援：三大法人整體（需 FINMIND_TOKEN）"""
    if not FINMIND_TOKEN:
        return None, None
    iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {'dataset': 'TaiwanStockInstitutionalInvestors',
              'start_date': iso, 'end_date': iso, 'token': FINMIND_TOKEN}
    try:
        rows = requests.get(url, params=params, timeout=30).json().get('data', [])
    except Exception:
        return None, None
    fb=fs=ib=is_=0
    for r in rows:
        if r.get('name') == '外資':    fb, fs = r.get('buy',0), r.get('sell',0)
        elif r.get('name') == '投信':  ib, is_ = r.get('buy',0), r.get('sell',0)
    if fb == 0 and fs == 0:
        return None, None
    return round((fb-fs)/1e8, 2), round((ib-is_)/1e8, 2)


def fetch_t86_finmind(date_str):
    """FinMind 備援：個股三大法人（需 FINMIND_TOKEN）"""
    if not FINMIND_TOKEN:
        return None
    iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {'dataset': 'TaiwanStockInstitutionalInvestorsBuySell',
              'start_date': iso, 'end_date': iso, 'token': FINMIND_TOKEN}
    try:
        rows = requests.get(url, params=params, timeout=30).json().get('data', [])
    except Exception:
        return None
    if not rows:
        return None
    # 彙整每支股票的外資/投信淨買超
    stock_map = {}
    for r in rows:
        code = r.get('stock_id','')
        name = r.get('stock_name', code)
        inst = r.get('name','')
        net  = (r.get('buy',0) - r.get('sell',0)) // 1000
        if code not in stock_map:
            stock_map[code] = {'code': code, 'name': name, 'f': 0, 'i': 0}
        if inst == '外資': stock_map[code]['f'] = net
        if inst == '投信': stock_map[code]['i'] = net
    return list(stock_map.values()) if stock_map else None

# ── Yahoo Finance：全球市場 ───────────────────────────

YF_SYMBOLS = {
    'sp500':   '^GSPC',
    'nasdaq':  '^IXIC',
    'vix':     '^VIX',
    'us10y':   '^TNX',
    'gold':    'GC=F',
    'sox':     '^SOX',
    'usdtwd':  'TWD=X',
}

def fetch_yf_quote(symbol):
    """Yahoo Finance 取得最新收盤與漲跌幅"""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d'
    try:
        d = requests.get(url, headers=YF_HEADERS, timeout=15).json()
        meta   = d['chart']['result'][0]['meta']
        close  = meta.get('regularMarketPrice') or meta.get('previousClose')
        prev   = meta.get('chartPreviousClose') or meta.get('previousClose', close)
        chg_pct = round((close - prev) / prev * 100, 2) if prev else 0
        return round(close, 2), chg_pct
    except Exception:
        return None, None


def fetch_global():
    """抓取全球市場指標，失敗欄位留 None"""
    result = {}
    for key, symbol in YF_SYMBOLS.items():
        val, chg = fetch_yf_quote(symbol)
        if val is not None:
            result[key]           = val
            result[f'{key}_chg']  = chg
    return result if result else None

# ── 主流程 ────────────────────────────────────────────

def get_target_date():
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
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    target = get_target_date()
    if target in {d['date'] for d in history}:
        print(f'[跳過] {target} 已存在')
        sys.exit(0)

    print(f'[開始] {target}')

    # 1. 三大法人整體（TWSE → FinMind 備援）
    foreign_bn, it_bn = fetch_bfi82u(target)
    if foreign_bn is None:
        print('  TWSE bfi82u 無資料，嘗試 FinMind...')
        foreign_bn, it_bn = fetch_bfi82u_finmind(target)
    if foreign_bn is None:
        print(f'[跳過] {target} 非交易日或無法取得三大法人資料')
        sys.exit(0)

    # 2. 大盤收盤 + 成交量
    close, change, vol_bn = fetch_fmtqik(target)
    if close is None:
        print(f'[跳過] {target} 無大盤收盤資料')
        sys.exit(0)

    # 3. 個股三大法人（TWSE → FinMind 備援）
    stocks = fetch_t86(target)
    if stocks is None:
        print('  TWSE T86 無資料，嘗試 FinMind...')
        stocks = fetch_t86_finmind(target)
    if stocks is None:
        print(f'[錯誤] 無法取得個股資料')
        sys.exit(1)

    # 4. 全球市場（Yahoo Finance，失敗不中止）
    print('  抓取全球市場...')
    global_data = fetch_global()
    if global_data:
        print(f'  S&P500={global_data.get("sp500")}  VIX={global_data.get("vix")}  黃金={global_data.get("gold")}')
    else:
        print('  全球市場資料暫時無法取得，跳過')

    # 衍生欄位
    last = sorted(history, key=lambda x: x['date'])[-1] if history else {}
    consecutive = (last.get('連續賣超', 0) + 1) if foreign_bn < 0 else 0
    hedge = round(it_bn / abs(foreign_bn) * 100, 1) if (foreign_bn < 0 and it_bn > 0) else 0

    tsmc  = next((s for s in stocks if s['code'] == '2330'), {'f': 0, 'i': 0})
    e0050 = next((s for s in stocks if s['code'] == '0050'), {'f': 0, 'i': 0})

    fb  = top5(stocks, 'f', ascending=False)
    fs  = top5(stocks, 'f', ascending=True)
    ib  = top5(stocks, 'i', ascending=False)
    is_ = top5(stocks, 'i', ascending=True)

    def fmt(items, key):
        return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]

    new_entry = {
        'date':        target,
        'dateLabel':   f'{target[4:6]}/{target[6:8]}',
        '外資億元':     foreign_bn,
        '投信億元':     it_bn,
        '收盤':         close,
        '漲跌':         change,
        '連續賣超':     consecutive,
        '警示':         market_alert(foreign_bn, consecutive),
        'tsmc外資':     tsmc['f'],
        'tsmc投信':     tsmc['i'],
        'tsmc警示':     tsmc_alert(tsmc['f']),
        'etf0050外資':  e0050['f'],
        'etf0050投信':  e0050['i'],
        'etf0050警示':  etf0050_alert(e0050['f']),
        '護盤比':        hedge,
        '成交金額億':    vol_bn,
        '外資買超':      fmt(fb, 'f'),
        '外資賣超':      fmt(fs, 'f'),
        '投信買超':      fmt(ib, 'i'),
        '投信賣超':      fmt(is_, 'i'),
    }
    if global_data:
        new_entry['global'] = global_data

    # ── QA 驗證 ──────────────────────────────────────────
    warnings = []
    if not (-2000 <= foreign_bn <= 2000):
        warnings.append(f'外資億元異常：{foreign_bn}（預期 -2000~+2000）')
    if not (15000 <= close <= 65000):
        warnings.append(f'收盤點位異常：{close}（預期 15000~65000）')
    if not (500 <= vol_bn <= 15000):
        warnings.append(f'成交金額異常：{vol_bn}億（預期 500~15000）')
    if len(fb) < 3:
        warnings.append(f'外資買超個股不足：僅 {len(fb)} 筆（預期 ≥3）')
    if warnings:
        print('[QA 警告]')
        for w in warnings:
            print(f'  ⚠️  {w}')
        print('  → 資料仍寫入，請人工確認')
    else:
        print('[QA] ✅ 資料驗證通過')
    # ─────────────────────────────────────────────────────

    history.append(new_entry)
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    latest = sorted(history, key=lambda x: x['date'])[-10:]
    with open(LATEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f'[完成] {target}｜外資{foreign_bn:+.1f}億｜投信{it_bn:+.1f}億｜收盤{close:,.0f}｜成交{vol_bn:.0f}億｜{new_entry["警示"]}')


if __name__ == '__main__':
    main()
