# 游庭皓字幕自動抓取 — 本機排程設定說明

> 2026-06-16 建立。原因：GitHub Actions 機房 IP 會被 YouTube 封鎖，導致字幕抓取靜默失敗
> （上次成功是 5/7）。改用你電腦的住宅 IP 抓字幕，免費、最穩。

## 它怎麼運作

1. Windows 工作排程器每天 **11:30 與 14:30** 各跑一次 `fetch_youtube.bat`。
2. `.bat` 會：同步遠端 → 抓游庭皓當日直播字幕 → 存到 `briefings\YYYYMMDD-youtube-transcript.md` → 自動 push 到 GitHub。
3. 隔天的每日簡報就會在「🎙️ 游庭皓財經皓角」讀到最新字幕。
   （兩個時段是冗餘：早上字幕還沒生成時，下午會補抓。）

## 一次性設定（只需做一次）

1. **註冊排程**：在 `C:\Users\lifongye\Documents\taiwan-market\` 資料夾，
   找到 `register_youtube_task.bat`，**雙擊執行**。
   - 看到「Done. Two daily tasks created」就成功了。
   - 若被擋，對它按右鍵 →「以系統管理員身分執行」。

2. **立即測試一次**：雙擊 `fetch_youtube.bat`。
   - 若今天有新直播且字幕已生成 → 會看到 `[OK] 已存：...` 並自動 push。
   - 若顯示 `[WARN] 字幕尚未生成` → 正常，等排程下次再抓即可。

## 維護

- 想停掉：開「工作排程器」刪除 `YT-Transcript-AM` 與 `YT-Transcript-PM` 兩個任務，
  或執行：`schtasks /delete /tn "YT-Transcript-AM" /f`（PM 同理）。
- 電腦在 11:30 / 14:30 需開機；若當下沒開機，Windows 會在下次開機後補跑（預設行為）。
- 雲端 `youtube_transcript.yml` 已停用自動排程（不會再寄失敗信），僅保留供手動測試。

## 注意

- 本機需有 Python（你的 `deploy.bat` 已在用，代表已安裝，無需另裝）。
- 首次執行會自動 `pip install youtube-transcript-api requests`。
