"""
Taiwan Market Pipeline - 資料完整性測試
執行：pytest scripts/test_pipeline.py -v
"""
import json, os
from datetime import date, datetime

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


def test_data_latest_consistent():
    data   = _load(DATA_PATH)
    latest = _load(LATEST_PATH)
    tail   = sorted(data, key=lambda x: x["date"])[-10:]
    assert [e["date"] for e in tail] == [e["date"] for e in latest], \
        "data-latest.json 與 data.json 最後 10 筆不一致"
