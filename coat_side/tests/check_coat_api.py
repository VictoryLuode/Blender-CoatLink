# SPDX-License-Identifier: GPL-3.0-or-later
"""Check every 3D-Coat API call in CoatBridge.py against the shipped stubs.

3D-Coat ships complete type stubs (UserPrefs/PythonAPI/coat.pyi and CMD.pyi).
Parsing them is the cheapest way to be sure a script only calls things that
exist - a typo in an API name fails silently inside 3D-Coat otherwise.

    python coat_side/tests/check_coat_api.py [path/to/CoatBridge.py] [path/to/PythonAPI]
"""

import os
import re
import sys

DEFAULT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "CoatBridge.py")
DEFAULT_API = r"D:\Program Files\3DCoat-2026\UserPrefs\PythonAPI"

CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)")
MEMBER_RE = re.compile(r"^\tdef\s+([A-Za-z_][A-Za-z0-9_]*)")
FUNC_RE = re.compile(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)")

CALL_RE = re.compile(r"\bcoat\.([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?")
CMD_CALL_RE = re.compile(r"\bCMD\.([A-Za-z_][A-Za-z0-9_]*)")


def parse_stub(path):
    """{class name: {members}}, {module level functions}"""
    classes, functions = {}, set()
    current = None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = CLASS_RE.match(line)
            if match:
                current = match.group(1)
                classes.setdefault(current, set())
                continue
            match = MEMBER_RE.match(line)
            if match and current:
                classes[current].add(match.group(1))
                continue
            match = FUNC_RE.match(line)
            if match:
                current = None
                functions.add(match.group(1))
    return classes, functions


def main():
    script_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCRIPT
    api_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_API
    coat_pyi = os.path.join(api_dir, "coat.pyi")
    cmd_pyi = os.path.join(api_dir, "CMD.pyi")
    for path in (script_path, coat_pyi, cmd_pyi):
        if not os.path.isfile(path):
            print("missing file: %s" % path)
            return 2

    classes, functions = parse_stub(coat_pyi)
    _cmd_classes, cmd_functions = parse_stub(cmd_pyi)

    text = open(script_path, "r", encoding="utf-8").read()
    # ignore the import lines themselves
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("import "))

    checked, problems = [], []
    for match in CALL_RE.finditer(body):
        first, second = match.group(1), match.group(2)
        if second is None:
            if first in classes or first in functions:
                checked.append("coat." + first)
            else:
                problems.append("coat.%s is neither a class nor a function" % first)
            continue
        if first not in classes:
            problems.append("coat.%s.%s - no class '%s' in coat.pyi" % (first, second, first))
            continue
        if second not in classes[first]:
            problems.append("coat.%s.%s - class '%s' has no member '%s'" % (first, second, first, second))
            continue
        checked.append("coat.%s.%s" % (first, second))

    for match in CMD_CALL_RE.finditer(body):
        name = match.group(1)
        if name in cmd_functions:
            checked.append("CMD." + name)
        else:
            problems.append("CMD.%s - not declared in CMD.pyi" % name)

    print("checked %d API reference(s) in %s" % (len(set(checked)), os.path.basename(script_path)))
    for name in sorted(set(checked)):
        print("  ok  %s" % name)
    if problems:
        print("\n%d problem(s):" % len(problems))
        for problem in sorted(set(problems)):
            print("  !!  %s" % problem)
        return 1
    print("\nRESULT: every API call exists in the 3D-Coat stubs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
