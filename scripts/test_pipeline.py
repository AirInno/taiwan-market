"""
Taiwan Market Pipeline - 資料完整性測試
執行：pytest scripts/test_pipeline.py -v
"""
import json, os, subprocess, sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_pull import merge_data

REPO        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH   = os.path.join(REPO, "data.json")
LATEST_PATH = os.path.join(REPO, "data-latest.json")
REQUIRED    = {"date", "dateLabel", "外資億元", "警示"}
ALERT_VALS  = {"正常", "注意", "高度警戒", "極度警戒"}


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_no_null_bytes():
    with open(DATA_PATH, "rb") as f:
        content = f.read()
    assert b"\x00" not in content, "data.json 含有 null bytes"


def test_valid_json():
    data = _load(DATA_PATH)
    assert isinstance(data, list) and len(data) > 0, "data.json 不是非空陣列"


def test_required_fields():
    data = _load(DATA_PATH)
    for entry in data:
        missing = REQUIRED - set(entry.keys())
        assert not missing, f"{entry.get('date','?')} 缺少欄位：{missing}"


def test_alert_values():
    data = _load(DATA_PATH)
    for entry in data:
        a = entry.get("警示")
        assert a in ALERT_VALS, f"{entry.get('date')} 警示值異常：{a!r}"


def test_signal_score_range():
    data = _load(DATA_PATH)
    for entry in data:
        sig = entry.get("進場訊號")
        if not isinstance(sig, dict):
            continue
        score = sig.get("分數")
        if score is None:
            continue
        assert 0 <= score <= 10, f"{entry.get('date')} 進場訊號分數異常：{score}"


def test_latest_entry_is_recent():
    data    = _load(DATA_PATH)
    last_dt = datetime.strptime(max(e["date"] for e in data), "%Y%m%d").date()
    delta   = (date.today() - last_dt).days
    assert delta <= 5, f"最新資料距今 {delta} 天（{last_dt}），超過 5 天門檻"


def test_foreign_trading_range():
    """外資億元應在合理交易範圍內（-2000 ~ +2000）"""
    data = _load(DATA_PATH)
    for entry in data:
        val = entry.get("外資億元")
        if val is None:
            continue
        assert -2000 <= val <= 2000, \
            f"{entry.get('date')} 外資億元異常：{val}（預期 -2000~+2000）"


def test_holdings_ratio_range():
    """外資持股比率應在 0~100% 之間（累計持股，非每日買賣超）"""
    data = _load(DATA_PATH)
    hold_fields = ("tsmc_hold", "etf0050_hold", "delta_hold")
    for entry in data:
        for field in hold_fields:
            hold = entry.get(field)
            if not isinstance(hold, dict):
                continue
            ratio = hold.get("比率")
            if ratio is None:
                continue
            assert 0 <= ratio <= 100, \
                f"{entry.get('date')} {field}.比率 異常：{ratio}（預期 0~100）"


def test_margin_balance_non_negative():
    """融資/融券餘額應為非負整數"""
    data = _load(DATA_PATH)
    for entry in data:
        margin = entry.get("margin")
        if not isinstance(margin, dict):
            continue
        for stock, m in margin.items():
            for key in ("融資餘額", "融券餘額"):
                val = m.get(key)
                if val is None:
                    continue
                assert val >= 0, \
                    f"{entry.get('date')} {stock}.{key} 為負值：{val}"


def _prev_committed_data():
    """取上一次 git commit 版本的 data.json；取不到（例如首次 commit）回傳 None。"""
    try:
        out = subprocess.run(["git", "show", "HEAD:data.json"], cwd=REPO,
                              capture_output=True, timeout=15)
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    return None


def test_latest_date_not_regressed():
    """最新 date 不可比上一次 git commit 的版本舊。
    跟 test_latest_entry_is_recent 語意不同：那個測「沒有太舊」，抓不到
    「日期欄位有更新但實質是重複/舊資料被寫回」這種更隱蔽的情況。"""
    prev = _prev_committed_data()
    if not prev:
        return
    data = _load(DATA_PATH)
    cur_max = max(e["date"] for e in data)
    prev_max = max(e["date"] for e in prev)
    assert cur_max >= prev_max, \
        f"最新 date 從 {prev_max} 倒退為 {cur_max}，疑似資料未真正更新卻寫回舊資料"


def test_merge_data_prefers_more_complete_side():
    """回歸測試：模擬 auto_pull.bat 可能出現的 race condition——本機剛寫入完整
    資料，這時另一邊（GitHub Actions 或另一個排程）的版本卻更空，merge_data
    必須保留較完整的一方，不能讓合併結果比任一邊都更殘缺。"""
    local_map = {
        "20260701": {
            "date": "20260701", "dateLabel": "7/1", "外資億元": 10, "警示": "正常",
            "外資買超": [{"code": "2330", "name": "x", "張數": 100}],
            "外資賣超": [], "投信買超": [], "投信賣超": [],
            "global": {"sp500": 5000}, "成交金額億": 3000,
        }
    }
    remote_map = {
        "20260701": {
            "date": "20260701", "dateLabel": "7/1", "外資億元": 10, "警示": "正常",
            "外資買超": [], "外資賣超": [], "投信買超": [], "投信賣超": [],
        }
    }
    merged = merge_data(local_map, remote_map)
    assert len(merged) == 1, "同一天的資料合併後應該只有一筆，不是重複或遺漏"
    entry = merged[0]
    assert entry["外資買超"] == local_map["20260701"]["外資買超"], \
        "應保留本機較完整的外資買超清單，不能被較空的一方蓋過"
    assert entry.get("global") == {"sp500": 5000}, "應保留本機獨有的 global 欄位"
    assert entry.get("成交金額億") == 3000, "應保留本機獨有的成交金額億欄位"


def test_merge_data_keeps_union_of_dates():
    """本機與遠端各有對方沒有的交易日時，合併後兩邊日期都要保留，不能互相蓋掉。"""
    local_map = {"20260701": {"date": "20260701"}}
    remote_map = {"20260702": {"date": "20260702"}}
    merged = merge_data(local_map, remote_map)
    assert {e["date"] for e in merged} == {"20260701", "20260702"}


def test_data_latest_consistent():
    data   = _load(DATA_PATH)
    latest = _load(LATEST_PATH)
    tail   = sorted(data, key=lambda x: x["date"])[-10:]
    assert [e["date"] for e in tail] == [e["date"] for e in latest], \
        "data-latest.json 與 data.json 最後 10 筆不一致"
