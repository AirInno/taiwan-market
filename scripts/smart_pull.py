"""
台股外資追蹤 - 綜合維護工具
用法：
  python scripts/smart_pull.py              # 同步 GitHub（fetch+merge，不會有衝突）
  python scripts/smart_pull.py --fix        # 修補空的個股排行
  python scripts/smart_pull.py --backfill   # 補齊缺漏交易日
  python scripts/smart_pull.py --setup      # 建立 fix_stocks.bat / backfill.bat
"""
import json, subprocess, sys, os, tempfile, time, requests, urllib3
from datetime import date, datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPO      = r"C:\Users\lifongye\Documents\taiwan-market"
DATA_PATH = os.path.join(REPO, "data.json")
HEADERS   = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.twse.com.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}
YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}
YF_SYMBOLS = {
    'sp500':  '^GSPC',
    'nasdaq': '^IXIC',
    'vix':    '^VIX',
    'us10y':  '^TNX',
    'gold':   'GC=F',
    'sox':    '^SOX',
    'usdtwd': 'TWD=X',
}

# ── 工具函式 ──────────────────────────────────────────

def clean_locks():
    """清除 git 殘留鎖定檔"""
    for lock in [r".git\HEAD.lock", r".git\index.lock"]:
        p = os.path.join(REPO, lock)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, cwd=REPO)
    if check and r.returncode != 0:
        print(f"[ERROR] 指令失敗: {cmd}")
        sys.exit(1)
    return r

def fetch_remote_data():
    """從 GitHub 抓取最新 data.json，回傳 dict{date: entry}"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='wb')
    tmp.close()
    try:
        subprocess.run(f'git show origin/main:data.json > "{tmp.name}"',
                       shell=True, cwd=REPO, capture_output=True)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            return {d['date']: d for d in json.load(f)}
    except Exception:
        return {}
    finally:
        try: os.unlink(tmp.name)
        except: pass

def merge_data(local_map, remote_map):
    """合併本機與 GitHub 的資料，以兩者最完整的欄位為準"""
    merged = []
    for d in sorted(set(local_map) | set(remote_map)):
        lo, re = local_map.get(d), remote_map.get(d)
        if lo is None:  merged.append(re);  continue
        if re is None:  merged.append(lo);  continue
        entry = dict(re)
        for k in ['外資買超','外資賣超','投信買超','投信賣超']:
            if len(lo.get(k,[])) > len(re.get(k,[])): entry[k] = lo[k]
        for k in ['global','成交金額億']:
            if lo.get(k) and not re.get(k): entry[k] = lo[k]
        merged.append(entry)
    return merged

def save_data(history):
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_data():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

# ── TWSE API ──────────────────────────────────────────

def fetch_bfi82u(date_str):
    url = f'https://www.twse.com.tw/rwd/zh/fund/bfi82u?date={date_str}&response=json'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        print(f'  HTTP {resp.status_code}, len={len(resp.text)}', end='')
        if len(resp.text.strip()) == 0:
            print(' → 空回應（非交易日或速率限制）')
            return None, None     # 空 body = TWSE 無此日資料
        print(f', preview={resp.text[:80]!r}')
        d = resp.json()
    except Exception as e:
        print(f'\n  [連線失敗] {e}')
        return 'ERROR', 'ERROR'   # 區分「連線失敗」與「非交易日」
    if d.get('stat') != 'OK' or not d.get('data'):
        print(f'  stat={d.get("stat")!r} → 非交易日')
        return None, None         # 非交易日或無資料
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
    url = f'https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json'
    try:
        d = requests.get(url, headers=HEADERS, timeout=30, verify=False).json()
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
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={date_str}&response=json'
    try:
        d = requests.get(url, headers=HEADERS, timeout=30, verify=False).json()
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

# ── Yahoo Finance：全球市場 ───────────────────────────

def fetch_yf_quote(symbol):
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
    result = {}
    for key, symbol in YF_SYMBOLS.items():
        val, chg = fetch_yf_quote(symbol)
        if val is not None:
            result[key]          = val
            result[f'{key}_chg'] = chg
    return result if result else None

# ── 警示邏輯 ──────────────────────────────────────────

def market_alert(f, c):
    if f>=-50 and c<3:   return '正常'
    elif f>=-100 or c<5: return '注意'
    elif f>=-200 or c<8: return '高度警戒'
    else:                return '極度警戒'

def tsmc_alert(n):
    return '正常' if n>=-15000 else '注意' if n>=-25000 else '高度警戒' if n>=-40000 else '極度警戒'

def etf_alert(n):
    return '正常' if n>=-5000 else '注意' if n>=-10000 else '高度警戒' if n>=-25000 else '極度警戒'

def top5(stocks, key, asc=False):
    return sorted([s for s in stocks if s[key]!=0], key=lambda x:x[key], reverse=not asc)[:5]

def fmt(items, key):
    return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]

# ── 模式 1：同步（fetch + merge，不用 pull，永不衝突）────

def sync():
    """從 GitHub fetch 最新資料，與本機 merge，寫回 data.json"""
    clean_locks()
    print("同步 GitHub...", end=' ', flush=True)
    run("git fetch origin", check=False)  # fetch 失敗不中止（可能離線）

    local_map  = {d['date']: d for d in load_data()}
    remote_map = fetch_remote_data()

    if not remote_map:
        print("(無法取得 GitHub 資料，使用本機版本)")
        return

    merged = merge_data(local_map, remote_map)
    save_data(merged)
    print(f"完成（共 {len(merged)} 筆）")

# ── 模式 2：修補個股排行 ──────────────────────────────

def fix_stocks():
    history = load_data()
    dates = [d['date'] for d in history if len(d.get('外資買超',[])) == 0]
    if not dates:
        print('個股排行均已完整'); return

    print(f'待修補：{dates}')
    changed = False
    for ds in dates:
        entry = next((d for d in history if d['date']==ds), None)
        if not entry: continue
        print(f'[修復] {ds}...', end=' ', flush=True)
        stocks = fetch_t86(ds)
        if not stocks: print('無資料'); continue
        fb=top5(stocks,'f'); fs=top5(stocks,'f',asc=True)
        ib=top5(stocks,'i'); is_=top5(stocks,'i',asc=True)
        entry['外資買超']=fmt(fb,'f'); entry['外資賣超']=fmt(fs,'f')
        entry['投信買超']=fmt(ib,'i'); entry['投信賣超']=fmt(is_,'i')
        t=next((s for s in stocks if s['code']=='2330'),None)
        e=next((s for s in stocks if s['code']=='0050'),None)
        if t: entry['tsmc外資']=t['f']; entry['tsmc投信']=t['i']
        if e: entry['etf0050外資']=e['f']; entry['etf0050投信']=e['i']
        print(f'OK')
        changed = True

    if changed:
        save_data(history)
        print('修補完成')

# ── 模式 3：補齊缺漏交易日 ───────────────────────────

def backfill():
    history = load_data()
    existing = {d['date'] for d in history}
    start = min(datetime.strptime(d['date'],'%Y%m%d').date() for d in history)
    end   = date.today()
    missing = [d.strftime('%Y%m%d')
               for i in range((end-start).days+1)
               for d in [start+timedelta(i)]
               if d.weekday()<5 and d.strftime('%Y%m%d') not in existing]

    if not missing:
        print('沒有缺漏的交易日'); return
    print(f'找到 {len(missing)} 個缺漏：{missing}')

    changed = False
    for ds in missing:
        print(f'[抓取] {ds}...', flush=True)
        time.sleep(2)   # 先等一下，避免 TWSE 速率限制
        fn, it = fetch_bfi82u(ds)
        if fn == 'ERROR': print('API 連線失敗，跳過'); continue
        if fn is None: print('非交易日，跳過'); continue
        cl, ch, vol = fetch_fmtqik(ds)
        if cl is None: print('無大盤資料，跳過'); continue
        stocks = fetch_t86(ds)
        if not stocks: print('無個股資料，跳過'); continue

        sorted_hist = sorted(history, key=lambda x:x['date'])
        prev   = sorted_hist[-1] if sorted_hist else {}
        consec = (prev.get('連續賣超',0)+1) if fn<0 else 0
        hedge  = round(it/abs(fn)*100,1) if fn<0 and it>0 else 0
        tsmc   = next((s for s in stocks if s['code']=='2330'),{'f':0,'i':0})
        e0050  = next((s for s in stocks if s['code']=='0050'),{'f':0,'i':0})
        fb=top5(stocks,'f'); fs=top5(stocks,'f',asc=True)
        ib=top5(stocks,'i'); is_=top5(stocks,'i',asc=True)

        global_data = fetch_global()
        if global_data:
            print(f'  S&P500={global_data.get("sp500")}  VIX={global_data.get("vix")}  黃金={global_data.get("gold")}')

        entry = {
            'date': ds, 'dateLabel': f'{ds[4:6]}/{ds[6:8]}',
            '外資億元': fn, '投信億元': it,
            '收盤': cl, '漲跌': ch, '連續賣超': consec,
            '警示': market_alert(fn,consec),
            'tsmc外資': tsmc['f'], 'tsmc投信': tsmc['i'],
            'tsmc警示': tsmc_alert(tsmc['f']),
            'etf0050外資': e0050['f'], 'etf0050投信': e0050['i'],
            'etf0050警示': etf_alert(e0050['f']),
            '護盤比': hedge, '成交金額億': vol,
            '外資買超': fmt(fb,'f'), '外資賣超': fmt(fs,'f'),
            '投信買超': fmt(ib,'i'), '投信賣超': fmt(is_,'i'),
        }
        if global_data:
            entry['global'] = global_data
        history.append(entry)
        history.sort(key=lambda x:x['date'])
        print(f'外資{fn:+.1f}億 收盤{cl:,.0f} 成交{vol:.0f}億 ✓')
        changed = True
        time.sleep(3)   # 避免 TWSE 速率限制

    if changed:
        save_data(history)
        print('補齊完成')

# ── 模式 4：建立輔助 bat 檔 ──────────────────────────

FIX_BAT = (
    '@echo off\r\n'
    'cd /d "C:\\Users\\lifongye\\Documents\\taiwan-market"\r\n'
    'echo [Fix Stock Rankings]\r\n'
    'python scripts\\smart_pull.py --fix\r\n'
    'if errorlevel 1 ( echo [ERROR] & pause & exit /b 1 )\r\n'
    'echo.\r\n'
    'echo Done! Run deploy.bat to push.\r\n'
    'pause\r\n'
)

BACKFILL_BAT = (
    '@echo off\r\n'
    'cd /d "C:\\Users\\lifongye\\Documents\\taiwan-market"\r\n'
    'echo [Sync + Fix + Backfill]\r\n'
    'python scripts\\smart_pull.py\r\n'
    'if errorlevel 1 ( echo [ERROR] sync & pause & exit /b 1 )\r\n'
    'python scripts\\smart_pull.py --fix\r\n'
    'python scripts\\smart_pull.py --backfill\r\n'
    'if errorlevel 1 ( echo [ERROR] backfill & pause & exit /b 1 )\r\n'
    'echo.\r\n'
    'echo Done! Run deploy.bat to push.\r\n'
    'pause\r\n'
)

def setup():
    for fname, content in [('fix_stocks.bat', FIX_BAT), ('backfill.bat', BACKFILL_BAT)]:
        with open(os.path.join(REPO, fname), 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'[建立] {fname}')

# ── 入口 ──────────────────────────────────────────────

if __name__ == '__main__':
    args = sys.argv[1:]
    clean_locks()
    if   '--fix'      in args: fix_stocks()
    elif '--backfill' in args: backfill()
    elif '--setup'    in args: setup()
    else:                      sync()
