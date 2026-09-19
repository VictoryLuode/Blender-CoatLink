#!/usr/bin/env bash
# All 3D-Coat side tests.  No 3D-Coat needed: the API names are checked against
# the shipped stubs and the scripts run against a fake `coat` module, with the
# Qt panel built offscreen on 3D-Coat's own Python.
#
#   coat_side/tests/run_tests.sh [path/to/3dc-python.exe]

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
PY="${1:-$(find_coat_python || true)}"

if [ -z "$PY" ] || [ ! -f "$PY" ]; then
    echo "3D-Coat's bundled python was not found (looked in ~/Documents/3DCoat/python-*/)." >&2
    echo "Pass it explicitly: coat_side/tests/run_tests.sh /path/to/python.exe" >&2
    exit 2
fi

cd "$REPO"
failed=0
run() {
    echo "──────────────── $* ────────────────"
    QT_QPA_PLATFORM=offscreen "$PY" "$@" || failed=1
    echo
}

run coat_side/tests/check_coat_api.py
run coat_side/tests/test_coat_side.py
run coat_side/tests/test_coat_tools.py
run coat_side/tests/test_idle_draw.py
run coat_side/tests/test_panel_probe.py
run coat_side/tests/test_coatlink_install.py
run coat_side/tests/test_scoped_send.py
echo "──────────────── install smoke test ────────────────"
bash coat_side/tests/test_install.sh || failed=1
echo

if [ "$failed" -eq 0 ]; then
    echo "ALL 3D-COAT SIDE TESTS PASSED"
else
    echo "SOME 3D-COAT SIDE TESTS FAILED" >&2
fi
exit "$failed"
