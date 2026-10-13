# guji-format 固定版本（pin）

book-text 的 CI 用 `.github/guji-format.pin`（一行 commit 全哈希）取 guji-format 的 `schemas/` 做校验，不跟 main 漂。

## 谁改什么
- guji-format 的 PR **凡动 `schemas/`**，必须同时在 book-text 开一个只改 `.github/guji-format.pin` 的 PR（写明新 commit 与改了什么），两边先后合并：guji-format 先合，取其 main 的合并 commit 填 pin。
- 只动 `spec/`、文档、夹具而不动 `schemas/` 的 guji-format PR，不用 bump pin。

## 漂移提示
CI 作业 `pin-drift` 比较 guji-format main 与 pin 处的 `schemas/` **目录树哈希**（`git rev-parse <commit>:schemas`），不同就红。它是 `continue-on-error`，不拦合并，但 PR 页能看到红叉；看到红就开 bump pin 的 PR，不要无视。

## 本地自查
```
pin=$(cat .github/guji-format.pin)
git -C <guji-format 仓> rev-parse "$pin:schemas" origin/main:schemas   # 两行相同＝没漂
```
