#!/usr/bin/env python3
import os, re, sys, time
from pathlib import Path

PAT = re.compile(r"(S\d{2}E\d{2})", re.IGNORECASE)

def main():
    apply = "--apply" in sys.argv
    root = None
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            root = a
            break

    if not root:
        root = os.environ.get("VIDEO_DIR")
    if not root:
        print("Usage: rename_to_SxxExx.py [--apply] <VIDEO_DIR>\n"
              "or set VIDEO_DIR in environment/.env", file=sys.stderr)
        sys.exit(2)

    root = Path(root).expanduser().resolve()
    if not root.exists():
        print(f"VIDEO_DIR does not exist: {root}", file=sys.stderr)
        sys.exit(2)

    ts = time.strftime("%Y%m%d-%H%M%S")
    log = Path("/root/repos/vk_stream/logs") / f"rename_map_{ts}.tsv"
    log.parent.mkdir(parents=True, exist_ok=True)

    changes = []
    conflicts = 0

    for p in sorted(root.rglob("*.mkv")):
        m = PAT.search(p.name)
        if not m:
            continue
        new_name = m.group(1).upper() + p.suffix.lower()
        if p.name == new_name:
            continue
        target = p.with_name(new_name)

        if target.exists():
            conflicts += 1
            print(f"CONFLICT (skip): {p} -> {target}")
            continue

        changes.append((p, target))

    print(f"Found {len(changes)} rename(s), {conflicts} conflict(s).")
    if not changes:
        print("Nothing to do.")
        return

    # Dry-run output + log
    with log.open("w", encoding="utf-8") as f:
        f.write("from\tto\n")
        for src, dst in changes:
            f.write(f"{src}\t{dst}\n")
            print(f"{src.name}  ->  {dst.name}")

    print(f"\nMapping written to: {log}")
    if not apply:
        print("\nDry-run only. Re-run with: --apply")
        return

    for src, dst in changes:
        src.rename(dst)
    print("Done.")

if __name__ == "__main__":
    main()
