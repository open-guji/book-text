# scripts/

## 与 overview 共有的四个脚本（校验脚本两份并存）

`validate_text_format.py`、`original_version.py`、`zi_convert.py`、`validate-collated.py` 是 overview 原件的复制品，除文件头「# 来源：」一行外逐字节相同。`overview-copies.sha256` 记录它们（去掉来源行后）的 sha256，CI 的 `drift` 步骤跑 `python3 scripts/check_drift.py`，哈希对不上就红。

改这四个脚本的流程：
1. 两边同改（overview 原件直接推 main；本仓走 PR）。
2. 本仓 `python3 scripts/check_drift.py --update` 重写哈希文件，一并提交。
3. 提交前 `python3 scripts/check_drift.py --overview <overview 根目录>`，确认 overview 原件也与记录一致。

局限：CI 读不了私有的 overview，所以只能拦「本仓副本被单边改」；「overview 原件被单边改」本仓看不见，靠第 3 步在改的人手里核。终态是只留本仓一份、overview 改指针（overview#568，B3 之后另开 PR）。
