# decision 夹具（副本）

与 guji-format `spec/fixtures/decision/` 同一份（guji-format#13），单测只读本目录。`SHA256SUMS` 是 guji-format 那边的哈希，核对：

    cd scripts/tests/fixtures/decision && sha256sum -c SHA256SUMS   # macOS：shasum -a 256 -c SHA256SUMS

CI 的 `decision 夹具哈希` 步骤会跑同一条命令。

升 `.github/guji-format.pin` 时对照 guji-format 同目录再核一次。
