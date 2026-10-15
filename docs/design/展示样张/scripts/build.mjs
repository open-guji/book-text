// T7 展示格式方案：样张生成脚本（一次性，产物落 overview/项目进展/古籍文本/整体设计/展示样张/）
// 只读三个真实 book-text 片段，产出静态自包含 HTML（内嵌繁简两份文本，JS 只做显示切换，不依赖网络）。
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import * as OpenCC from 'opencc-js';

const BOOK_TEXT = '/home/user/open-guji/book-text/Work';
const OUT_DIR = '/home/user/overview/项目进展/古籍文本/整体设计/展示样张';
mkdirSync(OUT_DIR, { recursive: true });

const t2s = OpenCC.Converter({ from: 'tw', to: 'cn' });

// ---------- 夹注扫描（照 book-index-manager primitives.tsx scanJiazhu 的判据搬来，保持与线上一致） ----------
function scanJiazhu(text) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    let close;
    if (ch === '⟨') close = '⟩';
    else if (ch === '<') {
      const nxt = text[i + 1];
      if (nxt === undefined || /[A-Za-z/!?>\s]/.test(nxt)) continue;
      close = '>';
    } else continue;
    const j = text.indexOf(close, i + 1);
    if (j < 0) continue;
    const inner = text.slice(i + 1, j);
    if (inner.includes('\n')) continue;
    out.push({ start: i, end: j + 1, inner });
    i = j;
  }
  return out;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 把一行文本渲染成带夹注 span 的 HTML（书名号《…》另加下划波浪线，专名号本样张未用不处理）
function renderLineHtml(text) {
  const marks = scanJiazhu(text);
  let out = '';
  let last = 0;
  for (const m of marks) {
    out += escapeHtml(text.slice(last, m.start)).replace(/《([^》]*)》/g, '<span class="sm">《$1》</span>');
    out += `<span class="jz">${escapeHtml(m.inner)}</span>`;
    last = m.end;
  }
  out += escapeHtml(text.slice(last)).replace(/《([^》]*)》/g, '<span class="sm">《$1》</span>');
  return out;
}

// 一份原文（若干「条目」，用换行分隔，不含空行）渲染两种模式：
//  lineMode: 条目分行——每条目一个 block，保留数据里现有的"一条一行"（=现在存储的编辑惯例，不等于原刻本真实换行）
//  paraMode: 自然段——同一组条目合并进一个连续段落，条目间插入全角空格作视觉间隔（贴近原刻本单栏连排、只用留白分隔条目的排法）
function renderEntryGroup(rawText, { asParagraph }) {
  const lines = rawText.split('\n').filter((l) => l.length > 0);
  if (asParagraph) {
    return `<p class="para">${lines.map(renderLineHtml).join('　')}</p>`;
  }
  return lines.map((l) => `<div class="line">${renderLineHtml(l)}</div>`).join('\n');
}

// 段落体（论语/公羊传：条目间本来就有空行，等价 markdown 段落）：
//  lineMode：保留现状——每条目独立一个视觉块（现在网站就是这样：pre-line 效果）
//  paraMode：把同一标题层级下的多个条目合并进一个连续段落（需要真的把 <p> 边界拆掉，是内容层合并，不只是 CSS 开关）
function renderParagraphGroup(entries, { asParagraph }) {
  if (asParagraph) {
    return `<p class="para">${entries.map(renderLineHtml).join('　')}</p>`;
  }
  return entries.map((e) => `<div class="line">${renderLineHtml(e)}</div>`).join('\n');
}

function buildGrid(title, source, sections) {
  // sections: [{heading, html_trad_line, html_trad_para, html_simp_line, html_simp_para}]
  const body = sections
    .map(
      (s) => `
    <section class="unit">
      <h3>${escapeHtml(s.heading)}</h3>
      <div class="grid">
        <div class="cell" data-locale="trad" data-mode="line">${s.line_t}</div>
        <div class="cell" data-locale="trad" data-mode="para">${s.para_t}</div>
        <div class="cell" data-locale="simp" data-mode="line">${s.line_s}</div>
        <div class="cell" data-locale="simp" data-mode="para">${s.para_s}</div>
      </div>
    </section>`
    )
    .join('\n');

  return `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)} · 展示格式样张</title>
<style>
  :root{ --fg:#2a2a2a; --bg:#fdfaf4; --meta:#7b6a54; --line:#ddd6c8; }
  body{ font-family:"Noto Serif CJK SC","Songti SC",serif; background:var(--bg); color:var(--fg); margin:0; padding:24px 32px 60px; }
  h1{ font-size:20px; margin:0 0 4px; }
  .src{ color:#888; font-size:12px; margin-bottom:20px; }
  .toolbar{ position:sticky; top:0; background:var(--bg); padding:10px 0; border-bottom:1px solid var(--line); display:flex; gap:18px; align-items:center; z-index:5; }
  .toolbar label{ font-size:13px; margin-right:10px; cursor:pointer; }
  .toolbar b{ font-size:12px; color:var(--meta); }
  section.unit{ margin-top:26px; }
  section.unit h3{ font-size:14px; color:var(--meta); border-left:3px solid var(--meta); padding-left:8px; margin-bottom:10px;}
  .grid{ display:grid; grid-template-columns:1fr 1fr; gap:0 24px; }
  .cell{ display:none; font-size:15px; line-height:2; padding:6px 0; border-bottom:1px dashed var(--line); }
  .cell.show{ display:block; }
  .cell .para{ margin:0; text-align:justify; white-space:normal; }
  .cell .line{ white-space:pre-line; }
  .jz{ font-size:.72em; color:var(--meta); }
  .sm{ text-decoration: none; border-bottom: .06em solid #999; padding: 0 1px; }
  .colhead{ font-size:12px; color:#999; margin-bottom:4px; }
  footer{ margin-top:40px; font-size:12px; color:#999; }
</style>
</head>
<body>
<h1>${escapeHtml(title)}</h1>
<div class="src">来源：${escapeHtml(source)}　·　T7-展示格式方案样张，仅供比较，非最终 UI</div>
<div class="toolbar">
  <b>字形</b>
  <label><input type="radio" name="locale" value="trad" checked /> 繁体（存储原样）</label>
  <label><input type="radio" name="locale" value="simp" /> 简体（OpenCC t2cn 实时转换）</label>
  <span style="width:1px;background:var(--line);height:16px;margin:0 6px;"></span>
  <b>分行</b>
  <label><input type="radio" name="mode" value="line" checked /> 条目分行（现状存储）</label>
  <label><input type="radio" name="mode" value="para" /> 自然段聚合</label>
</div>
${body}
<footer>两列对照：左「条目分行」／右「自然段聚合」，随上方单选切换繁简与分行方式。异体字/原书字形模式：本样张未做——现有数据（维基全文的 variants 是异文非异体字；无 CV 字形库对照）不支持，见方案档 §二·2。</footer>
<script>
function apply(){
  var locale = document.querySelector('input[name=locale]:checked').value;
  var mode = document.querySelector('input[name=mode]:checked').value;
  document.querySelectorAll('.cell').forEach(function(c){
    c.classList.toggle('show', c.dataset.locale===locale && c.dataset.mode===mode);
  });
}
document.querySelectorAll('input[name=locale],input[name=mode]').forEach(function(el){el.addEventListener('change',apply);});
apply();
</script>
</body>
</html>`;
}

// ================= 漢書藝文志·六藝略（p4-p7，易/書/詩三段，条目体） =================
{
  const raw = readFileSync(`${BOOK_TEXT}/g/w/2/d59f23o7ygw2/collated_edition/text/六藝略.md`, 'utf8');
  const blocks = raw.split(/<!-- p\d+ -->\n?/).filter((b) => b.trim());
  const heads = ['易類（p4）', '書類（p5）', '詩類（p6-7 節選）'];
  const sections = blocks.slice(0, 3).map((b, i) => {
    const lineT = renderEntryGroup(b, { asParagraph: false });
    const paraT = renderEntryGroup(b, { asParagraph: true });
    const bs = t2s(b);
    const lineS = renderEntryGroup(bs, { asParagraph: false });
    const paraS = renderEntryGroup(bs, { asParagraph: true });
    return { heading: heads[i] || `第${i + 1}段`, line_t: lineT, para_t: paraT, line_s: lineS, para_s: paraS };
  });
  writeFileSync(
    `${OUT_DIR}/01-漢書藝文志-六藝略.html`,
    buildGrid('《漢書藝文志》六藝略（節選）', 'book-text Work/d59f23o7ygw2/collated_edition/text/六藝略.md（整理本，目录体）', sections)
  );
}

// ================= 論語·學而第一（全文，语录体，条目本已用空行分段） =================
{
  const raw = readFileSync(`${BOOK_TEXT}/k/u/8/d59f1iopaku8/full_text/wikisource-01/001.md`, 'utf8');
  const lines = raw.split('\n');
  const heading = lines[0].replace(/^##\s*/, '').trim();
  const entries = raw
    .split('\n\n')
    .slice(1)
    .map((e) => e.trim())
    .filter(Boolean);
  const lineT = renderParagraphGroup(entries, { asParagraph: false });
  const paraT = renderParagraphGroup(entries, { asParagraph: true });
  const entriesS = entries.map((e) => t2s(e));
  const lineS = renderParagraphGroup(entriesS, { asParagraph: false });
  const paraS = renderParagraphGroup(entriesS, { asParagraph: true });
  writeFileSync(
    `${OUT_DIR}/02-論語-學而第一.html`,
    buildGrid('《論語》學而第一（全篇）', 'book-text Work/d59f1iopaku8/full_text/wikisource-01/001.md（维基文库全文，语录体）', [
      { heading, line_t: lineT, para_t: paraT, line_s: lineS, para_s: paraS },
    ])
  );
}

// ================= 春秋公羊傳·隱公元年-三年（经文+传文夹注，条目内含长夹注） =================
{
  const raw = readFileSync(`${BOOK_TEXT}/t/z/4/d59f1ioj1tz4/full_text/wikisource-01/001.md`, 'utf8');
  const secs = raw.split(/^## /m).filter((s) => s.trim());
  // secs[0] = "隱公\n"（卷标题），之后每个是一个年
  const years = secs.slice(1, 4); // 隱公元年、二年、三年
  const sections = years.map((y) => {
    const nlIdx = y.indexOf('\n');
    const heading = y.slice(0, nlIdx).trim();
    const entries = y
      .slice(nlIdx + 1)
      .split('\n\n')
      .map((e) => e.trim())
      .filter(Boolean);
    const lineT = renderParagraphGroup(entries, { asParagraph: false });
    const paraT = renderParagraphGroup(entries, { asParagraph: true });
    const entriesS = entries.map((e) => t2s(e));
    const lineS = renderParagraphGroup(entriesS, { asParagraph: false });
    const paraS = renderParagraphGroup(entriesS, { asParagraph: true });
    return { heading, line_t: lineT, para_t: paraT, line_s: lineS, para_s: paraS };
  });
  writeFileSync(
    `${OUT_DIR}/03-春秋公羊傳-隱公元年至三年.html`,
    buildGrid('《春秋公羊傳》隱公元年—三年', 'book-text Work/d59f1ioj1tz4/full_text/wikisource-01/001.md（维基文库全文，经传夹注体）', sections)
  );
}

console.log('done ->', OUT_DIR);
