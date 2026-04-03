"""
台股外資追蹤 - 綜合維護工具
用法：
  python scripts/smart_pull.py              # 智能同步（merge local + GitHub）
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

# ── git 工具 ─────────────────────────────────────────

def run(cmd, cwd=REPO, check=True):
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if check and result.returncode != 0:
        print(f"[ERROR] {cmd}")
        sys.exit(1)
    return result

def clean_locks():
    for lock in [r".git\HEAD.lock", r".git\index.lock"]:
        p = os.path.join(REPO, lock)
        if os.path.exists(p):
            os.remove(p)
            print(f"[清除] {lock}")

# ── TWSE API ─────────────────────────────────────────

def fetch_bfi82u(date_str):
    url = f'https://www.twse.com.tw/rwd/zh/fund/bfi82u?date={date_str}&response=json'
    try:
        d = requests.get(url, headers=HEADERS, timeout=30, verify=False).json()
    except Exception:
        return None, None
    if d.get('stat') != 'OK' or not d.get('data'):
        return None, None
    fb = fs = ib = is_ = 0
    for row in d['data']:
        name = row[0].strip()
        try:
            buy, sell = float(row[1].replace(',','')), float(row[2].replace(',',''))
        except Exception:
            continue
        if '外資及陸資(不含' in name:
            fb, fs = buy, sell
        elif name == '投信':
            ib, is_ = buy, sell
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

# ── 警示邏輯 ──────────────────────────────────────────

def market_alert(f, c):
    if f >= -50 and c < 3:   return '正常'
    elif f >= -100 or c < 5: return '注意'
    elif f >= -200 or c < 8: return '高度警戒'
    else:                     return '極度警戒'

def tsmc_alert(n):
    return '正常' if n>=-15000 else '注意' if n>=-25000 else '高度警戒' if n>=-40000 else '極度警戒'

def etf_alert(n):
    return '正常' if n>=-5000 else '注意' if n>=-10000 else '高度警戒' if n>=-25000 else '極度警戒'

def top5(stocks, key, asc=False):
    return sorted([s for s in stocks if s[key]!=0], key=lambda x: x[key], reverse=not asc)[:5]

def fmt(items, key):
    return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]

# ── 模式 1：智能 pull ─────────────────────────────────

def smart_pull():
    print("[1] 讀取本機 data.json...")
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        local_data = json.load(f)
    local_map = {d['date']: d for d in local_data}

    print("[2] git fetch origin...")
    run("git fetch origin")

    print("[3] 讀取 GitHub data.json...")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='wb')
    tmp.close()
    subprocess.run(f'git show origin/main:data.json > "{tmp.name}"', shell=True, cwd=REPO)
    try:
        with open(tmp.name, 'r', encoding='utf-8') as f:
            remote_map = {d['date']: d for d in json.load(f)}
    except Exception as e:
        print(f"[WARN] 無法讀取 GitHub data.json ({e})")
        remote_map = {}
    finally:
        os.unlink(tmp.name)

    print("[4] 合併...")
    merged = []
    for d in sorted(set(local_map)|set(remote_map)):
        lo, re = local_map.get(d), remote_map.get(d)
        if lo is None:   merged.append(re); continue
        if re is None:   merged.append(lo); continue
        entry = dict(re)
        for k in ['外資買超','外資賣超','投信買超','投信賣超']:
            if len(lo.get(k,[]))>len(re.get(k,[])): entry[k]=lo[k]
        for k in ['global','成交金額億']:
            if lo.get(k) and not re.get(k): entry[k]=lo[k]
        merged.append(entry)
    print(f"    合併結果：{len(merged)} 筆")

    print("[5] git reset --hard origin/main...")
    run("git reset --hard origin/main")

    print("[6] 寫回合併後的 data.json...")
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("[完成] pull 成功")

# ── 模式 2：修補個股排行 ──────────────────────────────

def fix_stocks(target_dates=None):
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    dates = target_dates or [d['date'] for d in history if len(d.get('外資買超',[]))==0]
    if not dates:
        print('所有日期個股排行均已有資料'); return

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
        print(f'OK - 外資買超Top1: {fb[0]["name"] if fb else "-"}')
        changed = True

    if changed:
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print('[儲存完成] 請執行 deploy.bat')

# ── 模式 3：補齊缺漏交易日 ───────────────────────────

def backfill():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    existing = {d['date'] for d in history}
    start = min(datetime.strptime(d['date'],'%Y%m%d').date() for d in history)
    end   = date.today()
    missing = [d.strftime('%Y%m%d') for d in
               (start+timedelta(i) for i in range((end-start).days+1))
               if d.weekday()<5 and d.strftime('%Y%m%d') not in existing]

    if not missing:
        print('沒有缺漏的交易日'); return
    print(f'找到 {len(missing)} 個缺漏：{missing}')

    changed = False
    for ds in missing:
        print(f'\n[抓取] {ds}')
        fn, it = fetch_bfi82u(ds)
        if fn is None: print('非交易日，跳過'); continue
        cl, ch, vol = fetch_fmtqik(ds)
        if cl is None: print('無大盤資料，跳過'); continue
        stocks = fetch_t86(ds)
        if stocks is None: print('無個股資料，跳過'); continue

        prev = sorted(history, key=lambda x:x['date'])[-1] if history else {}
        consec = (prev.get('連續賣超',0)+1) if fn<0 else 0
        hedge  = round(it/abs(fn)*100,1) if fn<0 and it>0 else 0
        tsmc   = next((s for s in stocks if s['code']=='2330'),{'f':0,'i':0})
        e0050  = next((s for s in stocks if s['code']=='0050'),{'f':0,'i':0})
        fb=top5(stocks,'f'); fs=top5(stocks,'f',asc=True)
        ib=top5(stocks,'i'); is_=top5(stocks,'i',asc=True)

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
        history.append(entry)
        history.sort(key=lambda x:x['date'])
        print(f'  外資 {fn:+.2f}億 | 收盤 {cl:,.2f} | 成交 {vol:.0f}億 ✓')
        changed = True
        time.sleep(1)

    if changed:
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print('\n[儲存完成] 請執行 deploy.bat')

# ── 模式 4：建立 bat 檔 ───────────────────────────────

FIX_BAT = r"""@echo off
setlocal enabledelayedexpansion
for /f %%a in ('echo prompt $E ^| cmd') do set "E=%%a"
set "GREEN=%E%[92m"
set "RED=%E%[91m"
set "CYAN=%E%[96m"
set "RESET=%E%[0m"
echo %CYAN%=============================%RESET%
echo %CYAN%  Fix Empty Stock Rankings%RESET%
echo %CYAN%=============================%RESET%
echo.
cd /d "C:\Users\lifongye\Documents\taiwan-market"
if exist .git\HEAD.lock  del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock
echo %CYAN%[1/2]%RESET% Smart pull...
python scripts\smart_pull.py
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %CYAN%[2/2]%RESET% Fix stock rankings...
python scripts\smart_pull.py --fix
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %GREEN%Done! Run deploy.bat to push.%RESET%
:END
echo.
pause
"""

BACKFILL_BAT = r"""@echo off
setlocal enabledelayedexpansion
for /f %%a in ('echo prompt $E ^| cmd') do set "E=%%a"
set "GREEN=%E%[92m"
set "RED=%E%[91m"
set "CYAN=%E%[96m"
set "RESET=%E%[0m"
echo %CYAN%=============================%RESET%
echo %CYAN%   Backfill Missing Data%RESET%
echo %CYAN%=============================%RESET%
echo.
cd /d "C:\Users\lifongye\Documents\taiwan-market"
if exist .git\HEAD.lock  del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock
echo %CYAN%[1/3]%RESET% Smart pull...
python scripts\smart_pull.py
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %CYAN%[2/3]%RESET% Fix empty rankings...
python scripts\smart_pull.py --fix
echo.
echo %CYAN%[3/3]%RESET% Backfill missing days...
python scripts\smart_pull.py --backfill
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %GREEN%Done! Run deploy.bat to push.%RESET%
:END
echo.
pause
"""

def setup():
    for fname, content in [('fix_stocks.bat', FIX_BAT), ('backfill.bat', BACKFILL_BAT)]:
        path = os.path.join(REPO, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content.lstrip('\n'))
        print(f'[建立] {fname}')
    print('[完成] bat 檔已建立')

# ── 入口 ──────────────────────────────────────────────

if __name__ == '__main__':
    args = sys.argv[1:]
    if '--fix' in args:
        fix_stocks()
    elif '--backfill' in args:
        backfill()
    elif '--setup' in args:
        setup()
    else:
        clean_locks()
        smart_pull()
