# 样张生成脚本

一次性脚本，产出本目录下的 5 份静态 HTML。只读 `book-text`（Work 全文/整理本片段）与
`guji-markdown`（`@open-guji/markdown-web` 的 `gujiToHtml`／CSS），不改任何数据仓。

```bash
npm install opencc-js
npm install /path/to/guji-markdown/packages/core /path/to/guji-markdown/packages/web  # 本地包，先在 guji-markdown 里 pnpm build
node build.mjs      # 01–03：条目分行／自然段 × 繁／简 四格
node vertical.mjs   # 04–05：竖排（走 guji-markdown-web 真实渲染）
```

路径写死为本次生成时的 clone 位置（`/home/user/open-guji/book-text`、`/home/user/guji-markdown`），
换机器跑要改开头两个常量。

```bash
node webtex-build.mjs   # 06：webtex-cn 版四库全书仿真竖排（需能 import /path/to/webtex-cn/src/index.js，纯 JS 无需编译）
```
