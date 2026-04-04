"""
川普新聞 RSS 爬蟲
每天由 GitHub Actions 自動執行，結果存入 trump-raw.json
不消耗 Claude token
"""
import json, os, re, sys, time
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET
import urllib.request, urllib.error

REPO_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT     = os.path.join(REPO_DIR, 'trump-raw.json')
CUTOFF_HRS = 36   # 只保留最近 36 小時的文章

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
        print(f'  ⚠️  無法抓取 {url[:60]}... : {e}')
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


def crawl():
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc - timedelta(hours=CUTOFF_HRS)
    today   = now_utc.astimezone(timezone(timedelta(hours=8))).strftime('%Y%m%d')

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

    result = {
        'fetchDate': today,
        'fetchTime': now_utc.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
        'count':     len(articles),
        'articles':  articles,
    }

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 共抓到 {len(articles)} 則川普相關新聞，已存入 trump-raw.json')
    return len(articles)


if __name__ == '__main__':
    n = crawl()
    sys.exit(0 if n > 0 else 1)
