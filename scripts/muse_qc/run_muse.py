#!/usr/bin/env python3
"""跑批：对 batch.jsonl 逐段调 `muse exec`，并发 ≤8，撞 429 就全体暂停等窗口。

前提：本机已 `TBH_CREDENTIAL_BACKEND=file muse login` 登录过（本道规矩：登录只由
用户在会话里直接发起，见 inbox 的 ask 单）。登录之前这份脚本跑不动，属预期。

用法：
    python3 run_muse.py --batch batch.jsonl --template prompt_template.txt \
        --schema schema.json --out results.jsonl --log muse_calls_log.json \
        --concurrency 8 --max-model-steps 2

可重跑续传：--out 里已有的 chunk_id 会跳过，不会重复计费。
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

RATE_LIMIT_MARKERS = ("429", "rate limit", "Too Many Requests", "rate_limit")
RESET_TIME_RE = re.compile(r"usage window resets at (\S+)")


def seconds_until_reset(text: str, default: float = 60.0) -> float:
    """真跑撞见过的实际错误：「Subscription quota exhausted. Your usage window
    resets at 2026-09-27T03:34:27Z.」——这种是整个账号的额度窗，不是并发限速，
    盲等 60 秒重试没用，得按它给的重置时间等到位。"""
    m = RESET_TIME_RE.search(text)
    if not m:
        return default
    # 真撞见过的坑：句子里时间戳后面常跟着句号（「resets at ...Z.」），\S+ 会把
    # 句号也抓进时间戳，fromisoformat 解析失败就静默退回默认 60 秒——账号级额度
    # 窗口通常要等几天，60 秒的空等完全没用，必须把尾随的标点去掉再解析。
    raw = m.group(1).rstrip(".,;:)")
    try:
        reset_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return default
    return max(default, (reset_at - datetime.now(timezone.utc)).total_seconds())


class Cooldown:
    """全体共用的撞 429 冷却窗，一个线程报了就让所有线程一起等。"""

    def __init__(self):
        self._until = 0.0
        self._lock = threading.Lock()

    def wait_if_needed(self):
        while True:
            with self._lock:
                remaining = self._until - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 5))

    def trigger(self, seconds: float):
        with self._lock:
            self._until = max(self._until, time.monotonic() + seconds)


def render_prompt(template: str, rec: dict) -> str:
    return (
        template.replace("{{WORK_TITLE}}", rec["work_title"])
        .replace("{{CHAPTER_TITLE}}", rec["chapter_title"])
        .replace("{{CHUNK_ID}}", rec["chunk_id"])
        .replace("{{CHUNK_TEXT}}", rec["text"])
    )


def extract_json(stdout: str):
    """muse exec 的输出格式实测前，先按「取第一段花括号配平的 JSON」兜底解析。

    必须跳过字符串字面量里的花括号——quote/note 字段里常带 `{{`/`{|` 这类原文摘录，
    不跳过会数错配对（撞见过 5/842 条因此误判失败，都是 table 类缺陷的摘录里带 `{`）。
    """
    start = stdout.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stdout)):
        ch = stdout[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stdout[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def call_muse(rec, template, schema_path, max_model_steps, cooldown: Cooldown, workspace_root: Path):
    cooldown.wait_if_needed()
    prompt_text = render_prompt(template, rec)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, dir=workspace_root, encoding="utf-8"
    ) as tf:
        tf.write(prompt_text)
        prompt_path = tf.name

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [
                "muse",
                "exec",
                "--prompt-file",
                prompt_path,
                "--output-schema",
                str(schema_path),
                "--max-model-steps",
                str(max_model_steps),
                "--workspace",
                str(workspace_root),
                # 文本总管转 M1 的实测：不关工具，muse 会先去调 bash，
                # 2 步收不住，报 did not reach a terminal state。
                "--disable-shell",
                "--disable-write",
                "--disable-web-tools",
                "--no-foreign-personal-context",
                "--no-session-log",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return rec["chunk_id"], None, time.monotonic() - t0, "timeout"
    finally:
        Path(prompt_path).unlink(missing_ok=True)

    elapsed = time.monotonic() - t0
    combined = (proc.stdout or "") + (proc.stderr or "")

    # 429 误判坑：chunk_id 是调用方自己写的请求参数、muse 会在 JSON 里原样
    # 回显；如果 work_id 本身恰好带「429」这几个字符（比如 d59f2go429kw），
    # 之前「stdout+stderr 里只要出现 429 就判限速」的检查会把一次完全成功、
    # schema 校验通过的调用误判成撞限速，白白重试到死。真正的限速错误只会
    # 出现在 stderr（诊断信息），stdout 只装 schema 校验过的 JSON——先试着
    # 把 stdout 解析成合法 JSON，解析成功就认成功，不看 429 这种粗暴字符串匹配。
    parsed = extract_json(proc.stdout) if proc.returncode == 0 else None
    if parsed is not None:
        return rec["chunk_id"], parsed, elapsed, None

    if any(marker in combined for marker in RATE_LIMIT_MARKERS):
        wait_s = seconds_until_reset(combined)
        cooldown.trigger(wait_s)
        return rec["chunk_id"], None, elapsed, f"rate_limited(等{wait_s:.0f}s)"
    if proc.returncode != 0:
        return rec["chunk_id"], None, elapsed, f"exit={proc.returncode}: {combined[:200]}"

    return rec["chunk_id"], None, elapsed, f"unparsed_output: {proc.stdout[:200]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, type=Path)
    ap.add_argument("--template", required=True, type=Path)
    ap.add_argument("--schema", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--log", required=True, type=Path)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-model-steps", type=int, default=2)
    args = ap.parse_args()

    if args.concurrency > 8:
        sys.exit("并发不许超过 8（规程铁律）")

    batch = [json.loads(l) for l in args.batch.read_text(encoding="utf-8").splitlines()]
    template = args.template.read_text(encoding="utf-8")

    done_ids = set()
    if args.out.exists():
        for l in args.out.read_text(encoding="utf-8").splitlines():
            if l.strip():
                done_ids.add(json.loads(l)["chunk_id"])
    todo = [r for r in batch if r["chunk_id"] not in done_ids]
    print(f"待跑 {len(todo)}／共 {len(batch)}（已有 {len(done_ids)} 条跳过续传）", file=sys.stderr)

    workspace_root = Path(tempfile.mkdtemp(prefix="muse_qc_"))
    cooldown = Cooldown()

    n_calls = 0
    n_errors = 0
    n_rate_limited = 0
    t_start = time.monotonic()

    out_f = args.out.open("a", encoding="utf-8")
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(
                    call_muse, rec, template, args.schema, args.max_model_steps, cooldown, workspace_root
                ): rec
                for rec in todo
            }
            for fut in as_completed(futures):
                chunk_id, parsed, elapsed, err = fut.result()
                n_calls += 1
                if err == "rate_limited":
                    n_rate_limited += 1
                if err is not None:
                    n_errors += 1
                    print(f"[{chunk_id}] 失败：{err}（{elapsed:.1f}s）", file=sys.stderr)
                    continue
                parsed["chunk_id"] = chunk_id  # 按请求的 chunk_id 写死，不依赖 schema 里有没有要求 muse 自己回填
                parsed["_elapsed_s"] = round(elapsed, 2)
                out_f.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                out_f.flush()
                if n_calls % 20 == 0:
                    print(f"已跑 {n_calls}／{len(todo)}", file=sys.stderr)
    finally:
        out_f.close()

    total_elapsed = time.monotonic() - t_start
    log = {
        "batch_size": len(batch),
        "already_done_before_this_run": len(done_ids),
        "calls_this_run": n_calls,
        "errors": n_errors,
        "rate_limited_hits": n_rate_limited,
        "wall_clock_seconds": round(total_elapsed, 1),
        "concurrency": args.concurrency,
        "max_model_steps": args.max_model_steps,
    }
    args.log.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
