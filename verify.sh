#!/usr/bin/env bash
# verify.sh — 一条命令回答「这个仓现在可发布吗？」
#
#   ./verify.sh           全量：版本一致 + 语法 + 端到端测试 + 打包依赖
#   ./verify.sh --quick   快速：只做版本一致 + 语法（改文档、小改时用）
#
# 退出码：0 = 全绿可发布；1 = 有失败。
#
# 三条纪律（动这个文件之前先读）：
#   1. 每个 gate 都必须真的能变红。永远绿的 gate 比没有 gate 更糟——它是对
#      坏代码的 ✓ 背书。加 gate 时故意弄坏一次，确认它红了，再改回来。
#   2. 本脚本是验证的唯一入口：本地跑它、发版前跑它、将来 CI 也只调它。
#   3. 版本号的唯一真源是 git tag；文件里的字面量是它的投影，两者必须相等。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

QUICK=0
for a in "$@"; do
  case "$a" in
    --quick) QUICK=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

failed=0
step() { printf '\n== %s\n' "$1"; }
pass() { printf '   ok   %s\n' "$1"; }
fail() { printf '   FAIL %s\n' "$1"; failed=1; }

PY="$(command -v python || command -v python3 || true)"
ADDON="coatlink/__init__.py"

# --------------------------------------------------------- 1. 版本一致性
step "1. version consistency"

if [ -z "$PY" ]; then
  fail "no python on PATH — cannot check bl_info"
else
  # bl_info 必须能被 ast.literal_eval 读出，因为 Blender 就是这么读它的。
  # 写成计算式（如 tuple(int(p) for p in __version__.split("."))）会抛错，
  # 后果是插件在 Edit > Preferences > Add-ons 里直接隐身，且没有任何其它症状。
  code_version="$("$PY" - "$ADDON" <<'PYEOF' 2>&1
import ast, pathlib, sys
path = pathlib.Path(sys.argv[1])
for node in ast.parse(path.read_text(encoding="utf-8")).body:
    if isinstance(node, ast.Assign) and any(
        getattr(t, "id", "") == "bl_info" for t in node.targets
    ):
        try:
            info = ast.literal_eval(node.value)
        except ValueError:
            sys.exit("not-a-literal")
        v = info.get("version")
        print(".".join(str(x) for x in v) if isinstance(v, (tuple, list)) else v)
        break
else:
    sys.exit("no-bl_info")
PYEOF
)"
  case "$code_version" in
    not-a-literal)
      fail "bl_info is NOT a literal — Blender reads it with ast.literal_eval;"
      fail "  a computed value makes the add-on invisible in Preferences"
      code_version=""
      ;;
    no-bl_info) fail "no bl_info assignment found in $ADDON"; code_version="" ;;
    "") fail "bl_info has no \"version\" key"; ;;
    *) pass "bl_info version = $code_version  (literal, Blender-readable)" ;;
  esac
fi

changelog_version="$(grep -m1 -E '^## +v?[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md 2>/dev/null \
  | sed -E 's/^## +v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"

if [ -n "$code_version" ] && [ "$code_version" = "$changelog_version" ]; then
  pass "CHANGELOG.md top heading agrees ($changelog_version)"
else
  fail "version mismatch: bl_info=${code_version:-?}  CHANGELOG=${changelog_version:-none}"
fi

# 已经打了 tag 就顺手查类型：lightweight tag 会被 git describe 忽略
tags_here="$(git tag --points-at HEAD 2>/dev/null || true)"
if [ -z "$tags_here" ]; then
  pass "HEAD carries no tag (fine — this is the pre-release state)"
else
  for t in $tags_here; do
    if [ "$(git cat-file -t "$t" 2>/dev/null)" = "tag" ]; then
      pass "tag $t is annotated"
    else
      fail "tag $t is lightweight — git describe ignores those; re-tag with: git tag -a"
    fi
  done
fi

# --------------------------------------------------------- 2. 语法
step "2. syntax"
if [ -z "$PY" ]; then
  fail "no python on PATH — cannot check syntax"
else
  syntax_report="$("$PY" - <<'PYEOF' 2>&1
import ast, pathlib
bad = []
for p in sorted(pathlib.Path("coatlink").rglob("*.py")):
    try:
        ast.parse(p.read_text(encoding="utf-8"), str(p))
    except SyntaxError as e:
        bad.append(f"{p}:{e.lineno}: {e.msg}")
print("\n".join(bad))
PYEOF
)"
  if [ -z "$syntax_report" ]; then
    pass "all .py under coatlink/ parse"
  else
    fail "$syntax_report"
  fi
fi

# --------------------------------------------------------- 3. 端到端测试
if [ "$QUICK" -eq 1 ]; then
  step "3. tests  (skipped: --quick)"
else
  step "3. tests"
  echo
  if "$REPO/tests/run_tests.sh"; then
    pass "tests/run_tests.sh green"
  else
    fail "tests/run_tests.sh reported failures (see output above)"
  fi
fi

# --------------------------------------------------------- 4. 打包依赖
# 不做产物级试跑：package.sh 固定写 dist/，原地跑会覆盖已有产物。
# 这里只验证它「跑得起来」的两个前提，产物级验证在 release.sh 里做。
step "4. packaging prerequisites"
if bash -n package.sh 2>/dev/null; then
  pass "package.sh parses"
else
  fail "package.sh has a syntax error"
fi
if git archive --format=tar HEAD >/dev/null 2>&1; then
  pass "git archive works (package.sh builds from the committed tree)"
else
  fail "git archive failed — package.sh cannot build from a committed tree"
fi

# --------------------------------------------------------- 汇总
echo
if [ "$failed" -eq 0 ]; then
  echo "VERIFY PASSED — this tree is releasable"
else
  echo "VERIFY FAILED"
fi
exit "$failed"
