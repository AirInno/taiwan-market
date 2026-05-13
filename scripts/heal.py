"""
Taiwan Market - 自動修復腳本
執行：python scripts/heal.py
修復項目：
  1. data.json null bytes 清除
  2. data-latest.json 重建（與 data.json 最後 10 筆同步）
"""
import json, os, sys

REPO        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH   = os.path.join(REPO, "data.json")
LATEST_PATH = os.path.join(REPO, "data-latest.json")


def fix_null_bytes():
    with open(DATA_PATH, "rb") as f:
        raw = f.read()
    if b"\x00" not in raw:
        return False
    with open(DATA_PATH, "wb") as f:
        f.write(raw.replace(b"\x00", b""))
    print("  ✅ null bytes 清除完成")
    return True


def rebuild_latest():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  ❌ data.json 讀取失敗：{e}")
        sys.exit(1)

    tail = sorted(data, key=lambda x: x["date"])[-10:]

    try:
        with open(LATEST_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if [e["date"] for e in tail] == [e["date"] for e in existing]:
            return False
    except Exception:
        pass

    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(tail, f, ensure_ascii=False, indent=2)
    print("  ✅ data-latest.json 已重建")
    return True


def flag_semantic_anomalies():
    """掃描語意異常（持股比率超範圍、外資億元超範圍），回報但不自動修改"""
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    anomalies = []
    hold_fields = ("tsmc_hold", "etf0050_hold", "delta_hold")

    for entry in data:
        d = entry.get("date", "?")

        val = entry.get("外資億元")
        if val is not None and not (-2000 <= val <= 2000):
            anomalies.append(f"  [{d}] 外資億元超範圍：{val}")

        for field in hold_fields:
            hold = entry.get(field)
            if isinstance(hold, dict):
                ratio = hold.get("比率")
                if ratio is not None and not (0 <= ratio <= 100):
                    anomalies.append(f"  [{d}] {field}.比率 超範圍：{ratio}")

        margin = entry.get("margin")
        if isinstance(margin, dict):
            for stock, m in margin.items():
                for key in ("融資餘額", "融券餘額"):
                    v = m.get(key)
                    if v is not None and v < 0:
                        anomalies.append(f"  [{d}] {stock}.{key} 為負值：{v}")

    if anomalies:
        print("  ⚠️ 發現語意異常（需人工確認，heal 不自動修改）：")
        for a in anomalies:
            print(a)
        return True

    return False


if __name__ == "__main__":
    print("[heal] 開始修復...")
    changed = fix_null_bytes() | rebuild_latest()
    flag_semantic_anomalies()
    print("[heal] 完成：有修復" if changed else "[heal] 完成：無需修復")
