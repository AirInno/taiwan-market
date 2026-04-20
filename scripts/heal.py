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


if __name__ == "__main__":
    print("[heal] 開始修復...")
    changed = fix_null_bytes() | rebuild_latest()
    print("[heal] 完成：有修復" if changed else "[heal] 完成：無需修復")
