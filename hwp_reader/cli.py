"""AI HWP Reader 명령줄 진입점."""

import argparse
import json
import os
import sys

from . import __version__
from .parser import read_documents, render

EXTS = (".hwp", ".hwpx", ".zip")


def _utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _collect(targets, recursive):
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


def _write(state, path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a" if state.get("append") else "w", encoding="utf-8") as fp:
        fp.write(text)
    state["append"] = True


def main(argv=None):
    _utf8_console()
    ap = argparse.ArgumentParser(
        prog="hwp-reader",
        description="AI가 HWP/HWPX/ZIP의 본문·표·메모·변경추적을 읽게 한다",
    )
    ap.add_argument("target", nargs="+", help="HWP/HWPX/ZIP 파일 또는 폴더")
    ap.add_argument("--format", default="text", choices=["text", "md", "json"],
                    help="출력 형식 (기본 text)")
    ap.add_argument("--tables-only", action="store_true", help="표만 출력")
    ap.add_argument("--memos-only", action="store_true", help="메모만 출력")
    ap.add_argument("--revisions-only", action="store_true", help="변경추적만 출력")
    ap.add_argument("-r", "--recursive", action="store_true", help="폴더를 하위까지 훑는다")
    ap.add_argument("-o", "--out", metavar="경로", help="결과를 파일에 저장한다")
    ap.add_argument("--version", action="version", version=f"hwp-reader {__version__}")
    args = ap.parse_args(argv)

    if sum(bool(x) for x in (args.tables_only, args.memos_only, args.revisions_only)) > 1:
        ap.error("--tables-only, --memos-only, --revisions-only는 하나만 선택할 수 있다")

    try:
        targets = _collect(args.target, args.recursive)
    except FileNotFoundError as exc:
        print(f"{exc}: 파일이나 폴더를 찾을 수 없다", file=sys.stderr)
        return 1
    if not targets:
        print("HWP/HWPX/ZIP 문서가 없다", file=sys.stderr)
        return 1

    state, failed, succeeded = {}, [], 0
    for path in targets:
        try:
            documents = read_documents(path)
        except Exception as exc:  # noqa: BLE001
            failed.append((os.path.basename(path), str(exc)))
            print(f"[실패] {os.path.basename(path)}: {exc}", file=sys.stderr)
            continue

        for document in documents:
            name, blocks = document["file"], document["blocks"]
            if args.tables_only:
                blocks = [b for b in blocks if b["type"] == "table"]
            elif args.memos_only:
                blocks = [b for b in blocks if b["type"] == "memo"]
            elif args.revisions_only:
                blocks = [b for b in blocks if b["type"] == "revision"]

            if args.format == "json":
                body = json.dumps({"file": name, "blocks": blocks}, ensure_ascii=False) + "\n"
            else:
                body = (f"\n{'=' * 70}\n{name}\n{'=' * 70}\n"
                        + render(blocks, args.format, args.tables_only) + "\n")
            if args.out:
                _write(state, args.out, body)
            else:
                sys.stdout.write(body)
            succeeded += 1

    if args.out:
        print(f"{succeeded}개 문서를 {args.out}에 저장했다", file=sys.stderr)
    if failed:
        print(f"\n{len(failed)}건 실패:", file=sys.stderr)
        for name, why in failed:
            print(f"  - {name}: {why}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
