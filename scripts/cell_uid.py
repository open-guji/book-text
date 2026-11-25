# -*- coding: utf-8 -*-
"""字格永久编号 u（guji-format 02 §4.10，char v0.6；punct／entity v0.4、norm v0.3；Sheldon 2026-11-24 定）。

格位 key `a` 是位置，补一个字后面整列都变；`u` 是身份，改字、补字、重切都不换。标点、专名、异体挂 u，
双写期与格位 key 并存、须指同一格。本模块是 book-text 各脚本共用的 u 工具，不读写文件：

  形状      u_problems(char)                 char 自身：u 不重、≤u_max、不在 u_retired、写了 u_max 每格必带 u …
  前后版    continuity_problems(old, new)    旧版有的 u 要么还在、要么进了 u_retired；u_max 不减
  伴生层    layer_u_problems(char, line, d)  标记的 u 在 char 里有、与格位 key 指同一格；char 有 u 时必写
  发号      assign_new(char)                 没有 u 的格取 u_max+1（读序），返回新发的 [(a, u)]
  作废      retire_missing(old, new)         旧版有、新版没有、也没登记的 u 记 {u, gone: true}
  重挂      relink(char, line, d)            按 u 把格位 key 改成新 char 里该 u 的格；并掉的跟 into；删掉的挪邻格
  初建      number_char(char, amap=None)     存量迁移：没有身份账按读序 1..N，有账按账（格位 key→u）

校验字（punct pre_char、entity text、norm c）一律只报不改：本模块任何函数都不改校验字。
"""
from __future__ import annotations

CHAR_V06 = "https://open-guji.org/schema/char/v0.6.json"
PUNCT_V04 = "https://open-guji.org/schema/punct/v0.4.json"
ENTITY_V04 = "https://open-guji.org/schema/entity/v0.4.json"
NORM_V03 = "https://open-guji.org/schema/norm/v0.3.json"
LAYER_SCHEMA = {"punct": PUNCT_V04, "entity": ENTITY_V04, "norm": NORM_V03}
LAYER_KEY = {"punct": "punctuations", "entity": "entities", "norm": "items"}


def _is_uint(x, lo=1):
    return isinstance(x, int) and not isinstance(x, bool) and x >= lo


def cells(char):
    """读序的格对象列表。"""
    return [c for p in (char or {}).get("pages") or [] for col in p.get("columns") or []
            for c in col.get("cells") or [] if isinstance(c, dict)]


def has_u(char):
    """这册是否已上 u（写了 u_max 或任一格有 u）。"""
    return "u_max" in (char or {}) or any("u" in c for c in cells(char))


def u_index(char):
    """{u: (读序下标, 格位 key, 字)}；重复的 u 只留第一个（重复由 u_problems 报）。"""
    out = {}
    for i, c in enumerate(cells(char)):
        u = c.get("u")
        if _is_uint(u) and u not in out:
            out[u] = (i, c.get("a"), c.get("c"))
    return out


def a_to_u(char):
    return {c.get("a"): c.get("u") for c in cells(char) if _is_uint(c.get("u"))}


def retired_map(char):
    """{u: into 或 None（删掉）}。"""
    out = {}
    for r in (char or {}).get("u_retired") or []:
        if isinstance(r, dict) and _is_uint(r.get("u")):
            out[r["u"]] = r.get("into") if _is_uint(r.get("into")) else None
    return out


def resolve(char, u, _seen=None):
    """u → 现行的 u：还在就是它；并掉的顺着 into 找；删掉或找不到返回 None。"""
    live = u_index(char)
    ret = retired_map(char)
    seen = set()
    while u is not None and u not in live:
        if u in seen or u not in ret:
            return None
        seen.add(u)
        u = ret[u]
    return u


# ── 检查 ─────────────────────────────────────────────────────────────────

def u_problems(char):
    """char 自身的 u 检查（F-OV-18），返回 [(说明, 子类)]。没上 u 的册返回空。"""
    out = []
    if not has_u(char):
        return out
    umax = char.get("u_max")
    if "u_max" not in char:
        out.append(("有格带 u 但顶层没有 u_max（写了 u 就要写 u_max，每格都带 u）", "u_max:missing"))
    elif not _is_uint(umax, 0):
        out.append((f"u_max={umax!r} 不是 ≥0 的整数", "u_max:type"))
        umax = None
    if char.get("$schema") != CHAR_V06:
        out.append((f"用了 u，$schema 应为 {CHAR_V06}，现为 {char.get('$schema')!r}", "schema"))
    ret = char.get("u_retired")
    rmap = {}
    if ret is not None:
        if not isinstance(ret, list):
            out.append(("u_retired 须是列表", "retired:type"))
        else:
            for k, r in enumerate(ret):
                if not isinstance(r, dict) or not _is_uint(r.get("u")):
                    out.append((f"u_retired[{k}] 须是 {{u, into}} 或 {{u, gone: true}}，u 为正整数", f"retired:{k}"))
                    continue
                has_into, gone = "into" in r, r.get("gone") is True
                if has_into == gone or set(r) - {"u", "into", "gone"} or ("gone" in r and not gone):
                    out.append((f"u_retired[{k}]（u={r['u']}）into 与 gone: true 须二者择一，别的键不许有", f"retired:{k}"))
                elif has_into and not _is_uint(r["into"]):
                    out.append((f"u_retired[{k}]（u={r['u']}）into={r['into']!r} 不是正整数", f"retired:{k}"))
                if r["u"] in rmap:
                    out.append((f"u_retired 里 u={r['u']} 重复", f"retired:dup:{r['u']}"))
                rmap[r["u"]] = r.get("into")
                if umax is not None and r["u"] > umax:
                    out.append((f"u_retired 里 u={r['u']} 超过 u_max={umax}", f"retired:max:{r['u']}"))
    seen = {}
    for c in cells(char):
        a, u = c.get("a"), c.get("u")
        if "u" not in c:
            out.append((f"格 {a} 没有 u（顶层写了 u_max，每格必带 u；新格用 char_edits.py uid 发号）", f"cell:{a}:missing"))
            continue
        if not _is_uint(u):
            out.append((f"格 {a} 的 u={u!r} 不是正整数", f"cell:{a}:type"))
            continue
        if u in seen:
            out.append((f"u={u} 重复：格 {seen[u]} 和 {a}", f"dup:{u}"))
        else:
            seen[u] = a
        if umax is not None and u > umax:
            out.append((f"格 {a} 的 u={u} 超过 u_max={umax}", f"cell:{a}:max"))
        if u in rmap:
            out.append((f"格 {a} 的 u={u} 已在 u_retired 里（作废的号永不复用）", f"cell:{a}:retired"))
    for u, into in rmap.items():
        if _is_uint(into) and into not in seen and resolve(char, into) is None:
            out.append((f"u_retired 里 u={u} 的 into={into} 在本章找不到（也没有继续并到现存的格）", f"retired:into:{u}"))
    return out


def continuity_problems(old, new):
    """同一册前后两版：旧版有的 u 要么还在、要么进了 u_retired；u_max 不减；旧版已作废的号不许复活。
    返回 [(说明, 子类)]；旧版没上 u 时返回空。"""
    out = []
    if not has_u(old):
        return out
    if not has_u(new):
        return [("旧版已有 u，新版把 u 全丢了（改字工具要保留 u）", "dropped")]
    om, nm = old.get("u_max"), new.get("u_max")
    if _is_uint(om, 0) and _is_uint(nm, 0) and nm < om:
        out.append((f"u_max 从 {om} 减到 {nm}（只增不减）", "u_max"))
    live, ret = u_index(new), retired_map(new)
    lost = sorted(u for u in u_index(old) if u not in live and u not in ret)
    for u in lost[:20]:
        i, a, c = u_index(old)[u]
        out.append((f"旧版格 {a}（{c}）的 u={u} 在新版既不在格里、也不在 u_retired 里", f"lost:{u}"))
    if len(lost) > 20:
        out.append((f"另有 {len(lost) - 20} 个旧 u 丢了", "lost:more"))
    for u in sorted(set(retired_map(old)) & set(live)):
        out.append((f"u={u} 旧版已作废，新版又出现在格 {live[u][1]}（作废的号永不复用）", f"revived:{u}"))
    for u, into in retired_map(old).items():
        if u in ret and ret[u] != into:
            out.append((f"u_retired 里 u={u} 旧版是 {into!r}，新版改成 {ret[u]!r}（作废记录只增不改）", f"retired:changed:{u}"))
        elif u not in ret:
            out.append((f"u_retired 里 u={u} 新版删掉了（作废记录只增不改）", f"retired:changed:{u}"))
    return out


def _entries(line, data):
    return (data or {}).get(LAYER_KEY[line]) or []


def layer_u_problems(char, line, data):
    """伴生层（punct／entity／norm）挂 u 的检查（F-OV-18）。返回 [(说明, 子类)]。
    - 条目写了 u：u 在 char 里有；与格位 key 指同一格（双写期）；entity 的 u_start、u_end 同在，读序不倒；
    - char 上了 u：有格位 key 的条目都要写 u（spec 04/05/06：char 有 u 时必写）；
    - 用了 u 的文件 $schema 要写对版本。"""
    out = []
    items = _entries(line, data)
    char_u = has_u(char)
    idx = u_index(char)
    a2u = a_to_u(char)
    used = False
    for i, e in enumerate(items):
        if not isinstance(e, dict):
            continue
        if line == "entity":
            anc = e.get("anchor") or {}
            us, ue = e.get("u_start"), e.get("u_end")
            if ("u_start" in e) != ("u_end" in e):
                out.append((f"实体 #{i} u_start、u_end 须同在", f"e{i}:pair"))
                continue
            if "u_start" in e:
                used = True
                for nm, u, a in (("u_start", us, anc.get("start")), ("u_end", ue, anc.get("end"))):
                    if not _is_uint(u) or u not in idx:
                        out.append((f"实体 #{i} {nm}={u!r} 在 char 里没有", f"e{i}:{nm}:missing"))
                    elif a is not None and idx[u][1] != a:
                        out.append((f"实体 #{i} {nm}={u} 是格 {idx[u][1]}，与 anchor 的 {a} 不是同一格（以 u 为准：remap_anchors.py --by-u 修格位）", f"e{i}:{nm}:anchor"))
                if _is_uint(us) and _is_uint(ue) and us in idx and ue in idx and idx[ue][0] < idx[us][0]:
                    out.append((f"实体 #{i} u_end={ue} 的格在 u_start={us} 之前（读序倒了）", f"e{i}:order"))
            elif char_u and anc.get("start") and anc.get("end"):
                out.append((f"实体 #{i} {anc.get('start')}～{anc.get('end')} 没写 u_start／u_end（char 已上 u）", f"e{i}:nou"))
            continue
        a = e.get("anchor") if line == "punct" else e.get("a")
        if "u" in e:
            used = True
            u = e["u"]
            if not _is_uint(u) or u not in idx:
                out.append((f"{'标点' if line == 'punct' else '异体'} #{i} u={u!r} 在 char 里没有", f"{line[0]}{i}:missing"))
            elif a is not None and idx[u][1] != a:
                out.append((f"{'标点' if line == 'punct' else '异体'} #{i} u={u} 是格 {idx[u][1]}，与格位 {a} 不是同一格（以 u 为准：remap_anchors.py --by-u 修格位）",
                            f"{line[0]}{i}:anchor"))
        elif char_u and a:
            hint = f"（该格 u={a2u[a]}）" if a in a2u else ""
            out.append((f"{'标点' if line == 'punct' else '异体'} #{i} 格位 {a} 没写 u{hint}（char 已上 u）", f"{line[0]}{i}:nou"))
    if used:
        sk = "schema" if (line == "norm" and "schema" in (data or {}) and "$schema" not in data) else "$schema"
        if (data or {}).get(sk) != LAYER_SCHEMA[line]:
            out.append((f"用了 u，$schema 应为 {LAYER_SCHEMA[line]}，现为 {(data or {}).get(sk)!r}", "schema"))
    return out


# ── 写：发号、作废、重挂、初建 ──────────────────────────────────────────────

def assign_new(char):
    """没有 u 的格按读序取 u_max+1，返回 [(a, u)]。就地改 char；顶层补 u_max、$schema。"""
    umax = char.get("u_max")
    if not _is_uint(umax, 0):
        umax = max([c["u"] for c in cells(char) if _is_uint(c.get("u"))] + [0])
    new = []
    for c in cells(char):
        if "u" not in c:
            umax += 1
            _set_u(c, umax)
            new.append((c.get("a"), umax))
    set_top(char, umax, char.get("u_retired"))
    return new


def retire_missing(old, new, into=None):
    """旧版有、新版没有、也没登记作废的 u 记进新版 u_retired。into：{u: 并进的 u}（重切合并时给），
    其余记 gone: true。返回新记的 [(u, into 或 None)]。就地改 new。"""
    live, ret = u_index(new), retired_map(new)
    into = into or {}
    added = []
    lst = list(new.get("u_retired") or [])
    for u in sorted(u_index(old)):
        if u in live or u in ret:
            continue
        if _is_uint(into.get(u)):
            lst.append({"u": u, "into": into[u]})
        else:
            lst.append({"u": u, "gone": True})
        added.append((u, into.get(u)))
    if added:
        umax = max(new.get("u_max") or 0, old.get("u_max") or 0)
        set_top(new, umax, lst)
    return added


def _neighbor(old, new, u, forward):
    """删掉的 u 在旧版读序里往前（forward=False）或往后找第一个新版还在的格，返回其 u；找不到 None。"""
    oc = cells(old)
    live = u_index(new)
    k = next((i for i, c in enumerate(oc) if c.get("u") == u), None)
    if k is None:
        return None
    rng = range(k + 1, len(oc)) if forward else range(k - 1, -1, -1)
    for j in rng:
        v = oc[j].get("u")
        if v in live:
            return v
    return None


def relink(char, line, data, old_char=None):
    """按 u 把伴生层条目的格位 key 改成 char 里该 u 现在的格（就地改）。不改校验字。
    - u 还在：anchor／a ← 该 u 的格位；
    - u 并掉了（u_retired into）：顺着 into 挂到留下的格，记「待看」；
    - u 删掉了：给了 old_char 就挪邻格（标点 after／异体挪前一格，标题 before 挪后一格；
      专名起格往后、止格往前），记「待看」；没有邻格或没给 old_char 就不动，记「对不上」；
    - 条目没写 u：不动（存量迁移用 number_layer 补）。
    返回 (改了格位的条数, [(序号, 旧格, 新格或 None, 说明)] 待看／对不上清单)。"""
    idx = u_index(char)
    items = _entries(line, data)
    moved, review = 0, []

    def follow(u, forward):
        """→ (现行 u 或 None, 说明或 None)。"""
        if u in idx:
            return u, None
        r = resolve(char, u)
        if r is not None:
            return r, f"u={u} 已并进 u={r}"
        if old_char is not None:
            v = _neighbor(old_char, char, u, forward)
            if v is not None:
                return v, f"u={u} 的格删了，挪到{'后' if forward else '前'}邻格 u={v}"
        return None, f"u={u} 的格删了，没有可挪的邻格"

    for i, e in enumerate(items):
        if not isinstance(e, dict):
            continue
        if line == "entity":
            if "u_start" not in e:
                continue
            anc = e.setdefault("anchor", {})
            s, why_s = follow(e["u_start"], True)
            t, why_t = follow(e["u_end"], False)
            old = f"{anc.get('start')}～{anc.get('end')}"
            if s is None or t is None or idx[t][0] < idx[s][0]:
                review.append((i, old, None, "；".join(w for w in (why_s, why_t) if w) or "专名整段删了"))
                continue
            na, nb = idx[s][1], idx[t][1]
            if (na, nb) != (anc.get("start"), anc.get("end")):
                moved += 1
            e["u_start"], e["u_end"] = s, t
            anc["start"], anc["end"] = na, nb
            if why_s or why_t:
                review.append((i, old, f"{na}～{nb}", "；".join(w for w in (why_s, why_t) if w)))
            continue
        if "u" not in e:
            continue
        key = "anchor" if line == "punct" else "a"
        forward = line == "punct" and e.get("pos") == "before"
        v, why = follow(e["u"], forward)
        if v is None:
            review.append((i, e.get(key), None, why))
            continue
        na = idx[v][1]
        if na != e.get(key):
            moved += 1
        old = e.get(key)
        e["u"] = v
        e[key] = na
        if why:
            review.append((i, old, na, why))
    return moved, review


def _set_u(cell, u):
    """把 u 放在 a 之后（与 guji-format 样例同序：a、u、c、…）。"""
    items = [(k, v) for k, v in cell.items() if k != "u"]
    cell.clear()
    placed = False
    for k, v in items:
        cell[k] = v
        if k == "a":
            cell["u"] = u
            placed = True
    if not placed:
        cell["u"] = u


def set_top(char, umax, retired=None):
    """顶层：$schema 升 v0.6，u_max（及非空的 u_retired）放在 pages 之前。"""
    items = [(k, v) for k, v in char.items() if k not in ("u_max", "u_retired")]
    char.clear()
    for k, v in items:
        if k == "pages":
            char["u_max"] = umax
            if retired:
                char["u_retired"] = retired
        char[k] = v
    if "pages" not in char:
        char["u_max"] = umax
        if retired:
            char["u_retired"] = retired
    char["$schema"] = CHAR_V06


def number_char(char, amap=None, umax=None, retired=None):
    """存量迁移：给 char 每格写 u。amap 为 {格位 key: u}（身份账给的）时按账，否则按读序 1..N。
    账里查不到的格接着发新号。返回 {"cells": N, "from_map": k, "new": m, "u_max": …}。
    已上 u 的册原样不动（返回 None）。"""
    if has_u(char):
        return None
    n = from_map = 0
    top = umax if _is_uint(umax, 0) else 0
    if amap:
        top = max([top] + [v for v in amap.values() if _is_uint(v)])
    seen = set()
    pending = []
    for c in cells(char):
        n += 1
        u = (amap or {}).get(c.get("a"))
        if _is_uint(u) and u not in seen:
            _set_u(c, u)
            seen.add(u)
            from_map += 1
        else:
            pending.append(c)
    if not amap:
        for k, c in enumerate(pending, 1):
            _set_u(c, k)
        top = max(top, len(pending))
    else:
        for c in pending:
            top += 1
            _set_u(c, top)
    set_top(char, top, retired)
    return {"cells": n, "from_map": from_map, "new": n - from_map, "u_max": top}


def number_layer(char, line, data):
    """存量迁移：按格位 key 给伴生层条目补 u（双写），升 $schema。不改校验字、不动已有 u。
    返回 (补了的条数, [(序号, 格位, 说明)] 格位在 char 里找不到的)。"""
    a2u = a_to_u(char)
    added, miss = 0, []
    for i, e in enumerate(_entries(line, data)):
        if not isinstance(e, dict):
            continue
        if line == "entity":
            anc = e.get("anchor") or {}
            s, t = anc.get("start"), anc.get("end")
            if "u_start" in e or not s or not t:
                continue
            if s in a2u and t in a2u:
                _insert_after(e, "anchor", (("u_start", a2u[s]), ("u_end", a2u[t])))
                added += 1
            else:
                miss.append((i, f"{s}～{t}", "格位在 char 里找不到"))
            continue
        key = "anchor" if line == "punct" else "a"
        a = e.get(key)
        if "u" in e or not a:
            continue
        if a in a2u:
            _insert_after(e, key, (("u", a2u[a]),))
            added += 1
        else:
            miss.append((i, a, "格位在 char 里找不到"))
    if added:
        if line == "norm" and "schema" in data:
            items = [(k, v) for k, v in data.items() if k != "schema"]
            data.clear()
            data["$schema"] = NORM_V03
            data.update(items)
        else:
            data["$schema"] = LAYER_SCHEMA[line]
    return added, miss


def _insert_after(obj, key, pairs):
    items = list(obj.items())
    obj.clear()
    done = False
    for k, v in items:
        obj[k] = v
        if k == key:
            obj.update(pairs)
            done = True
    if not done:
        obj.update(pairs)
