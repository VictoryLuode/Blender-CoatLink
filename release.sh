#!/usr/bin/env bash
# release.sh — 把「发行 X.Y.Z」变成一次可重复的执行。
#
#   ./release.sh 0.2.1              改版本 → 校验 → 提交 → annotated tag → 打包 → push → gh release → 回读验证
#   ./release.sh 0.2.1 --dry        只演练：显示会改哪些文件，一个字节都不写
#   ./release.sh 0.2.1 --no-push    改 + 提交 + tag + 打包后停下，不 push
#
# 跑这个脚本 ＝ 维护者已确认「发行 X.Y.Z」。版本号永远由维护者定；本脚本只把那句话
# 变成机械动作，不必记任何命令。
#
# 配置在 .version-bump.json：声明本仓的版本落点、CHANGELOG、打包命令、产物。
#
# 三条纪律：
#   * 版本号的唯一真源是 git tag；本脚本把字面量投影到 tag 上，再由 verify.sh 断言相等。
#   * tag 一律 annotated（lightweight 会被 git describe 忽略，实测会退回旧版本）。
#   * gh release create 必须带 --verify-tag，否则 gh 在 tag 不存在时会自己造一个 lightweight tag。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

VERSION=""
DRY=0
PUSH=1
for a in "$@"; do
  case "$a" in
    --dry) DRY=1 ;;
    --no-push) PUSH=0 ;;
    -h|--help) sed -n '3,5p' "$0"; exit 0 ;;
    -*) echo "release: unknown option $a" >&2; exit 2 ;;
    *) VERSION="$a" ;;
  esac
done

die() { printf '\nrelease: %s\n' "$1" >&2; exit 1; }
say() { printf '\n== %s\n' "$1"; }

[ -n "$VERSION" ] || die "usage: ./release.sh <X.Y.Z> [--dry] [--no-push]"
case "$VERSION" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) die "version must look like X.Y.Z (got '$VERSION')" ;;
esac
TAG="v$VERSION"

[ -f .version-bump.json ] || die "no .version-bump.json here — this repo is not wired for release.sh"
PY="$(command -v python || command -v python3 || true)"
[ -n "$PY" ] || die "no python on PATH"
[ -x ./verify.sh ] || die "./verify.sh is missing — releases go through it (see repo-conventions)"

cfg_get() {
  "$PY" -c "import json,sys;print(json.load(open('.version-bump.json',encoding='utf-8')).get(sys.argv[1]) or '')" "$1"
}

# ---------------------------------------------------------------- 1. preflight
say "1. preflight"

if [ "$DRY" -eq 1 ]; then
  echo "   (--dry: skipping the cleanliness / tag-existence checks)"
else
  git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"
  dirty="$(git status --porcelain)"
  if [ -n "$dirty" ]; then
    printf '%s\n' "$dirty" | sed 's/^/   /'
    die "working tree is not clean — commit or stash first"
  fi
  branch="$(git rev-parse --abbrev-ref HEAD)"
  [ "$branch" = "main" ] || echo "   note: on branch '$branch', not 'main'"
  git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && die "tag $TAG already exists"
  echo "   tree clean, tag $TAG free"
fi

./verify.sh --quick || die "verify.sh --quick failed — fix before releasing"

# ---------------------------------------------------------------- 2. 写版本
say "2. apply version $VERSION"

"$PY" - "$VERSION" $([ "$DRY" -eq 1 ] && echo --dry) <<'PYEOF' || die "version write failed"
import datetime, json, pathlib, re, sys

ver = sys.argv[1]
dry = "--dry" in sys.argv[1:]
major, minor, patch = ver.split(".")
cfg = json.loads(pathlib.Path(".version-bump.json").read_text(encoding="utf-8"))


def sub(path, pattern, repl, label):
    p = pathlib.Path(path)
    with open(p, "r", encoding="utf-8", newline="") as fh:
        s = fh.read()
    new, n = re.subn(pattern, repl, s, flags=re.M)
    if n == 0:
        sys.exit(f"{path}: nothing matched for {label} — refusing to guess")
    if dry:
        print(f"   would update {path}  ({label})")
        return
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    print(f"   updated {path}  ({label})")


for t in cfg.get("targets", []):
    kind = t["kind"]
    if kind == "py_version":
        sub(t["path"], r'^__version__\s*=\s*"[^"]+"', f'__version__ = "{ver}"', "py_version")
    elif kind == "bl_info_tuple":
        sub(t["path"], r'("version"\s*:\s*\()\d+,\s*\d+,\s*\d+(\))',
            rf'\g<1>{major}, {minor}, {patch}\g<2>', "bl_info_tuple")
    elif kind == "notes_heading":
        sub(t["path"], r'^(#+ +[^\n]*?v?)\d+\.\d+\.\d+',
            rf'\g<1>{ver}', "notes_heading")
    else:
        sys.exit(f"unknown target kind '{kind}'")

cl = cfg.get("changelog")
if cl and pathlib.Path(cl).exists():
    p = pathlib.Path(cl)
    with open(p, "r", encoding="utf-8", newline="") as fh:
        s = fh.read()
    nl = "\r\n" if "\r\n" in s else "\n"
    if re.search(rf'^#+ +v?{re.escape(ver)}\b', s, re.M):
        print(f"   {cl}: a v{ver} heading is already there")
    else:
        today = datetime.date.today().isoformat()
        entry = f"## v{ver} - {today}{nl}{nl}- {cfg.get('summary_placeholder', 'TODO: what changed')}{nl}{nl}"
        m = re.search(r'^#+ +v?\d+\.\d+\.\d+', s, re.M)
        new = (s[:m.start()] + entry + s[m.start():]) if m else (s.rstrip() + nl + nl + entry)
        if dry:
            print(f"   would prepend a v{ver} heading to {cl}")
        else:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            print(f"   prepended a v{ver} heading to {cl}")
PYEOF

if [ "$DRY" -eq 1 ]; then
  say "dry run"
  echo "   nothing was written. Re-run without --dry to release $TAG."
  exit 0
fi

# ---------------------------------------------------------------- 3. 改完再验
say "3. verify after the bump"
./verify.sh --quick || die "verify.sh --quick failed after the bump — release aborted"

# ---------------------------------------------------------------- 4. 提交 + annotated tag
say "4. commit + annotated tag"
git add -A
git commit -q -m "chore(release): $VERSION" || die "commit failed (nothing to commit?)"
git tag -a "$TAG" -m "$TAG"
echo "   committed and tagged $TAG (annotated)"

# ---------------------------------------------------------------- 5. 打包
PKG="$(cfg_get package)"
if [ -n "$PKG" ]; then
  say "5. package"
  bash -c "$PKG $VERSION" || die "packaging failed — the tag exists locally but nothing was pushed"
else
  say "5. package  (none declared)"
fi

# ---------------------------------------------------------------- 6. push
if [ "$PUSH" -eq 1 ]; then
  say "6. push"
  git push origin HEAD || die "push failed"
  git push origin "$TAG" || die "tag push failed"
else
  say "6. push  (skipped: --no-push)"
fi

# ---------------------------------------------------------------- 7. release notes + gh release
NOTES="$(mktemp)"
NOTES_SRC="$(cfg_get notes_source)"
[ -n "$NOTES_SRC" ] || NOTES_SRC="$(cfg_get changelog)"
[ -n "$NOTES_SRC" ] || NOTES_SRC="CHANGELOG.md"
"$PY" - "$VERSION" "$NOTES" "$NOTES_SRC" <<'PYEOF' 2>/dev/null
import pathlib, re, sys
ver, out, src = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(src)
text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
m = re.search(rf'^#+ +[^\n]*?v?{re.escape(ver)}[^\n]*\n', text, re.M)
if m:
    rest = text[m.end():]
    nxt = re.search(r'^#+ +v?\d+\.\d+\.\d+', rest, re.M)
    body = rest[:nxt.start()] if nxt else rest
else:
    body = text
pathlib.Path(out).write_text((body.strip() or f"Release {ver}") + "\n", encoding="utf-8")
PYEOF

if [ "$PUSH" -eq 1 ]; then
  say "7. github release"
  ARTIFACTS="$(cfg_get artifacts)"
  # shellcheck disable=SC2086
  gh release create "$TAG" $ARTIFACTS \
      --verify-tag \
      --title "$(cfg_get title_prefix) $VERSION" \
      --notes-file "$NOTES" || die "gh release create failed (tag is pushed; create the release by hand)"
else
  say "7. github release  (skipped: --no-push)"
fi
rm -f "$NOTES"

# ---------------------------------------------------------------- 8. 回读验证
say "8. read back"
if [ "$PUSH" -eq 1 ]; then
  git fetch -q --tags origin 2>/dev/null || true
  [ "$(git cat-file -t "$TAG" 2>/dev/null)" = "tag" ] && echo "   tag $TAG is annotated" || die "tag $TAG is not annotated!"
  if gh release view "$TAG" >/dev/null 2>&1; then
    echo "   release $TAG exists"
    gh release view "$TAG" --json tagName,isDraft,url -q '"   " + .tagName + "  " + .url' 2>/dev/null || true
  else
    die "release $TAG not found after create"
  fi
else
  echo "   local only: $(git describe --tags --exact-match 2>/dev/null || echo "tag $TAG")"
fi

printf '\nreleased %s\n' "$TAG"
