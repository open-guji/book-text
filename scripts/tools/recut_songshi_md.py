#!/usr/bin/env python3
"""一次性脚本：按 json 的 section 边界重切宋史藝文志 md 的行界。

背景：协调者 2026-09-26 04:4x 裁决（见 调度/任务书/T3-md-json补真缺.md「裁决」节）——
宋史 md 的"一条一行"切分被一个抽取 bug 切歪了（注者名错挂到上一行行尾），
json 的切分是对的（已用维基文库原文核实）。**不是内容不同，是行界错了**。
修法：以 json 的 section 顺序与字数为准，在 md 原始字符流里重新找切点，
每一段的文字仍然一字不差地取自 md 原文（保留 md 自己的 `（（…））`／「」记号），
只是断行的位置跟 json 走。

算法：
1. 把一卷 md 的正文（去掉顶层 `# 类名` 标题、空行）逐行拼接成一条连续原始
   字符流 `raw`（不额外插入分隔符——md 的断行本身就是要被重新决定的东西）。
2. 边走边剥「记号包裹符号」（与 verify_md.normalize 用同一套），得到
   `norm`（归一后的字符）与一份 `raw_pos`（`norm` 每个字符对应 `raw` 里的下标）。
3. 同样归一并首尾拼接 json 各 section 的 content，得到 `json_norm`。
4. **字流闸**：`norm == json_norm` 才能往下走；不等就跳过这一卷，原样不动，
   记入 ask。
5. 按 json 每个 section 归一后文字的字数，在 `norm`（等价于 `json_norm`）上
   切出对应区间，用 `raw_pos` 映射回 `raw` 的字符区间，取 `raw` 原文（连同
   区间内被跳过的记号字符）作为这个 section 的新行文字。区间之间被跳过的
   字符（记号符号、空白）一律并入前一段末尾——不新增不丢字，只挪断行位置。
6. 重新拼装 md：`# 类名\n\n` + 每段一行、段间一个空行。

用法：
    python3 recut_songshi_md.py <collated_edition 目录> [--apply] [--json 报告出档]
不加 --apply 只跑闸与统计，不改文件；加 --apply 才落盘写 md。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_md as vm  # noqa: E402

_STRIP_SINGLE = set()
for pair in vm._WRAP_PAIRS:
    _STRIP_SINGLE.add(pair[0])
    _STRIP_SINGLE.add(pair[1])

# 已核实的系统性异体字对（md 侧字 -> json 侧字），只用于字流闸的"是否算等同"
# 判断，**不改变落盘文字**——两侧各自的原字原样保留，见任务书§二 4。
# 逐部扫全书才敢确认"系统性"（每一处都是同一个字对，不是零散异文）：
# 幹/干、範/范、衝/沖、鬆/松，均为传统写法与规范字的既有变体，不是内容差异。
KNOWN_VARIANTS_MD_TO_JSON = {"幹": "干", "範": "范", "衝": "沖", "鬆": "松", "麵": "面"}

# 裁决四：这 4 个 work_id 结构上是误建节（内容＝宿主注文＋下一条撰人字头，
# 一个字都不是自己的书名卷数），但索引脚本按标题字面猜出了 work_id，不满足
# "work_id is None" 的硬判据。协调者逐个核对原数据后放行整节删，**只放行这
# 四个，不放宽通用判据**——与 PR #4 删过的 3 个误建节（`d59ezak6jq4g`／
# `d59f2pseahvk`／`d59f2q06llvl`）同类。book-index 里这些 Work 若仍有指向
# 宋史的「收录」记录，是目录总管的事，本道不管。
WHITELIST_REMOVE_WORK_IDS = {
    "d59f2pv58q9u",  # 儒家類《中興書目》：内容＝《子華子》注全文
    "d59f2q0g9ywx",  # 道家類《紫陵語》：内容＝《釋門要錄》注＋「十朋」
    "d59f1il4ot1c",  # 醫書類《甲乙經》：内容＝《黃帝三部針灸經》注＋「岐伯」
    "d59f2pvk84qq",  # 別集類《非有齋類槁》：内容＝《苕溪集》注的后半
}


def _removable_work_id(work_id):
    """work_id 是 None，或在裁决四逐个核过、放行整节删的白名单内。"""
    return work_id is None or work_id in WHITELIST_REMOVE_WORK_IDS


def _max_overlap(a, b):
    """a 的最长后缀恰好等于 b 的前缀，返回重叠字数（找不到则 0）。"""
    max_len = min(len(a), len(b))
    for L in range(max_len, 0, -1):
        if a[-L:] == b[:L]:
            return L
    return 0


def _canon_for_gate(s):
    return "".join(KNOWN_VARIANTS_MD_TO_JSON.get(ch, ch) for ch in s)


def dedup_overlap_lines(lines):
    """md 抽取管线的一个已查实的 bug：相邻两行有重叠——本行结尾错误地"预告"了
    下一行的开头（如 `…郭璞注` / `郭璞注《穆天子傳》…`），下一行自己开头正确，
    本行结尾是多余的。**保留后一行的，删前一行结尾的重复**，重叠阈值取 2 字，
    避免单字巧合误删。这一步只挪／删字符，不判定内容对错，纯几何操作。
    """
    out = list(lines)
    overlaps = []
    # 链式重叠（连续三条以上互相预告下一条）单趟扫不完，反复扫到不动点；
    # 44 卷、几千条，扫几轮成本可忽略。
    changed = True
    while changed:
        changed = False
        for i in range(len(out) - 1):
            L = _max_overlap(out[i], out[i + 1])
            if L >= 2:
                overlaps.append((i, L, out[i][-L:]))
                out[i] = out[i][:-L]
                changed = True
    return out, overlaps


def dedup_overlap_json(sections):
    """裁决二＋裁决三：19 卷字流闸不过，多数是**同一个抽取 bug 出在 json 侧**——
    相邻两条 section 的 `content` 有重叠，但**重叠的归属分两种、删的方向相反**
    （裁决三，回 `20260926-0610-status.md` 那版"一律删前一条尾部"删反了一半）：

    - **撰人／注者名重叠**（不含 `⟨`）：属于**后一条**（撰人前置于所撰
      之书，如 `範傳式`／`蔡幼學`），**删前一条尾部**，后一条不动。
    - **夹注重叠**（**含** `⟨`，不必是整段以 `⟨` 起头——`卷⟨一名《竅甲經》⟩`
      这种"量词＋夹注"同样算，裁决四订正了裁决三"以 `⟨` 起头"的说法）：
      属于**前一条＝宿主**（注跟在所注之书后面），**删后一条开头**，
      前一条（宿主）不动。若删完后一条变成空串**且它的 `work_id` 本来就是
      `None`（或在 `WHITELIST_REMOVE_WORK_IDS` 白名单内，裁决四逐个核过
      放行的 4 个）**——说明它通篇只是从宿主注文里误切出来的独立节
      （PR #4 那 3 处同型），整节标记删除（见下方 `removed`），不是"改了
      内容"，是"这个 section 本不该存在"。

    比较用 `_canon_for_gate` 归一（含已知异体字对，如"範傳式"/"范傳式"这类
    一繁一简的重叠也能对上），**删除动作仍作用在各自原始字符串的那一份上**
    （断言重叠段在两侧归一后确实相等，删的是各自的原文，不会把原字替换掉）。

    sections: 带 `content` 字段的 section dict 列表（只读，不原地改）。
    返回 (new_contents, tail_deletes, head_deletes, removed, containment_removed)：
      - new_contents：与 sections 等长的新 content（含判定整删的，此时已是空串，
        由调用方按 removed 剔除）
      - tail_deletes / head_deletes：[(i, 删了几字, 删的原文), ...]
      - removed：判定为"从注文误建"、应整节删除的下标集合（含 containment_removed）
      - containment_removed：{i: 原 content}，removed 的子集，这些是靠"整段
        原样出现在前一条里"（而非相邻边界重叠）抓到的，见下方补充判据
    """
    out = [s["content"] for s in sections]
    tail_deletes = []
    head_deletes = []
    changed = True
    while changed:
        changed = False
        for i in range(len(out) - 1):
            if not out[i] or not out[i + 1]:
                continue
            ca, cb = _canon_for_gate(out[i]), _canon_for_gate(out[i + 1])
            L = _max_overlap(ca, cb)
            # 阈值 2 字防单字巧合，但"又"单独作衔接词、前后各判一次的重叠
            # 只有 1 字（`…下記》二卷又` / `又《諱行後錄》…`），跟前面"注者名
            # 错位"是同一个 bug 的最短形态，破例放行；别的单字不放，避免
            # 常见字巧合误判
            if L < 2 and not (L == 1 and ca[-1:] == "又"):
                continue
            if "⟨" in ca[-L:]:
                # 夹注型：宿主 i 保留，重叠段从后一条 i+1 开头删
                deleted = out[i + 1][:L]
                assert _canon_for_gate(deleted) == ca[-L:], "重叠段应在两侧归一后相等"
                head_deletes.append((i + 1, L, deleted))
                out[i + 1] = out[i + 1][L:]
            else:
                # 撰人型：后一条 i+1 保留，重叠段从前一条 i 尾部删
                deleted = out[i][-L:]
                head_check = cb[:L]
                assert _canon_for_gate(deleted) == head_check, "重叠段应在两侧归一后相等"
                tail_deletes.append((i, L, deleted))
                out[i] = out[i][:-L]
            changed = True
    removed = {i for i, s in enumerate(sections) if _removable_work_id(s.get("work_id")) and out[i] == ""}

    # 补一种相邻重叠抓不到的形状：宿主注文**中间**提到一本书（后面还有
    # "，即此書也""）"一类收尾字样），误建节的内容是这段中间文字的**原样
    # 整段**，不是"紧贴末尾"的后缀，suffix=prefix 的重叠判定找不到它
    # （`⟨…有劉啟明《占候雲賦式》，即此書也⟩` 与 `有劉啟明《占候雲賦式》`
    # 是"中间截取"关系，不是"边界重叠"关系）。判据收紧到**整段字符串
    # 原样出现在前一条里**（不是任意子串巧合）＋ `work_id is None`＋
    # 至少 4 字，四个条件全占了才认，宁可漏报也不误删。
    # 宿主本身也可能被判定误建（一个注文被拆成两个连续误建节，如《書目》＋
    # 《非有齋類槁》都来自《苕溪集》的同一条注），这时第二个误建节的"前一条"
    # 已经空了——要跳过已删的，找最近一个**没被删**的前条才是真宿主。
    containment_removed = {}
    for i in range(1, len(out)):
        if i in removed or out[i] == "" or not _removable_work_id(sections[i].get("work_id")):
            continue
        c = _canon_for_gate(out[i])
        j = i - 1
        while j >= 0 and j in removed:
            j -= 1
        if j < 0:
            continue
        if len(c) >= 4 and c in _canon_for_gate(out[j]):
            containment_removed[i] = out[i]
            removed.add(i)

    return out, tail_deletes, head_deletes, removed, containment_removed


def _is_ws(ch):
    return ch.isspace()


def build_raw_and_norm(lines):
    """lines: md 正文行列表（已去标题/空行）。返回 (raw, norm, raw_pos)。"""
    raw_parts = []
    for l in lines:
        raw_parts.append(l)
    raw = "".join(raw_parts)

    norm_chars = []
    raw_pos = []
    i = 0
    n = len(raw)
    while i < n:
        # 双层圆括号夹注 （（…）） 的两个字符一起判断
        if raw[i:i + 2] == "（（" or raw[i:i + 2] == "））":
            i += 2
            continue
        ch = raw[i]
        if ch in _STRIP_SINGLE or _is_ws(ch):
            i += 1
            continue
        norm_chars.append(ch)
        raw_pos.append(i)
        i += 1
    return raw, "".join(norm_chars), raw_pos


def recut_one_juan(work_dir, jf, juan_title):
    jpath = os.path.join(work_dir, jf)
    data = json.load(open(jpath, encoding="utf-8"))
    mdpath = os.path.join(work_dir, "text", juan_title + ".md")
    if not os.path.exists(mdpath):
        return {"juan_file": jf, "error": f"找不到 {mdpath}"}

    with open(mdpath, encoding="utf-8") as f:
        raw_text = f.read()
    body_lines = [l for l in raw_text.split("\n") if l.strip() != "" and not l.strip().startswith("#")]
    body_lines, overlaps = dedup_overlap_lines(body_lines)

    raw, norm, raw_pos = build_raw_and_norm(body_lines)

    sections = [s for s in data["sections"] if "content" in s]
    json_contents, tail_deletes, head_deletes, removed, containment_removed = dedup_overlap_json(sections)

    # 整节删除之外——**只看真的被去重叠动过的 section**（不是全书扫一遍
    # work_id 为 None 的条目：大多数 None 就是正常没配上 work_id 的短条目，
    # 跟本轮的重叠判定无关，混进来会把噪音报成"可疑"）。判据不满足两种：
    # "content 被删空但 work_id 不是 None"（结构像误建节，但不敢按 None
    # 判据自动删，留人核）；"work_id 是 None 但删完没空"（正常不该发生，
    # 记一下防脚本本身有洞）。
    touched = {i for i, _, _ in tail_deletes} | {i for i, _, _ in head_deletes}
    suspicious = []
    for i in sorted(touched):
        if i in removed:
            continue
        s = sections[i]
        is_none = s.get("work_id") is None
        is_empty = json_contents[i] == ""
        if is_empty and not is_none:
            suspicious.append({"idx": i, "work_id": s.get("work_id"), "title": s.get("title"),
                                "剩余content": "", "原因": "content去重叠后变空但work_id不是None，结构像误建节但不敢自动删"})
        elif is_none and not is_empty:
            suspicious.append({"idx": i, "work_id": None, "title": s.get("title"),
                                "剩余content": json_contents[i], "原因": "work_id为None但去重叠后未变空（异常，检查脚本）"})

    # 同理：整段包含于前条、但 work_id 不是 None 的，不自动删，只报
    for i in range(1, len(json_contents)):
        if i in removed or json_contents[i] == "" or sections[i].get("work_id") is None:
            continue
        j = i - 1
        while j >= 0 and j in removed:
            j -= 1
        if j < 0:
            continue
        c = _canon_for_gate(json_contents[i])
        if len(c) >= 4 and c in _canon_for_gate(json_contents[j]):
            suspicious.append({"idx": i, "work_id": sections[i].get("work_id"), "title": sections[i].get("title"),
                                "剩余content": json_contents[i],
                                "原因": f"整段包含于第{j}条但work_id不是None，结构像误建节但不敢自动删"})

    effective = [i for i in range(len(sections)) if i not in removed]
    json_norm_parts = [vm.normalize(json_contents[i]) for i in effective]
    json_norm_full = "".join(json_norm_parts)

    def _fmt(i, l, txt, tag):
        s = sections[i]
        return {"work_id": s.get("work_id"), "title": s.get("title"), "删几字": l, "删的原文": txt, "类型": tag}

    result = {
        "juan_file": jf, "juan_title": juan_title,
        "md原始行数": len(body_lines), "json条数": len(sections),
        "md归一后字数": len(norm), "json归一后字数": len(json_norm_full),
        "去重叠处数": len(overlaps), "去重叠合计字数": sum(l for _, l, _ in overlaps),
        "json去重叠处数": len(tail_deletes) + len(head_deletes),
        "json将删": (
            [_fmt(i, l, txt, "删上一条尾") for i, l, txt in tail_deletes]
            + [_fmt(i, l, txt, "删下一条头") for i, l, txt in head_deletes]
            + [{"work_id": sections[i].get("work_id"), "title": sections[i].get("title"),
                "类型": "整节删（误建节·相邻重叠清空）"}
               for i in sorted(removed) if i not in containment_removed]
            + [{"work_id": sections[i].get("work_id"), "title": sections[i].get("title"),
                "类型": "整节删（误建节·整段包含于前条）", "原内容": txt}
               for i, txt in sorted(containment_removed.items())]
        ),
        "json可疑未处理": suspicious,
    }
    if _canon_for_gate(norm) != _canon_for_gate(json_norm_full):
        result["字流闸"] = "不通过"
        # 找第一个不同点，方便人工核查
        for k in range(min(len(norm), len(json_norm_full))):
            if norm[k] != json_norm_full[k] and KNOWN_VARIANTS_MD_TO_JSON.get(norm[k]) != json_norm_full[k]:
                result["首个差异位置"] = k
                result["md侧上下文"] = norm[max(0, k - 20):k + 20]
                result["json侧上下文"] = json_norm_full[max(0, k - 20):k + 20]
                break
        else:
            result["首个差异位置"] = min(len(norm), len(json_norm_full))
            result["长度差"] = len(norm) - len(json_norm_full)
        return result
    result["字流闸"] = "通过"
    if norm != json_norm_full:
        result["字流闸备注"] = "含已知异体字对，落盘时各自保留原字"

    # 按 json 每段字数切 raw——**用"每段第一个被留下字符的位置"当分界**，
    # 段间跳过的记号/空白（典型如闭合的 （（…）） 的 ）） ）并入前一段末尾，
    # 不是后一段开头：（（題卜子夏傳）） 的 ）） 紧跟在"傳"（前一段最后一个
    # 留下的字）之后、下一段首字《之前，理应留在前一段里保持括号完整。
    # 早先按"prev_raw_end 起切到本段最后一个留下字"实现，实际把跳过字符
    # 并进了本段开头，把闭合括号错移到了下一行——这是真的踩过的坑，
    # 靠三重校验（字流闸、多重集自证、下方逐行抽查）才发现。
    for part in json_norm_parts:
        if len(part) == 0:
            result["字流闸"] = f"重切前置假设失败：仍有非整删 section 归一后为空串，见 json可疑未处理（{len(suspicious)} 条）"
            return result
    cursor = 0
    section_starts_raw = []  # 每段第一个被留下字符在 raw 里的下标
    for part in json_norm_parts:
        section_starts_raw.append(raw_pos[cursor])
        cursor += len(part)
    # 每段的终点＝下一段的起点（段间跳过的记号/空白归属前一段），
    # 最后一段吃到文件末尾；第一段前面正常不该有字符，若有也并入第一段。
    new_lines = []
    for k, start in enumerate(section_starts_raw):
        end = section_starts_raw[k + 1] if k + 1 < len(section_starts_raw) else len(raw)
        seg = raw[start:end]
        if k == 0 and start > 0:
            seg = raw[0:start] + seg
        new_lines.append(seg)

    # 校验：新行拼接后的字符多重集合与旧 raw 完全一致（不增不减字，只挪断行）
    old_concat = raw
    new_concat = "".join(new_lines)
    if sorted(old_concat) != sorted(new_concat):
        result["字流闸"] = "重切后自证失败"
        return result

    result["新md行数"] = len([l for l in new_lines if l != ""])
    result["_new_lines"] = new_lines
    result["_juan_title"] = juan_title
    # 供 --apply 写回 json：content 改动的下标 -> 新 content；另存要整节删除的下标。
    # 下标是 data["sections"]（原始、含没有 content 字段的 section）里的下标，
    # 用 id() 从 sections（过滤后的子集）映射回去，避免 title 撞名找错。
    changed_idx = {i for i, _, _ in tail_deletes} | {i for i, _, _ in head_deletes}
    if changed_idx or removed:
        sections_all = data["sections"]
        idx_map = {id(s): k for k, s in enumerate(sections_all)}
        result["_json_content_updates"] = {
            idx_map[id(sections[i])]: json_contents[i] for i in changed_idx if i not in removed
        }
        result["_json_removed_indices"] = sorted(idx_map[id(sections[i])] for i in removed)
        result["_json_file"] = jf
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("work_dir")
    p.add_argument("--apply", action="store_true", help="真的写回 md 文件；不加则只跑闸和统计")
    p.add_argument("--json", default=None)
    a = p.parse_args()

    index = json.load(open(os.path.join(a.work_dir, "index.json"), encoding="utf-8"))
    results = []
    for jf in index["juan_files"]:
        data = json.load(open(os.path.join(a.work_dir, jf), encoding="utf-8"))
        title = data.get("title", "")
        r = recut_one_juan(a.work_dir, jf, title)
        results.append(r)

    passed = [r for r in results if r.get("字流闸") == "通过"]
    failed = [r for r in results if r.get("字流闸") != "通过"]
    print(f"共 {len(results)} 卷，字流闸通过 {len(passed)} 卷，未通过 {len(failed)} 卷")
    for r in failed:
        print(f"  ⚠ {r['juan_file']}（{r.get('juan_title', '')}）：{r.get('字流闸', r.get('error'))}")

    with_json_fix = [r for r in passed if r.get("json将删")]
    if with_json_fix:
        print(f"\n{len(with_json_fix)} 卷字流闸通过前先修了 json 侧重叠，json 将删（三栏：删上一条尾／删下一条头／整节删）：")
        for r in with_json_fix:
            print(f"  {r['juan_file']}（{r['juan_title']}）：{len(r['json将删'])} 处")
            for item in r["json将删"]:
                if item["类型"].startswith("整节删"):
                    extra = f" 原内容={item['原内容']!r}" if "原内容" in item else ""
                    print(f"    [{item['类型']}] work_id={item['work_id']} title={item['title']!r}{extra}")
                else:
                    print(f"    [{item['类型']}] work_id={item['work_id']} title={item['title']!r} "
                          f"删{item['删几字']}字：{item['删的原文']!r}")

    all_suspicious = [(r["juan_file"], r["juan_title"], s) for r in results for s in r.get("json可疑未处理", [])]
    if all_suspicious:
        print(f"\n{len(all_suspicious)} 处「work_id/content 不满足整删判据」，未删，列出：")
        for jf_, title_, s in all_suspicious:
            print(f"  {jf_}（{title_}）idx={s['idx']} work_id={s['work_id']} title={s['title']!r} "
                  f"剩余={s['剩余content']!r} 原因：{s['原因']}")

    if a.apply:
        for r in passed:
            mdpath = os.path.join(a.work_dir, "text", r["_juan_title"] + ".md")
            body = "\n\n".join(r["_new_lines"])
            content = f"# {r['_juan_title']}\n\n{body}\n"
            with open(mdpath, "w", encoding="utf-8") as f:
                f.write(content)
            if r.get("_json_content_updates") or r.get("_json_removed_indices"):
                jpath = os.path.join(a.work_dir, r["_json_file"])
                jdata = json.load(open(jpath, encoding="utf-8"))
                for idx, new_content in r.get("_json_content_updates", {}).items():
                    jdata["sections"][idx]["content"] = new_content
                for idx in sorted(r.get("_json_removed_indices", []), reverse=True):
                    del jdata["sections"][idx]
                json.dump(jdata, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                open(jpath, "a", encoding="utf-8").write("\n")
        print(f"\n已写回 {len(passed)} 个 md 文件，{len(with_json_fix)} 个 json 文件同步去重叠／删误建节")

    if a.json:
        out = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"已写 {a.json}")


if __name__ == "__main__":
    main()
