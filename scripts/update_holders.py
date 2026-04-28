"""
每週從 TDCC 下載個股持股人數（股權分散表）
執行時機：每週一 UTC 2:00（台灣時間 10:00）
資料來源：https://opendata.tdcc.com.tw/getOD.ashx?id=1-5
"""
import json, requests, urllib3, os, sys
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOLDER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'holder-weekly.json')
TDCC_URL    = 'https://opendata.tdcc.com.tw/getOD.ashx?id=1-5'
TARGETS     = {'2330': 'tsmc', '0050': 'etf0050', '2308': 'delta'}

def fetch_holder_count():
    try:
        resp = requests.get(TDCC_URL, timeout=30, verify=False)
        resp.encoding = 'utf-8'
        lines = resp.text.strip().split('\n')
    except Exception as e:
        print(f'[ERROR] 下載 TDCC 資料失敗: {e}')
        return None

    header = [h.strip().strip('"') for h in lines[0].split(',')]
    try:
        date_idx  = header.index('資料日期')
        code_idx  = header.index('證券代號')
        level_idx = header.index('持股分級')
        count_idx = header.index('人數')
    except ValueError as e:
        print(f'[ERROR] CSV 欄位解析失敗: {e}，header={header}')
        return None

    result = {}
    data_date = None

    for line in lines[1:]:
        cols = [c.strip().strip('"') for c in line.split(',')]
        if len(cols) <= max(date_idx, code_idx, level_idx, count_idx):
            continue
        code  = cols[code_idx]
        level = cols[level_idx]
        if code not in TARGETS:
            continue
        if data_date is None:
            data_date = cols[date_idx]
        if level == '16':  # 級距16 = 合計
            try:
                result[TARGETS[code]] = int(cols[count_idx].replace(',', ''))
            except (ValueError, IndexError):
                pass

    if not result:
        print('[警告] 未找到目標股票資料，可能 CSV 格式有變')
        return None

    return {'date': data_date, **result}


def main():
    holder_data = fetch_holder_count()
    if not holder_data:
        print('[跳過] 無法取得持股人數資料')
        sys.exit(0)

    print(f'[持股人數] 資料日期: {holder_data["date"]}')
    for key, name in [('tsmc','2330'), ('etf0050','0050'), ('delta','2308')]:
        if key in holder_data:
            print(f'  {name}: {holder_data[key]:,} 人')

    with open(HOLDER_PATH, 'w', encoding='utf-8') as f:
        json.dump(holder_data, f, ensure_ascii=False, indent=2)
    print('[完成] 已更新 holder-weekly.json')


if __name__ == '__main__':
    main()
