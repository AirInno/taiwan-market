"""
川普新聞 RSS 爬蟲
每天由 GitHub Actions 自動執行，結果存入 trump-raw.json
不消耗 Claude token
支援 DeepL Free API 自動翻譯（設定環境變數 DEEPL_API_KEY 即啟用）
"""
import json, os, re, sys, time
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
import urllib.request, urllib.error, urllib.parse

REPO_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT     = os.path.join(REPO_DIR, 'trump-raw.json')
CUTOFF_HRS = 36   # 篩選 RSS 文章的時間窗口（避免抓到太舊的文章）
MAX_DAYS   = None  # 無限保留所有歷史記錄

RSS_FEEDS = [
    # Google News（川普關稅貿易）
    'https://news.google.com/rss/search?q=Trump+tariff+trade+policy&hl=en-US&gl=US&ceid=US:en',
    # Google News（川普台灣半導體）
    'https://news.google.com/rss/search?q=Trump+Taiwan+TSMC+semiconductor&hl=en-US&gl=US&ceid=US:en',
    # Google News（川普科技公司）
    'https://news.google.com/rss/search?q=Trump+Apple+Nvidia+tech+company&hl=en-US&gl=US&ceid=US:en',
    # Google News（川普外交軍事）
    'https://news.google.com/rss/search?q=Trump+China+foreign+policy+military&hl=en-US&gl=US&ceid=US:en',
    # Reuters 政治頻道
    'https://feeds.reuters.com/reuters/politicsNews',
    # AP News 政治
    'https://rsshub.app/apnews/topics/ap-top-news',
]

TRUMP_KEYWORDS = [
    'trump', 'tariff', 'taiwan', 'tsmc', 'semiconductor',
    'trade war', 'executive order', 'truth social',
    'white house', 'oval office',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; NewsCrawler/1.0)',
    'Accept': 'application/rss+xml, application/xml, text/xml',
}


def fetch_feed(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [WARNING] 無法抓取 {url[:60]}... : {e}')
        return None


def parse_date(date_str):
    """解析 RSS pubDate，回傳 UTC datetime"""
    if not date_str:
        return None
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S GMT',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S%z',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    return None


def is_trump_related(text):
    t = text.lower()
    return any(kw in t for kw in TRUMP_KEYWORDS)


def strip_html(text):
    if not text:
        return ''
    return re.sub(r'<[^>]+>', '', text).strip()


def translate_batch(texts, api_key, target_lang='ZH-TW'):
    """呼叫 DeepL Free API 批次翻譯，回傳翻譯後文字清單"""
    if not texts or not api_key:
        return [''] * len(texts)

    # Free API endpoint
    url = 'https://api-free.deepl.com/v2/translate'
    params = [('target_lang', target_lang)]
    for t in texts:
        params.append(('text', t))

    data = urllib.parse.urlencode(params).encode('utf-8')
    req  = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', f'DeepL-Auth-Key {api_key}')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            result = json.loads(r.read().decode('utf-8'))
            return [t['text'] for t in result.get('translations', [])]
    except Exception as e:
        print(f'  [WARNING]  DeepL 翻譯失敗: {e}')
        return [''] * len(texts)


def crawl():
    now_utc   = datetime.now(timezone.utc)
    cutoff    = now_utc - timedelta(hours=CUTOFF_HRS)
    today     = now_utc.astimezone(timezone(timedelta(hours=8))).strftime('%Y%m%d')
    deepl_key = os.environ.get('DEEPL_API_KEY', '')

    articles = []
    seen_titles = set()

    for url in RSS_FEEDS:
        print(f'抓取: {url[:70]}...')
        xml_text = fetch_feed(url)
        if not xml_text:
            continue
        time.sleep(1)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f'  XML 解析失敗: {e}')
            continue

        ns = {'media': 'http://search.yahoo.com/mrss/'}
        items = root.findall('.//item')
        print(f'  找到 {len(items)} 則文章')

        for item in items:
            title = strip_html(item.findtext('title', ''))
            desc  = strip_html(item.findtext('description', ''))
            link  = item.findtext('link', '')
            pub   = item.findtext('pubDate', '') or item.findtext('published', '')

            if not title or not is_trump_related(title + ' ' + desc):
                continue

            # 去除重複
            key = title[:60].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)

            # 時間篩選
            pub_dt = parse_date(pub)
            if pub_dt:
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                pub_str = pub_dt.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
            else:
                pub_str = ''

            articles.append({
                'title':   title,
                'desc':    desc[:200] if desc else '',
                'url':     link,
                'pubTime': pub_str,
                'source':  url.split('/')[2],  # domain
            })

    # 依時間排序（新 → 舊）
    articles.sort(key=lambda x: x['pubTime'], reverse=True)
    articles = articles[:40]  # 最多 40 則

    # DeepL 自動翻譯（若有 API Key）
    if deepl_key and articles:
        print(f'\n[TRANSLATE] 使用 DeepL 翻譯 {len(articles)} 則標題...')
        titles = [a['title'] for a in articles]
        descs  = [a['desc']  for a in articles]
        title_zh = translate_batch(titles, deepl_key)
        desc_zh  = translate_batch(descs,  deepl_key)
        for i, a in enumerate(articles):
            if i < len(title_zh) and title_zh[i]:
                a['titleZh'] = title_zh[i]
            if i < len(desc_zh) and desc_zh[i]:
                a['descZh'] = desc_zh[i]
        print(f'[OK] 翻譯完成')
    else:
        if not deepl_key:
            print('\n[WARNING]  未設定 DEEPL_API_KEY，跳過翻譯')

    today_record = {
        'date':      today,
        'fetchTime': now_utc.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
        'count':     len(articles),
        'articles':  articles,
    }

    # 讀取現有歷史，轉換舊格式（單物件 → 陣列）
    existing = []
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, encoding='utf-8') as f:
                old_data = json.load(f)
            if isinstance(old_data, list):
                existing = old_data
            elif isinstance(old_data, dict) and 'articles' in old_data:
                # 舊格式：轉換為陣列（保留舊資料）
                old_date = old_data.get('fetchDate') or old_data.get('date', '')
                if old_date and old_date != today:
                    old_record = {k: v for k, v in old_data.items() if k != 'fetchDate'}
                    old_record['date'] = old_date
                    existing = [old_record]
        except Exception as e:
            print(f'[WARNING] 讀取舊資料失敗，從頭開始: {e}')

    # 更新今日記錄（upsert）
    existing = [r for r in existing if r.get('date') != today]
    existing.append(today_record)
    existing.sort(key=lambda x: x.get('date', ''), reverse=True)
    if MAX_DAYS:
        existing = existing[:MAX_DAYS]

    print(f'\n[SAVE] 累積歷史記錄：共 {len(existing)} 天')

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    crawl()
