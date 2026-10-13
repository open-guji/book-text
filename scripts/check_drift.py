#!/usr/bin/env python3
"""校验脚本漂移检查（overview#568 B3 步 4，方案 2：哈希文件）。

本仓 scripts/ 里有四个脚本是 overview 的复制品（文件头一行「# 来源：…」除外，其余逐字节相同）。
`scripts/overview-copies.sha256` 记录每个脚本（去掉「来源」行后）的 sha256。

  python3 scripts/check_drift.py                       # CI 用：本仓副本的哈希必须等于记录
  python3 scripts/check_drift.py --overview <overview根> # 改脚本的人用：再核 overview 工作区里的原件
  python3 scripts/check_drift.py --update              # 改完副本后重写哈希文件（须同时同步 overview 原件）

退出码 0 一致，1 有漂移。能防本仓单边改；overview 单边改本仓看不见，靠 --overview 在改的人手里核。
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "overview-copies.sha256")
# 本仓文件名 → overview 里的相对路径
COPIES = {
    "validate_text_format.py": "项目进展/古籍文本/scripts/validate_text_format.py",
    "original_version.py": "项目进展/古籍文本/scripts/original_version.py",
    "zi_convert.py": "项目进展/古籍文本/scripts/zi_convert.py",
    "validate-collated.py": "scripts/validate-collated.py",
}


def digest(path):
    with open(path, "rb") as f:
        lines = [ln for ln in f.read().split(b"\n") if not ln.startswith("# 来源：open-guji-core/overview".encode())]
    return hashlib.sha256(b"\n".join(lines)).hexdigest()


def load_manifest():
    out = {}
    with open(MANIFEST, encoding="utf-8") as f:
        for ln in f:
            if ln.strip() and not ln.startswith("#"):
                h, name = ln.split()[:2]
                out[name] = h
    return out


def main(argv):
    if "--update" in argv:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write("# 由 scripts/check_drift.py --update 生成；sha256 为去掉「# 来源：」行后的内容\n")
            for name in sorted(COPIES):
                f.write(f"{digest(os.path.join(HERE, name))}  {name}\n")
        print("已重写", MANIFEST)
        return 0
    want = load_manifest()
    root = argv[argv.index("--overview") + 1] if "--overview" in argv else None
    bad = 0
    for name, rel in sorted(COPIES.items()):
        got = digest(os.path.join(HERE, name))
        if want.get(name) != got:
            print(f"漂移: scripts/{name} 哈希 {got[:12]} ≠ 记录 {str(want.get(name))[:12]}；改了副本须同步 overview 原件并跑 --update")
            bad += 1
        if root:
            op = os.path.join(root, rel)
            if not os.path.isfile(op):
                print(f"缺失: overview 原件 {rel} 不存在")
                bad += 1
            elif digest(op) != want.get(name):
                print(f"漂移: overview {rel} 与记录不一致（原件被改而本仓副本没跟）")
                bad += 1
    print("drift check", "FAIL" if bad else "OK", f"({len(COPIES)} 个脚本)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
