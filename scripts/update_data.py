"""
台股外資動向追蹤 - 自動資料更新腳本
每個交易日收盤後由 GitHub Actions 執行

資料來源優先順序：
  台股資料：TWSE（主）→ FinMind（備）
  全球市場：Yahoo Finance（自動）
"""

import json, requests, sys, os, urllib3, smtplib, ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

_LVLS = ['正常', '注意', '高度警戒', '極度警戒']

def market_alert(f, c, etf0050_f=0):
    """主警示：外資整體 + 連續賣超天數 + 0050 大量賣超聯動升級"""
    if f >= -50 and c < 3:   base = '正常'
    elif f >= -100 or c < 5: base = '注意'
    elif f >= -200 or c < 8: base = '高度警戒'
    else:                     base = '極度警戒'
    # 0050 大量賣超：直接升級主警示（≥2萬張高度、≥3萬張極度）
    if etf0050_f <= -30000:
        base = _LVLS[max(_LVLS.index(base), 3)]
    elif etf0050_f <= -20000:
        base = _LVLS[max(_LVLS.index(base), 2)]
    return base

def send_alert_email(entry, gmail_user, gmail_pwd):
    """發送警示或進場訊號 email"""
    alert  = entry.get('警示', '')
    sig    = entry.get('進場訊號', {})
    sig_lv = sig.get('訊號', '')
    score  = sig.get('分數', 0)
    date_l = entry.get('dateLabel', entry.get('date', ''))

    is_danger  = alert in ('高度警戒', '極度警戒')
    is_entry   = score >= 7
    if not is_danger and not is_entry:
        return  # 不需要通知

    subj_tag = f'[{"危險" if is_danger else "機會"}]'
    subject  = f'{subj_tag} 台股外資警示 {date_l} ｜ {alert} / 進場訊號:{sig_lv}({score}/10)'

    reasons_html = ''.join(f'<li>{r}</li>' for r in sig.get('依據', []))
    fb_top = entry.get('外資買超', [{}])
    fs_top = entry.get('外資賣超', [{}])
    top_buy  = fb_top[0].get('name', '--') + f' {fb_top[0].get("張數", 0):+,}張' if fb_top else '--'
    top_sell = fs_top[0].get('name', '--') + f' {fs_top[0].get("張數", 0):+,}張' if fs_top else '--'

    body = f"""
<html><body style="font-family:sans-serif;background:#0f1117;color:#e2e8f0;padding:20px">
<h2 style="color:{'#ef4444' if is_danger else '#34d399'}">
  {'⚠️' if is_danger else '🟢'} 台股外資追蹤｜{date_l}
</h2>
<table style="border-collapse:collapse;margin:12px 0;font-size:14px">
  <tr><td style="padding:4px 12px 4px 0;color:#718096">警示等級</td>
      <td style="font-weight:700;color:{'#ef4444' if is_danger else '#34d399'}">{alert}</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">進場訊號</td>
      <td style="font-weight:700">{sig_lv}（{score}/10）</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">外資整體</td>
      <td>{entry.get('外資億元', 0):+.1f} 億</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">台積電外資</td>
      <td>{entry.get('tsmc外資', 0):+,} 張</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">台股收盤</td>
      <td>{entry.get('收盤', 0):,.0f} 點（{entry.get('漲跌', 0):+.2f}）</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">外資最大買超</td>
      <td>{top_buy}</td></tr>
  <tr><td style="padding:4px 12px 4px 0;color:#718096">外資最大賣超</td>
      <td>{top_sell}</td></tr>
</table>
<h4 style="margin-top:14px;color:#a0aec0">訊號依據</h4>
<ul style="color:#e2e8f0;font-size:13px;line-height:1.9">{reasons_html}</ul>
<p style="margin-top:18px">
  <a href="https://airinno.github.io/taiwan-market/" style="color:#60a5fa">→ 開啟完整儀表板</a>
</p>
<p style="font-size:11px;color:#4a5568;margin-top:20px">此為自動通知，不構成投資建議。</p>
</body></html>"""

    to_email = gmail_user  # 寄給自己
    msg = MIMEMultipart('alternative')
    msg['From']    = gmail_user
    msg['To']      = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ctx) as s:
            s.login(gmail_user, gmail_pwd)
            s.send_message(msg)
        print(f'[EMAIL] 通知已寄出 → {to_email}')
    except Exception as e:
        print(f'[EMAIL] 寄送失敗: {e}')


def entry_signal(foreign_bn, consecutive_buy, tsmc_f, global_data, futures_data=None):
    """計算進場訊號強度（0-10分，外資期貨空倉可扣1分）"""
    score   = 0
    reasons = []
    vix     = (global_data or {}).get('vix')
    sox_chg = (global_data or {}).get('sox_chg')
    fut_net = (futures_data or {}).get('外資')  # 外資期貨淨部位（口）

    # 外資買超金額 (0-3)
    if   foreign_bn >= 300: score += 3; reasons.append(f'外資大買 +{foreign_bn:.0f}億')
    elif foreign_bn >= 100: score += 2; reasons.append(f'外資買超 +{foreign_bn:.0f}億')
    elif foreign_bn >    0: score += 1; reasons.append(f'外資小買 +{foreign_bn:.0f}億')
    else:                                reasons.append(f'外資賣超 {foreign_bn:.0f}億')

    # 連續買超天數 (0-2)
    if   consecutive_buy >= 3: score += 2; reasons.append(f'連續買超 {consecutive_buy} 天')
    elif consecutive_buy >= 1: score += 1; reasons.append(f'買超第 {consecutive_buy} 天')

    # 台積電外資 (0-2)
    if   tsmc_f >= 10000: score += 2; reasons.append(f'台積電大買 +{tsmc_f:,} 張')
    elif tsmc_f >      0: score += 1; reasons.append(f'台積電買超 +{tsmc_f:,} 張')
    elif tsmc_f < -10000:              reasons.append(f'台積電大賣 {tsmc_f:,} 張')
    elif tsmc_f <      0:              reasons.append(f'台積電賣超 {tsmc_f:,} 張')

    # VIX (0-2)
    if vix is not None:
        if   vix < 15: score += 2; reasons.append(f'VIX {vix:.1f} 極低')
        elif vix < 20: score += 1; reasons.append(f'VIX {vix:.1f} 偏低')
        else:                       reasons.append(f'VIX {vix:.1f} 偏高')

    # SOX 漲幅 (0-1)
    if sox_chg is not None and sox_chg >= 2:
        score += 1; reasons.append(f'SOX +{sox_chg}%')

    # 外資期貨（加減分）
    if fut_net is not None:
        if   fut_net >= 10000:  score += 1; reasons.append(f'期貨多方 +{fut_net:,} 口')
        elif fut_net <= -20000: score -= 1; reasons.append(f'期貨空方 {fut_net:,} 口（警示）')
        elif fut_net < 0:                   reasons.append(f'期貨偏空 {fut_net:,} 口')
        else:                               reasons.append(f'期貨中立 +{fut_net:,} 口')

    score = max(0, score)  # 不低於 0
    label = '強' if score >= 7 else '中' if score >= 4 else '弱' if score >= 2 else '觀望'
    return {'訊號': label, '分數': score, '滿分': 10, '依據': reasons}

def tsmc_alert(n):
    return '正常' if n>=-15000 else '注意' if n>=-25000 else '高度警戒' if n>=-40000 else '極度警戒'

def etf0050_alert(n):
    return '正常' if n>=-5000 else '注意' if n>=-10000 else '高度警戒' if n>=-25000 else '極度警戒'

def delta_alert(n):
    return '正常' if n>=-3000 else '注意' if n>=-6000 else '高度警戒' if n>=-12000 else '極度警戒'

def divergence_signal(foreign_bn, futures_data):
    """現貨×期貨分歧信號：判斷外資現貨與期貨方向是否一致"""
    if futures_data is None or futures_data.get('外資') is None:
        return None
    fut_net  = futures_data['外資']
    spot_buy = foreign_bn > 0
    fut_long = fut_net > 0
    if   spot_buy and fut_long:      status = '多方一致'   # 現貨買 + 期貨多（強力看多）
    elif spot_buy and not fut_long:  status = '分歧警戒'   # 現貨買 + 期貨空（表多實空）
    elif not spot_buy and not fut_long: status = '空方一致' # 現貨賣 + 期貨空（全面撤退）
    else:                            status = '分歧觀望'   # 現貨賣 + 期貨多（矛盾）
    return {'狀態': status, '現貨': '買超' if spot_buy else '賣超', '期貨淨口': fut_net}

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

# ── FinMind：外資期貨未平倉 ──────────────────────────

def fetch_futures(date_str):
    """抓取台指期（TX）三大法人未平倉淨部位（口）；不需要 token"""
    iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {'dataset': 'TaiwanFuturesInstitutionalInvestors',
              'data_id': 'TX', 'start_date': iso, 'end_date': iso}
    if FINMIND_TOKEN:
        params['token'] = FINMIND_TOKEN
    try:
        rows = requests.get(url, params=params, timeout=15).json().get('data', [])
    except Exception as e:
        print(f'  [WARNING] 期貨資料抓取失敗: {e}')
        return None
    if not rows:
        return None
    result = {}
    for r in rows:
        name = r.get('institutional_investors', '')
        net  = r.get('long_open_interest_balance_volume', 0) - r.get('short_open_interest_balance_volume', 0)
        if '外資' in name:  result['外資'] = net
        elif '投信' in name: result['投信'] = net
        elif '自營' in name: result['自營'] = net
    return result if result else None


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
    """抓取全球市場指標（並行請求），失敗欄位留 None"""
    result = {}
    with ThreadPoolExecutor(max_workers=len(YF_SYMBOLS)) as ex:
        futures = {ex.submit(fetch_yf_quote, symbol): key for key, symbol in YF_SYMBOLS.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val, chg = fut.result()
            except Exception:
                val, chg = None, None
            if val is not None:
                result[key]          = val
                result[f'{key}_chg'] = chg
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

    # 5. 外資期貨淨部位（FinMind，失敗不中止）
    print('  抓取外資期貨...')
    futures_data = fetch_futures(target)
    if futures_data:
        f_net = futures_data.get('外資', 0)
        print(f'  外資期貨淨部位: {f_net:+,} 口（{"多方" if f_net >= 0 else "空方"}）')
    else:
        print('  外資期貨資料暫時無法取得，跳過')

    # 衍生欄位
    last = sorted(history, key=lambda x: x['date'])[-1] if history else {}
    consecutive_sell = (last.get('連續賣超', 0) + 1) if foreign_bn < 0 else 0
    consecutive_buy  = (last.get('連續買超', 0) + 1) if foreign_bn > 0 else 0
    hedge = round(it_bn / abs(foreign_bn) * 100, 1) if (foreign_bn < 0 and it_bn > 0) else 0

    tsmc  = next((s for s in stocks if s['code'] == '2330'), {'f': 0, 'i': 0})
    e0050 = next((s for s in stocks if s['code'] == '0050'), {'f': 0, 'i': 0})
    delta = next((s for s in stocks if s['code'] == '2308'), {'f': 0, 'i': 0})

    fb  = top5(stocks, 'f', ascending=False)
    fs  = top5(stocks, 'f', ascending=True)
    ib  = top5(stocks, 'i', ascending=False)
    is_ = top5(stocks, 'i', ascending=True)

    # 分析欄位（需先計算才能用於 new_entry）
    sig_data = entry_signal(foreign_bn, consecutive_buy, tsmc['f'], global_data, futures_data)
    div_data = divergence_signal(foreign_bn, futures_data)

    # 訊號連續天數：與前一日相同訊號等級則累加，否則重設為 1
    last_sig_lv  = last.get('進場訊號', {}).get('訊號', '')
    sig_streak   = (last.get('訊號連續天數', 1) + 1) if last_sig_lv == sig_data['訊號'] else 1

    def fmt(items, key):
        return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]

    new_entry = {
        'date':        target,
        'dateLabel':   f'{target[4:6]}/{target[6:8]}',
        '外資億元':     foreign_bn,
        '投信億元':     it_bn,
        '收盤':         close,
        '漲跌':         change,
        '連續賣超':     consecutive_sell,
        '連續買超':     consecutive_buy,
        '警示':         market_alert(foreign_bn, consecutive_sell, e0050['f']),
        '進場訊號':     sig_data,
        '訊號連續天數': sig_streak,
        'tsmc外資':     tsmc['f'],
        'tsmc投信':     tsmc['i'],
        'tsmc警示':     tsmc_alert(tsmc['f']),
        'etf0050外資':  e0050['f'],
        'etf0050投信':  e0050['i'],
        'etf0050警示':  etf0050_alert(e0050['f']),
        'delta外資':    delta['f'],
        'delta投信':    delta['i'],
        'delta警示':    delta_alert(delta['f']),
        '護盤比':        hedge,
        '成交金額億':    vol_bn,
        '外資買超':      fmt(fb, 'f'),
        '外資賣超':      fmt(fs, 'f'),
        '投信買超':      fmt(ib, 'i'),
        '投信賣超':      fmt(is_, 'i'),
    }
    if global_data:
        new_entry['global'] = global_data
    if futures_data:
        new_entry['futures'] = futures_data
    if div_data:
        new_entry['分歧信號'] = div_data

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

    div_str = new_entry.get('分歧信號', {}).get('狀態', 'N/A') if '分歧信號' in new_entry else '無期貨'
    print(f'[完成] {target}｜外資{foreign_bn:+.1f}億｜投信{it_bn:+.1f}億｜收盤{close:,.0f}｜成交{vol_bn:.0f}億｜{new_entry["警示"]}｜進場:{sig_data["訊號"]}({sig_data["分數"]}/10)x{sig_streak}天｜分歧:{div_str}')

    # ── Email 通知（警示升高或進場訊號強時觸發）──────────────
    gmail_user = os.environ.get('GMAIL_USER', '')
    gmail_pwd  = os.environ.get('GMAIL_APP_PASSWORD', '')
    if gmail_user and gmail_pwd:
        send_alert_email(new_entry, gmail_user, gmail_pwd)
    else:
        print('[EMAIL] 未設定 GMAIL_USER / GMAIL_APP_PASSWORD，跳過通知')


if __name__ == '__main__':
    main()
