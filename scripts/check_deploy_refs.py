"""
Hook: 每次 Edit/Write 後確認 deploy.bat 引用的檔案都存在
      並掃描 scripts/*.py 是否有硬編碼絕對路徑
只發出警告，不阻斷操作（exit 0）
"""
import os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# smart_pull.py --setup 自動產生，deploy 前可能不存在，不列入檢查
AUTO_GENERATED = {'fix_stocks.bat', 'backfill.bat'}


def check_deploy_bat():
    bat = os.path.join(REPO, 'deploy.bat')
    if not os.path.exists(bat):
        return []
    with open(bat, encoding='utf-8', errors='replace') as f:
        content = f.read()
    match = re.search(r'^git add\s+([^\r\n]+)', content, re.MULTILINE)
    if not match:
        return []
    missing = []
    for fname in match.group(1).split():
        fname_norm = fname.replace('\\', os.sep)
        if os.path.basename(fname_norm) in AUTO_GENERATED:
            continue
        if not os.path.exists(os.path.join(REPO, fname_norm)):
            missing.append(fname)
    return missing


def check_script_hardcoded_paths():
    """掃描 scripts/*.py 裡的硬編碼 Windows 絕對路徑。"""
    scripts_dir = os.path.join(REPO, 'scripts')
    issues = []
    for fname in sorted(os.listdir(scripts_dir)):
        if not fname.endswith('.py'):
            continue
        with open(os.path.join(scripts_dir, fname), encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f, 1):
                for m in re.findall(r'[A-Z]:\\\\Users\\\\[^\'"]+', line):
                    # 排除 bat 字串常數（含 bat 語法或 echo）
                    if 'echo' not in line.lower() and '.bat' not in line.lower():
                        issues.append(f'  {fname}:{i}: {m}')
    return issues


if __name__ == '__main__':
    warnings = []

    missing = check_deploy_bat()
    if missing:
        warnings.append('[deploy.bat] Missing files (git add will fail):')
        for f in missing:
            warnings.append(f'  [X] {f}')

    hardcoded = check_script_hardcoded_paths()
    if hardcoded:
        warnings.append('[scripts] Hardcoded absolute paths found:')
        warnings.extend(hardcoded)

    if warnings:
        print('\n[WARNING] check_deploy_refs:')
        for w in warnings:
            print(w)
        print()

    sys.exit(0)
