import { renderToPage } from '/home/user/open-guji/webtex-cn/src/index.js';
import { readFileSync, writeFileSync } from 'node:fs';

const OUT = '/home/user/overview/项目进展/古籍文本/整体设计/展示样张';
const BOOK_TEXT = '/home/user/open-guji/book-text/Work';

// 取真实数据：六藝略 易類 前 6 条，转成 webtex-cn 的 tex 语法（\夹注{…}）
const raw = readFileSync(`${BOOK_TEXT}/g/w/2/d59f23o7ygw2/collated_edition/text/六藝略.md`, 'utf8');
const block = raw.split(/<!-- p\d+ -->\n?/)[1];
const entries = block.split('\n').filter((l) => l.trim()).slice(0, 8);

function toTex(line) {
  // <...> 夹注 -> \夹注{...}；书名号《》原样（webtex-cn 自己识别书名号命令，这里保留纯文本亦可读）
  return line.replace(/<([^<>]*)>/g, (_, inner) => `\\夹注{${inner}}`);
}

const body = entries.map(toTex).join('\n\n');

const tex = `\\documentclass[四库全书彩色]{ltc-guji}
\\title{欽定四庫全書}
\\chapter{漢書藝文志\\\\六藝略}

\\begin{document}
\\begin{正文}
${body}
\\end{正文}
\\end{document}`;

const html = renderToPage(tex);
writeFileSync(`${OUT}/06-竖排-webtex-cn-漢書藝文志-易類.html`, html);
console.log('written, tex 长度', tex.length, 'html 长度', html.length);
