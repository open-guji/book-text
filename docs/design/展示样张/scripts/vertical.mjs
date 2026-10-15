// T7 竖排样张：用 guji-markdown-web 的 gujiToHtml + guji-vertical.css 真实渲染（非手工模拟）
import { readFileSync, writeFileSync } from 'node:fs';
import { gujiToHtml, gujiCss, gujiVerticalCss } from '@open-guji/markdown-web';

const BOOK_TEXT = '/home/user/open-guji/book-text/Work';
const OUT_DIR = '/home/user/overview/项目进展/古籍文本/整体设计/展示样张';

function page(title, source, bodyHtml, extraCss = '') {
  return `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<title>${title} · 竖排样张</title>
<style>
${gujiCss}
${gujiVerticalCss}
body{ font-family:"Noto Serif CJK SC","Songti SC",serif; background:#fdfaf4; margin:0; padding:20px 28px 50px; }
h1{ font-size:19px; margin:0 0 4px; }
.src{ color:#888; font-size:12px; margin-bottom:16px; }
.reader{ height:34rem; overflow-x:auto; border:1px solid #ddd6c8; padding:12px 20px; background:#fff; }
.guji-vertical{ height:100%; font-size:19px; line-height:2.05; }
note{ display:block; font-size:12px; color:#999; margin-top:14px; }
${extraCss}
</style>
</head>
<body>
<h1>${title}</h1>
<div class="src">来源：${source}　·　用 @open-guji/markdown-web 的 gujiToHtml 直接渲染，guji-vertical.css 未改动</div>
<div class="reader">
  <article class="guji-doc guji-vertical guji-doc--jz-double">
  ${bodyHtml}
  </article>
</div>
<note>横向滚动条对应"翻页"；夹注按双行小字排入与正文等宽的两栏（CSS column，纯样式层，不改数据）。</note>
</body>
</html>`;
}

// 漢志·六藝略「易類」一段：guji-markdown 原生认 `<…>` 夹注、《…》书名号，可直接喂原始 md 片段
{
  const raw = readFileSync(`${BOOK_TEXT}/g/w/2/d59f23o7ygw2/collated_edition/text/六藝略.md`, 'utf8');
  const block = raw.split(/<!-- p\d+ -->\n?/)[1]; // 易類
  // 逐条目转成 markdown 段落（空行分隔），交给 gujiToHtml 走真正的 CommonMark 解析
  const md = block
    .split('\n')
    .filter((l) => l.trim())
    .join('\n\n');
  const html = gujiToHtml(md);
  writeFileSync(
    `${OUT_DIR}/04-竖排-漢書藝文志-易類.html`,
    page('《漢書藝文志》易類（竖排）', 'book-text 六藝略.md 易類段', html)
  );
}

// 公羊傳 隱公元年：经文+传文夹注，天然适合看竖排双行小注效果
{
  const raw = readFileSync(`${BOOK_TEXT}/t/z/4/d59f1ioj1tz4/full_text/wikisource-01/001.md`, 'utf8');
  const secs = raw.split(/^## /m);
  const yr = secs[2]; // 隱公元年
  const nlIdx = yr.indexOf('\n');
  const md = `## ${yr}`.trim();
  const html = gujiToHtml(md.split('\n\n').slice(1).join('\n\n') || md);
  // 直接用原段（含空行分隔的条目），去掉标题行重复
  const bodyMd = yr.slice(nlIdx + 1);
  writeFileSync(
    `${OUT_DIR}/05-竖排-春秋公羊傳-隱公元年.html`,
    page('《春秋公羊傳》隱公元年（竖排）', 'book-text 001.md 隱公元年段', gujiToHtml(bodyMd))
  );
}

console.log('vertical done');
