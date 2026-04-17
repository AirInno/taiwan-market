"""
補填歷史外資持股比率（tsmc_hold / etf0050_hold / delta_hold）
一次性執行：python scripts/backfill_holdings.py
"""
import json, requests, sys, os, time, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_PATH   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')
LATEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data-latest.json')

TWSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.twse.com.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

def fetch_twt38u(date_str):
    url = f'https://www.twse.com.tw/fund/TWT38U?response=json&date={date_str}&selectType=ALL'
    try:
        d = requests.get(url, headers=TWSE_HEADERS, timeout=30, verify=False).json()
    except Exception as e:
        print(f'[錯誤] {e}')
        return None
    if d.get('stat') != 'OK' or not d.get('data'):
        return None
    result = {}
    targets = {'2330': 'tsmc', '0050': 'etf0050', '2308': 'delta'}
    for row in d['data']:
        code = row[0].strip()
        if code in targets:
            key = targets[code]
            try:
                shares = int(row[4].replace(',', '')) // 1000  # 股→張
                ratio  = float(row[5].replace(',', '').replace('%', ''))
                result[key] = {'張數': shares, '比率': ratio}
            except Exception:
                pass
    return result if result else None

def main():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    to_fill = [e for e in history if 'tsmc_hold' not in e]
    total   = len(to_fill)
    print(f'[開始] 需補填 {total} 筆（共 {len(history)} 筆）')
    if total == 0:
        print('[完成] 全部已補填，無需處理')
        return

    updated = failed = 0

    for i, entry in enumerate(to_fill):
        date_str = entry['date']
        sys.stdout.write(f'  [{i+1:3d}/{total}] {date_str} ... ')
        sys.stdout.flush()

        hold = fetch_twt38u(date_str)
        if hold:
            if 'tsmc'    in hold: entry['tsmc_hold']    = hold['tsmc']
            if 'etf0050' in hold: entry['etf0050_hold'] = hold['etf0050']
            if 'delta'   in hold: entry['delta_hold']   = hold['delta']
            r = hold.get('tsmc', {}).get('比率', '?')
            print(f'OK  2330持股 {r}%')
            updated += 1
        else:
            print('無資料（跳過）')
            failed += 1

        # 每10筆儲存一次，防止中途中斷遺失
        if (i + 1) % 10 == 0:
            with open(DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f'    → 進度已儲存（{i+1}/{total}）')

        time.sleep(0.8)

    # 最終儲存
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    latest = sorted(history, key=lambda x: x['date'])[-10:]
    with open(LATEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f'\n[完成] 補填 {updated} 筆，跳過 {failed} 筆（無資料）')
    print('請執行 deploy.bat 推送到 GitHub')

if __name__ == '__main__':
    main()
