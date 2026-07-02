# -*- coding: utf-8 -*-
"""GitHub Traffic API 每週記錄腳本：GitHub 網頁只保留過去 14 天的流量資料，
這支腳本把每次執行當下拿到的資料累積寫進 traffic-history.json，藉此保留 14 天以上的歷史。
執行方式：python scripts/log_traffic.py（需要環境變數 GITHUB_TOKEN、GITHUB_REPOSITORY）"""
import json, os, sys, io, urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo 根目錄
HIST_FILE = os.path.join(HERE, 'traffic-history.json')

TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = os.environ.get('GITHUB_REPOSITORY', 'AirInno/taiwan-market')


def fetch(kind: str) -> dict:
    url = f'https://api.github.com/repos/{REPO}/traffic/{kind}?per=day'
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.exit(
                '403：目前這個 GITHUB_TOKEN 沒有讀取 Traffic API 的權限（需要對 repo 有 push 權限）。'
                '若這個預設 token 持續不夠，需要改用一組有 repo 權限的 Personal Access Token 存進 GitHub Secrets。'
            )
        raise


def main():
    if not TOKEN:
        sys.exit('缺少 GITHUB_TOKEN 環境變數')

    views = fetch('views')
    clones = fetch('clones')

    hist = {}
    if os.path.exists(HIST_FILE):
        hist = json.load(open(HIST_FILE, encoding='utf-8'))

    for v in views.get('views', []):
        day = v['timestamp'][:10]
        hist.setdefault(day, {})['views'] = v['count']
        hist[day]['unique_visitors'] = v['uniques']

    for c in clones.get('clones', []):
        day = c['timestamp'][:10]
        hist.setdefault(day, {})['clones'] = c['count']
        hist[day]['unique_cloners'] = c['uniques']

    hist = dict(sorted(hist.items()))
    json.dump(hist, open(HIST_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'已累積 {len(hist)} 天的流量歷史，寫入 {HIST_FILE}')


if __name__ == '__main__':
    main()
