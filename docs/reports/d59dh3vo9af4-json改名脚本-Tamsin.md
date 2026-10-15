# d59dh3vo9af4 json −4 改名：被拦的命令（Tamsin，10-14）

Maren 裁决 A（GUJI-29-裁决-d59dh3vo9af4-json偏移-Maren.md）。我在 book-text 本地分支 `d59dh3vo9af4-json-shift`（基于 main fe90f995）执行下列批量 `git mv`＋改 index／manifest 时，Bash 被自动模式以「Modify Shared Resources」拦截。**未做任何改动，未绕过。** 请 Maren 放行这批命令，或自行执行；执行后我接着跑 validate-collated／CI、写 PR 描述（含 10 例改名对照）。

```bash
cd Work/a/f/4/d59dh3vo9af4
mkdir -p sources
for n in 1 2 3 4; do git mv default/00$n.json sources/卷首$n.json; done
for i in $(seq 5 204); do git mv default/$(printf '%03d' $i).json default/$(printf '%03d' $((i-4))).json; done
python3 - <<'PY'
import json
p='default/index.json'
d=json.load(open(p,encoding='utf8'))
d['chapters']=[c for c in d['chapters'] if not (201<=c['n']<=204)]
def fix(g):
    if 'files' in g:
        g['files']=['%03d'%(int(x)-4) if int(x)<205 else x for x in g['files'] if int(x)>4]
    for c in g.get('children',[]): fix(c)
for g in d['juan_groups']: fix(g)
open(p,'w',encoding='utf8').write(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
m=json.load(open('manifest.json',encoding='utf8'))
m['versions'][0]['chapters_total']=len(d['chapters'])
open('manifest.json','w',encoding='utf8').write(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
PY
```

## 预期结果
- json：卷首1–4（原 001–004）→ 条目级 `sources/卷首N.json`（与版本目录同级的 `sources/`，已有 `ctext/`；spec 07 把 sources 放条目级，我按 spec 放，不放 default/ 下）；005–204 → 001–200；205 附錄不动；md 全不动。
- `default/index.json`：删 `chapters` 里 n=201–204 四条（改名后无对应 md／json）；`juan_groups` 全体文件号 −4、去掉 001–004（卷首），205 不动。例：易類 001–014 → 001–010；詩文評類 199–201 → 195–197；詞曲類 202–204 → 198–200。
- `manifest.json`：default 版 `chapters_total` 205 → 201（wikisource 版仍 205，不动）。
- 全仓 grep：book-text 内只有 `index/texts/6.json`（重建索引即可）、`wikisource/index.json`（转录本自身 001=卷首1 的编号，不动）引用该 id；`default/extra/juan_groups.json` 是旧文件名体系（juanshou/juanNNN），不受影响。
- 同步：guji-format spec/07 §4.2 例外清单（`d59dh3vo9af4` 4 章）与 overview `scripts/book-text/b3_status.py:58` 的例外计数 4 → 0，合并后走各自提交。
