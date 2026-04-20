"""
台股外資追蹤 - 歷史資料補填腳本
補填 data.json 中指定日期範圍的缺漏交易日

用法：
  python scripts/backfill_history.py                            # 預設補填 20251001 ~ 20260228
  python scripts/backfill_history.py --start 20251001 --end 20251031
  python scripts/backfill_history.py --test                     # 只測第一筆，不寫入
"""

import json, time, sys, os, requests, urllib3
from datetime import datetime, date, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_data import (
    fetch_bfi82u, fetch_bfi82u_finmind,
    fetch_t86, fetch_t86_finmind,
    fetch_fmtqik, fetch_futures,
    market_alert, entry_signal, divergence_signal,
    tsmc_alert, etf0050_alert, delta_alert,
    top5, YF_HEADERS, YF_SYMBOLS,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPO      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO, 'data.json')

# ── Yahoo Finance 歷史特定日期 ─────────────────────────────

def fetch_yf_historical(symbol, date_str):
    """抓取指定日期（或最近前一交易日）的收盤價與漲跌幅"""
    dt      = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
    period1 = int((dt - timedelta(days=7)).timestamp())
    period2 = int((dt + timedelta(days=2)).timestamp())
    url = (f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
           f'?interval=1d&period1={period1}&period2={period2}')
    try:
        d      = requests.get(url, headers=YF_HEADERS, timeout=15).json()
        result = d['chart']['result'][0]
        tss    = result.get('timestamp', [])
        closes = result['indicators']['quote'][0].get('close', [])

        # 找 <= date_str 的最近有效收盤
        best_idx = None
        for i, ts in enumerate(tss):
            ts_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y%m%d')
            if ts_date <= date_str and closes[i] is not None:
                best_idx = i

        if best_idx is None:
            return None, None
        close      = closes[best_idx]
        prev_close = closes[best_idx - 1] if best_idx > 0 and closes[best_idx - 1] else close
        chg_pct    = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
        return round(close, 2), chg_pct
    except Exception:
        return None, None


def fetch_global_historical(date_str):
    """並行抓取所有指標的歷史收盤"""
    result = {}
    with ThreadPoolExecutor(max_workers=len(YF_SYMBOLS)) as ex:
        futs = {ex.submit(fetch_yf_historical, sym, date_str): key
                for key, sym in YF_SYMBOLS.items()}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                val, chg = fut.result()
            except Exception:
                val, chg = None, None
            if val is not None:
                result[key]            = val
                result[f'{key}_chg']   = chg
    return result if result else None


# ── 工具函式 ──────────────────────────────────────────────

def get_weekdays(start_str, end_str):
    start = datetime.strptime(start_str, '%Y%m%d').date()
    end   = datetime.strptime(end_str,   '%Y%m%d').date()
    cur   = start
    days  = []
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur.strftime('%Y%m%d'))
        cur += timedelta(days=1)
    return days


def fmt(items, key):
    return [{'code': s['code'], 'name': s['name'], '張數': s[key]} for s in items]


def prev_entry(sorted_hist, ds):
    """回傳 sorted_hist 中日期最近且 < ds 的那筆，找不到回傳 {}"""
    result = {}
    for h in sorted_hist:
        if h['date'] < ds:
            result = h
        else:
            break
    return result


# ── 主補填流程 ─────────────────────────────────────────────

def backfill_range(start_str, end_str, test_mode=False):
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    existing  = {d['date'] for d in history}
    weekdays  = get_weekdays(start_str, end_str)
    missing   = [d for d in weekdays if d not in existing]

    if not missing:
        print(f'[完成] {start_str}~{end_str} 無缺漏資料')
        return

    if test_mode:
        print(f'[TEST] 只測試第一筆：{missing[0]}（不寫入）')
        missing = [missing[0]]

    est_min = len(missing) * 6 // 60
    print(f'[開始] 補填 {len(missing)} 個交易日：{missing[0]} ~ {missing[-1]}')
    print(f'       預估時間：約 {est_min} 分鐘')

    # 保持排序以便 prev_entry 使用
    sorted_hist = sorted(history, key=lambda x: x['date'])
    changed = 0

    for idx, ds in enumerate(missing, 1):
        print(f'\n[{idx}/{len(missing)}] {ds} ...', flush=True)

        # ① 三大法人整體
        fn, it = fetch_bfi82u(ds)
        if fn is None:
            fn, it = fetch_bfi82u_finmind(ds)
        if fn is None:
            print('  → 非交易日，跳過')
            time.sleep(1)
            continue

        # ② 大盤收盤
        cl, ch, vol = fetch_fmtqik(ds)
        if cl is None:
            print('  → 無大盤資料，跳過')
            time.sleep(1)
            continue

        # ③ 個股三大法人
        stocks = fetch_t86(ds)
        if stocks is None:
            stocks = fetch_t86_finmind(ds)
        if stocks is None:
            print('  → 無個股資料，跳過')
            time.sleep(1)
            continue

        # ④ 全球市場（歷史）
        global_data = fetch_global_historical(ds)
        if global_data:
            print(f'  S&P={global_data.get("sp500")}  '
                  f'VIX={global_data.get("vix")}  '
                  f'Gold={global_data.get("gold")}')

        # ⑤ 期貨（失敗不中止）
        futures_data = fetch_futures(ds)

        # 衍生欄位：以正確的前一筆為基準計算 streak
        prev = prev_entry(sorted_hist, ds)
        consecutive_sell = (prev.get('連續賣超', 0) + 1) if fn < 0 else 0
        consecutive_buy  = (prev.get('連續買超', 0) + 1) if fn > 0 else 0
        hedge = round(it / abs(fn) * 100, 1) if (fn < 0 and it > 0) else 0

        tsmc  = next((s for s in stocks if s['code'] == '2330'), {'f': 0, 'i': 0})
        e0050 = next((s for s in stocks if s['code'] == '0050'), {'f': 0, 'i': 0})
        delta = next((s for s in stocks if s['code'] == '2308'), {'f': 0, 'i': 0})

        fb  = top5(stocks, 'f', ascending=False)
        fs  = top5(stocks, 'f', ascending=True)
        ib  = top5(stocks, 'i', ascending=False)
        is_ = top5(stocks, 'i', ascending=True)

        sig_data = entry_signal(fn, consecutive_buy, tsmc['f'], global_data, futures_data)
        div_data = divergence_signal(fn, futures_data)

        last_sig_lv = prev.get('進場訊號', {}).get('訊號', '')
        sig_streak  = (prev.get('訊號連續天數', 1) + 1) if last_sig_lv == sig_data['訊號'] else 1

        entry = {
            'date':         ds,
            'dateLabel':    f'{ds[4:6]}/{ds[6:8]}',
            '外資億元':      fn,
            '投信億元':      it,
            '收盤':          cl,
            '漲跌':          ch,
            '連續賣超':      consecutive_sell,
            '連續買超':      consecutive_buy,
            '警示':          market_alert(fn, consecutive_sell, e0050['f']),
            '進場訊號':      sig_data,
            '訊號連續天數':  sig_streak,
            'tsmc外資':      tsmc['f'],
            'tsmc投信':      tsmc['i'],
            'tsmc警示':      tsmc_alert(tsmc['f']),
            'etf0050外資':   e0050['f'],
            'etf0050投信':   e0050['i'],
            'etf0050警示':   etf0050_alert(e0050['f']),
            'delta外資':     delta['f'],
            'delta投信':     delta['i'],
            'delta警示':     delta_alert(delta['f']),
            '護盤比':         hedge,
            '成交金額億':     vol,
            '外資買超':       fmt(fb, 'f'),
            '外資賣超':       fmt(fs, 'f'),
            '投信買超':       fmt(ib, 'i'),
            '投信賣超':       fmt(is_, 'i'),
        }
        if global_data:
            entry['global']   = global_data
        if futures_data:
            entry['futures']  = futures_data
        if div_data:
            entry['分歧信號'] = div_data

        # QA
        qa_warn = []
        if not (-2000 <= fn <= 2000):         qa_warn.append(f'外資億元異常：{fn}')
        if cl and not (15000 <= cl <= 65000): qa_warn.append(f'收盤點位異常：{cl}')
        if vol and not (500 <= vol <= 15000): qa_warn.append(f'成交金額異常：{vol}億')
        if qa_warn:
            for w in qa_warn:
                print(f'  [WARN] {w}')
        else:
            print(f'  [OK] {fn:+.1f}ok {cl:.0f}pt {vol:.0f}ok '
                  f'| {entry["警示"]} | {sig_data["訊號"]}({sig_data["分數"]}/10)')

        if not test_mode:
            sorted_hist.append(entry)
            changed += 1

            # 每 10 筆中途儲存（防意外中斷）
            if changed % 10 == 0:
                sorted_hist.sort(key=lambda x: x['date'])
                with open(DATA_PATH, 'w', encoding='utf-8') as f:
                    json.dump(sorted_hist, f, ensure_ascii=False, indent=2)
                print(f'  [中途儲存] 已寫入 {changed} 筆')

        time.sleep(4)   # 避免 TWSE 速率限制

    # 最終儲存
    if not test_mode and changed > 0:
        sorted_hist.sort(key=lambda x: x['date'])
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(sorted_hist, f, ensure_ascii=False, indent=2)
        print(f'\n[完成] 共補填 {changed} 筆，data.json 共 {len(sorted_hist)} 筆')
        print('執行 deploy.bat 推送到 GitHub')
    elif test_mode:
        print('\n[TEST] 測試完成，data.json 未修改')
    else:
        print('\n[完成] 無新增資料')


# ── 入口 ──────────────────────────────────────────────────

if __name__ == '__main__':
    args      = sys.argv[1:]
    start     = '20251001'
    end       = '20260228'
    test_mode = '--test' in args

    if '--start' in args:
        start = args[args.index('--start') + 1]
    if '--end' in args:
        end = args[args.index('--end') + 1]

    print(f'補填範圍：{start} ~ {end}{"  [TEST 模式，不寫入]" if test_mode else ""}')
    backfill_range(start, end, test_mode=test_mode)
