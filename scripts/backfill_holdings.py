"""
補填歷史外資持股比率（tsmc_hold / etf0050_hold / delta_hold）
資料來源：FinMind TaiwanStockShareholding
一次性執行：python scripts/backfill_holdings.py
"""
import json, requests, os, sys

DATA_PATH   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.json')
LATEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data-latest.json')

def fetch_holdings_range(code, start_date, end_date):
    """一次抓取某檔股票指定日期範圍的外資持股資料"""
    url = 'https://api.finmindtrade.com/api/v4/data'
    params = {'dataset': 'TaiwanStockShareholding', 'data_id': code,
              'start_date': start_date, 'end_date': end_date}
    try:
        rows = requests.get(url, params=params, timeout=30).json().get('data', [])
        result = {}
        for r in rows:
            date_key = r['date'].replace('-', '')
            result[date_key] = {
                '張數': r['ForeignInvestmentShares'] // 1000,
                '比率': r['ForeignInvestmentSharesRatio']
            }
        return result
    except Exception as e:
        print(f'  [錯誤] {code}: {e}')
        return {}

def main():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        history = json.load(f)

    to_fill = [e for e in history if 'tsmc_hold' not in e]
    total = len(to_fill)
    print(f'[開始] 需補填 {total} 筆（共 {len(history)} 筆）')
    if total == 0:
        print('[完成] 全部已補填，無需處理')
        return

    dates = sorted(e['date'] for e in to_fill)
    start = f'{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:8]}'
    end   = f'{dates[-1][:4]}-{dates[-1][4:6]}-{dates[-1][6:8]}'
    print(f'  日期範圍：{start} ～ {end}')

    # 三檔股票各抓一次（共 3 次 API call）
    print('  抓取 2330 持股資料...')
    tsmc_map    = fetch_holdings_range('2330', start, end)
    print(f'  → {len(tsmc_map)} 筆')

    print('  抓取 0050 持股資料...')
    etf_map     = fetch_holdings_range('0050', start, end)
    print(f'  → {len(etf_map)} 筆')

    print('  抓取 2308 持股資料...')
    delta_map   = fetch_holdings_range('2308', start, end)
    print(f'  → {len(delta_map)} 筆')

    # 逐筆寫入
    updated = matched = 0
    for entry in history:
        if 'tsmc_hold' in entry:
            continue
        d = entry['date']
        if d in tsmc_map:
            entry['tsmc_hold']    = tsmc_map[d]
            entry['etf0050_hold'] = etf_map.get(d)
            entry['delta_hold']   = delta_map.get(d)
            matched += 1
        updated += 1

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    latest = sorted(history, key=lambda x: x['date'])[-10:]
    with open(LATEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f'\n[完成] 共 {total} 筆，成功補填 {matched} 筆，{total - matched} 筆無對應資料')
    print('請執行 deploy.bat 推送到 GitHub')

if __name__ == '__main__':
    main()
