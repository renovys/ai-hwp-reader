"""명령줄 진입점.

    hwp-reader 문서.hwp                  본문 + 표 + 메모
    hwp-reader ./폴더 --format md -o out  마크다운으로 저장(웹 챗봇에 올리기 좋다)
"""

import argparse
import json
import os
import sys

from . import __version__
from .parser import read, render

EXTS = (".hwp", ".hwpx")


def _collect(targets, recursive):
    """파일·폴더 목록을 실제 문서 경로로 편다."""
    out = []
    for target in targets:
        if os.path.isfile(target):
            out.append(target)
        elif os.path.isdir(target):
            if recursive:
                for root, _, names in os.walk(target):
                    out += [os.path.join(root, n) for n in names
                            if n.lower().endswith(EXTS)]
            else:
                out += [os.path.join(target, n) for n in os.listdir(target)
                        if n.lower().endswith(EXTS)]
        else:
            raise FileNotFoundError(target)
    return sorted(out)


def _write(out, path, text):
    """--out이 폴더면 문서마다 한 파일, 파일이면 모아서 한 파일."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a" if out.get("append") else "w", encoding="utf-8") as fp:
        fp.write(text)
    out["append"] = True


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="hwp-reader",
        description="한글 문서(HWP/HWPX)를 표 구조까지 살려 읽는다",
    )
    ap.add_argument("target", nargs="+", help="파일 또는 폴더 (여러 개 가능)")
    ap.add_argument("--format", default="text", choices=["text", "md", "json"],
                    help="출력 형식 (기본 text)")
    ap.add_argument("--tables-only", action="store_true", help="표만 출력")
    ap.add_argument("--memos-only", action="store_true", help="메모만 출력")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="폴더를 하위까지 훑는다")
    ap.add_argument("-o", "--out", metavar="경로",
                    help="결과를 파일이나 폴더에 저장한다 "
                         "(폴더면 문서마다 한 파일. 웹 챗봇에 올릴 때 쓴다)")
    ap.add_argument("--version", action="version",
                    version=f"hwp-reader {__version__}")
    args = ap.parse_args(argv)

    try:
        targets = _collect(args.target, args.recursive)
    except FileNotFoundError as exc:
        print(f"{exc}: 파일이나 폴더를 찾을 수 없다", file=sys.stderr)
        return 1
    if not targets:
        print("한글 문서(.hwp/.hwpx)가 없다", file=sys.stderr)
        return 1

    ext = {"json": ".json", "md": ".md"}.get(args.format, ".txt")
    per_file = bool(args.out) and (os.path.isdir(args.out) or args.out.endswith(os.sep))
    state = {}
    failed = []

    for path in targets:
        name = os.path.basename(path)
        try:
            blocks = read(path)
        except Exception as exc:                       # noqa: BLE001
            failed.append((name, str(exc)))
            print(f"[실패] {name}: {exc}", file=sys.stderr)
            continue

        if args.memos_only:
            memos = [b["text"] for b in blocks if b["type"] == "memo"]
            if args.format == "json":
                body = json.dumps({"file": path, "memos": memos},
                                  ensure_ascii=False) + "\n"
            elif not memos:
                continue
            else:
                body = f"\n{name}\n" + "".join(f"  - {m}\n" for m in memos)
        elif args.format == "json":
            body = json.dumps({"file": path, "blocks": blocks},
                              ensure_ascii=False) + "\n"
        else:
            body = (f"\n{'=' * 70}\n{name}\n{'=' * 70}\n"
                    + render(blocks, args.format, args.tables_only) + "\n")

        if not args.out:
            sys.stdout.write(body)
        elif per_file:
            dest = os.path.join(args.out, os.path.splitext(name)[0] + ext)
            with open(dest, "w", encoding="utf-8") as fp:
                fp.write(body)
        else:
            _write(state, args.out, body)

    if args.out:
        print(f"{len(targets) - len(failed)}개 문서를 {args.out}에 저장했다",
              file=sys.stderr)

    if failed:
        print(f"\n{len(failed)}건 실패:", file=sys.stderr)
        for name, why in failed:
            print(f"  - {name}: {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
