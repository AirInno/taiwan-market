# -*- coding: utf-8 -*-
"""本機抓取游庭皓 YouTube 直播字幕（住宅 IP，免代理）。
由 fetch_youtube.bat 呼叫；只負責抓字幕、寫檔，git 由 .bat 處理。
"""
import requests, xml.etree.ElementTree as ET, os, sys, time
from datetime import datetime, timezone, timedelta
from youtube_transcript_api import YouTubeTranscriptApi

CHANNEL_ID = "UC0lbAQVpenvfA2QqzsRtL_g"
TZ_TAIPEI = timezone(timedelta(hours=8))
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
BRIEFINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "briefings")

def main():
    api = YouTubeTranscriptApi()
    for attempt in range(3):
        try:
            resp = requests.get(RSS_URL, headers=HEADERS, timeout=30); resp.raise_for_status(); break
        except Exception as e:
            if attempt == 2:
                print(f"[ERROR] YouTube RSS 連續失敗 3 次：{e}"); return 1
            print(f"[WARN] RSS 失敗，15 秒後重試 ({attempt+1}/3)：{e}"); time.sleep(15)

    ns = {'atom':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}
    root = ET.fromstring(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)  # 本機中午/午後跑，抓當日晨間直播

    pending, errors, saved = [], [], 0
    for entry in root.findall('atom:entry', ns):
        pub = datetime.fromisoformat(entry.find('atom:published', ns).text.replace('Z','+00:00'))
        if pub < cutoff:
            continue
        vid_id = entry.find('yt:videoId', ns).text
        title = entry.find('atom:title', ns).text
        date_str = pub.astimezone(TZ_TAIPEI).strftime('%Y%m%d')
        out_file = os.path.join(BRIEFINGS_DIR, f"{date_str}-youtube-transcript.md")
        if os.path.exists(out_file):
            print(f"[SKIP] 已存在：{date_str}-youtube-transcript.md"); continue
        pending.append(f"{date_str} {title}")
        print(f"[NEW] {title} ({vid_id})")
        try:
            t = api.fetch(vid_id, languages=['zh-TW','zh-Hant','zh'])
            text = ' '.join([s.text for s in t])
            if len(text) < 100:
                print(f"[SKIP] 字幕太短：{vid_id}"); continue
        except Exception as e:
            print(f"[FAIL] 抓字幕失敗（字幕可能尚未生成）：{vid_id} ({e})")
            errors.append(f"{date_str}: {e}"); continue
        os.makedirs(BRIEFINGS_DIR, exist_ok=True)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n- 影片ID: {vid_id}\n")
            f.write(f"- 發布時間: {pub.astimezone(TZ_TAIPEI).strftime('%Y-%m-%d %H:%M')} 台灣時間\n")
            f.write(f"- 連結: https://www.youtube.com/watch?v={vid_id}\n\n---\n\n## 逐字稿\n\n")
            f.write(text)
        print(f"[OK] 已存：{date_str}-youtube-transcript.md"); saved += 1

    if not pending:
        print("[DONE] 本次無新影片"); return 0
    if saved == 0:
        print("[WARN] 偵測到新片但字幕尚未生成，下次排程再試"); return 0
    print(f"[DONE] 成功儲存 {saved} 份字幕"); return 0

if __name__ == "__main__":
    sys.exit(main())
