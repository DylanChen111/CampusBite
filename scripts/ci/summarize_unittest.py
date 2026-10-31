"""解析 unittest -v 日志，汇总每个测试文件的通过/失败/错误/耗时。

用法：python scripts/ci/summarize_unittest.py <log1> [log2 ...]

仅做统计报告，不修改任何测试或业务代码；真实失败判定由 CI workflow 负责。
"""

import re
import sys
from pathlib import Path

_RAN_RE = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.MULTILINE)
_FAILED_RE = re.compile(r"^FAILED \((.*)\)$", re.MULTILINE)


def _parse_counts(failed_line):
    failures = 0
    errors = 0
    for part in failed_line.split(","):
        part = part.strip()
        if part.startswith("failures="):
            failures = int(part.split("=", 1)[1])
        elif part.startswith("errors="):
            errors = int(part.split("=", 1)[1])
    return failures, errors


def summarize(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    ran = _RAN_RE.search(text)
    if not ran:
        return {
            "file": Path(path).name,
            "total": None,
            "failures": None,
            "errors": None,
            "passed": None,
            "duration": None,
            "status": "无 Ran 行（导入失败或进程崩溃）",
        }
    total = int(ran.group(1))
    duration = float(ran.group(2))
    failed = _FAILED_RE.search(text)
    if failed:
        failures, errors = _parse_counts(failed.group(1))
        status = "FAILED"
    else:
        failures, errors = 0, 0
        status = "OK"
    return {
        "file": Path(path).name,
        "total": total,
        "failures": failures,
        "errors": errors,
        "passed": max(total - failures - errors, 0),
        "duration": duration,
        "status": status,
    }


def main(argv):
    if not argv:
        print("用法：python scripts/ci/summarize_unittest.py <log1> [log2 ...]", file=sys.stderr)
        return 2

    rows = [summarize(p) for p in argv]

    header = "文件".ljust(28) + "状态".ljust(10) + "总数".rjust(6) + "通过".rjust(6) + "失败".rjust(6) + "错误".rjust(6) + "耗时".rjust(10)
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["total"] is None:
            print(r["file"].ljust(28) + r["status"])
        else:
            print(
                r["file"].ljust(28)
                + r["status"].ljust(10)
                + str(r["total"]).rjust(6)
                + str(r["passed"]).rjust(6)
                + str(r["failures"]).rjust(6)
                + str(r["errors"]).rjust(6)
                + f"{r['duration']:.2f}s".rjust(10)
            )

    valid = [r for r in rows if r["total"] is not None]
    bad = [r for r in rows if r["total"] is None]
    total = sum(r["total"] for r in valid)
    passed = sum(r["passed"] for r in valid)
    failures = sum(r["failures"] for r in valid)
    errors = sum(r["errors"] for r in valid)

    print("-" * len(header))
    print(f"合计：总数 {total}，通过 {passed}，失败 {failures}，错误 {errors}")
    print("注：失败/错误计数含 unittest subTest 展开项，可能大于方法数；通过数按 max(0, 总数-失败-错误) 计。")
    if bad:
        print(f"警告：{len(bad)} 个日志无法解析（见上方状态）。")
    if failures or errors or bad:
        print("结论：存在失败/错误，AC1 未满足，不得标记为通过。")
    else:
        print("结论：全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))