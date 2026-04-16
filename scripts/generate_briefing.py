#!/usr/bin/env python3
"""
generate_briefing.py
每日自動簡報產生器，由 GitHub Actions 呼叫。
讀取 data-latest.json 與 trump-raw.json，呼叫 Claude API 產生簡報後存檔。
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
import anthropic

TW_TZ = timezone(timedelta(hours=8))
REPO  = 'AirInno/taiwan-market'


# ─── 讀取資料 ────────────────────────────────────────────────

def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ─── 建立 Prompt ──────────────────────────────────────────────

def build_prompt(today, recent5, trump_latest, date_str, taiwan_mode, trump_mode):
    display_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    alert        = today.get('警示', '正常')
    trump_count  = trump_latest.get('count', 0)

    # 近五日趨勢表
    trend_rows = '\n'.join(
        f"  {d['dateLabel']}  外資:{d['外資億元']:>8}億  投信:{d['投信億元']:>7}億"
        f"  收盤:{d['收盤']:>9}  漲跌:{d['漲跌']:>+8}  警示:{d['警示']}"
        for d in recent5
    )

    # 台股資料（JSON）
    today_json = json.dumps(today, ensure_ascii=False, indent=2)

    # 川普文章
    if trump_mode == 'analyze':
        arts = trump_latest.get('articles', [])
        trump_block = f"今日則數：{trump_count}\n\n" + '\n\n'.join(
            f"[{a['pubTime']}] {a['title']}\n{a.get('desc', '')}\nURL: {a['url']}"
            for a in arts
        )
    else:
        trump_block = "（今日 count=0，無需分析）"

    # 模式說明
    tw_mode_note = {
        'short':  '短版：直接出報告，Section 1 只含基本欄位，不含5日趨勢表及 Top5 列表。',
        'medium': '中版：Section 1 含5日趨勢表、外資/投信 Top5 列表、護盤比。',
        'full':   '完整版：同中版，另對外資最大買超、最大賣超、投信最大買超個股各提供一段背景分析（根據你的知識庫）。',
    }[taiwan_mode]

    trump_mode_note = (
        '完整分析：生成四段式川普分析（A~D）。' if trump_mode == 'analyze'
        else 'skip：僅輸出一行「今日無川普重大動態」，不生成 <TRUMP_BRIEFING> 區塊。'
    )

    return f"""你是 Bee 的每日簡報代理人。Bee 是台灣股票投資者。所有輸出請用繁體中文。

今日日期：{display_date}
台股模式：{taiwan_mode}　說明：{tw_mode_note}
川普模式：{trump_mode}　說明：{trump_mode_note}

════════════════════════════════
台股資料（最新交易日）
════════════════════════════════
{today_json}

════════════════════════════════
近五日趨勢
════════════════════════════════
{trend_rows}

════════════════════════════════
川普新聞原始資料
════════════════════════════════
{trump_block}

════════════════════════════════
輸出規格
════════════════════════════════

請嚴格使用以下 XML 標記輸出，不要在標記外加任何文字：

<TW_BRIEFING>
# 台股每日簡報 {display_date}

## 一、台股外資動向

警示等級：（正常🟢 / 注意🟡 / 高度警戒🔴 / 極度警戒🔴🔴）+ 文字
外資淨額：+/-X.XX 億元
投信淨額：+/-X.XX 億元

**台積電（2330）**  外資：X 張｜投信：X 張｜警示：X
**元大台灣50（0050）**  外資：X 張｜投信：X 張｜警示：X
**台達電（2308）**  外資：X 張｜投信：X 張｜警示：X

收盤：X（漲跌 +/-X）　成交：X 億元

外資最大買超：**名稱（代號）** +X 張
外資最大賣超：**名稱（代號）** -X 張

（medium / full 模式才加以下區塊）
### 近五日趨勢
| 日期 | 外資億 | 投信億 | 收盤 | 警示 |
...（從 recent5 填入）

外資買超 Top5 / 賣超 Top5 / 投信買超 Top5（表格）
護盤比：X%

（full 模式才加）
### 個股背景
針對外資最大買超、最大賣超、投信最大買超，各一段依知識庫分析的背景說明。

## 二、進場訊號

**訊號：X**　分數：X / 10（連續N天買超，若 連續買超 ≥ 2）
- 依據條列...
操作建議：（一行）
（若 分歧信號 欄位存在）現貨×期貨分歧：[狀態]（現貨X，期貨X方）

## 三、全球市場

| 指標 | 數值 | 漲跌 |
|------|------|------|
| S&P 500 | X | +/-X% |
| VIX | X | +/-X% |
| 黃金 | X | +/-X% |
| 費城半導體 SOX | X | +/-X% |
| 美10年債殖利率 | X% | +/-X% |
| 美元／新台幣 | X | +/-X% |

---
*本簡報依據客觀數據產生，不構成投資建議。*
</TW_BRIEFING>

（若 trump_mode == analyze，則輸出以下區塊；若 skip，則完全省略 <TRUMP_BRIEFING> 標記）
<TRUMP_BRIEFING>
# 川普動態分析 {display_date}

> 今日爬蟲新聞則數：{trump_count} 則｜模式：完整分析

## （A）今日重點摘要

（5 條，每條格式：🔴利空/🟡中性/🟢利多 **粗體主題** — 說明，明確指出對台灣或全球市場的影響）

## （B）社群媒體發文

（引用 Truth Social 帖文，含精確時間 ET，標注可信度 🟢高/🟡中/🔴低；若無法確認原文，明確說明）

## （C）關稅與貿易政策

（關稅/半導體政策動態，附來源連結，明確點出台積電 2330、台達電 2308 影響）

## （D）今日台股影響評估

（短線 1-2週 + 中線 1-3月，偏多/偏空/中性，列出受影響板塊）

**整體情緒：偏多 / 偏空 / 中性**

---
*本分析依據公開資訊產生，不構成投資建議。*
</TRUMP_BRIEFING>

注意：請完整填入所有數字，不要留佔位符如「X」或「...」。
"""


# ─── 呼叫 Claude API ──────────────────────────────────────────

def call_claude(prompt):
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=8192,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.content[0].text


# ─── 解析輸出 ─────────────────────────────────────────────────

def extract_section(text, tag):
    import re
    m = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return m.group(1).strip() if m else None


# ─── 主流程 ───────────────────────────────────────────────────

def main():
    market_data  = load_json('data-latest.json')
    trump_data   = load_json('trump-raw.json')

    today        = market_data[-1]
    recent5      = market_data[-5:]
    trump_latest = trump_data[0]

    alert        = today.get('警示', '正常')
    trump_count  = trump_latest.get('count', 0)
    date_str     = datetime.now(TW_TZ).strftime('%Y%m%d')

    # 判斷模式
    if alert in ('高度警戒', '極度警戒'):
        taiwan_mode = 'full'
    elif alert == '注意':
        taiwan_mode = 'medium'
    else:
        taiwan_mode = 'short'

    trump_mode = 'analyze' if trump_count >= 1 else 'skip'

    print(f"[{date_str}] 台股：{alert} → {taiwan_mode} | 川普：{trump_count} 則 → {trump_mode}")

    # 如果今天的簡報已存在，跳過（避免重複執行）
    tw_path = f'briefings/{date_str}-tw.md'
    if os.path.exists(tw_path):
        print(f"今日簡報已存在（{tw_path}），跳過。")
        sys.exit(0)

    # 產生簡報
    print("呼叫 Claude API...")
    prompt = build_prompt(today, recent5, trump_latest, date_str, taiwan_mode, trump_mode)
    output = call_claude(prompt)

    # 解析
    tw_content    = extract_section(output, 'TW_BRIEFING')
    trump_content = extract_section(output, 'TRUMP_BRIEFING')

    if not tw_content:
        print("錯誤：無法解析 TW_BRIEFING 區塊。原始輸出：")
        print(output[:500])
        sys.exit(1)

    # 寫入檔案（由 workflow 的 git commit 步驟推上去）
    os.makedirs('briefings', exist_ok=True)

    with open(tw_path, 'w', encoding='utf-8') as f:
        f.write(tw_content)
    print(f"✅ 寫入 {tw_path}")

    if trump_mode == 'analyze' and trump_content:
        trump_path = f'briefings/{date_str}-trump.md'
        with open(trump_path, 'w', encoding='utf-8') as f:
            f.write(trump_content)
        print(f"✅ 寫入 {trump_path}")
    elif trump_mode == 'skip':
        print("川普模式 skip，不產生 trump 簡報。")

    print("完成。")


if __name__ == '__main__':
    main()
