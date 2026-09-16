# SPDX-License-Identifier: GPL-3.0-or-later
"""The panel probe must stay read-only, or it is worse than no probe.

Dry-runs the real diagnostics script against the fake host with the phase
lengths shortened, then asserts it touched nothing but the read-only face count
and never reached for an import, export, transform or slider.

Fake host, no 3D-Coat: this proves what the probe's code does, not what 3D-Coat
does with those calls.
"""

import os
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "coat_side"))
sys.path.insert(0, HERE)

import fake_coat  # noqa: E402

PROBE = os.path.join(ROOT, "coat_side", "diagnostics", "panel_probe.py")
FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="coatlink_probe.")
    fake_coat.make_exchange_tree(tmp)
    coat, cmd = fake_coat.build_environment(tmp)

    source = open(PROBE, encoding="utf-8").read()
    source = source.replace("PHASE_SECONDS = 24.0", "PHASE_SECONDS = 0.6")
    source = source.replace("INTERVAL = 4.0", "INTERVAL = 0.2")
    namespace = {"__name__": "panel_probe_dryrun"}
    exec(compile(source, PROBE, "exec"), namespace)
    report = namespace["REPORT"]

    check("the probe runs to completion", report.get("success") is True, report.get("traceback"))
    check("both phases were recorded",
          [phase["phase"] for phase in report["phases"]] == ["A no panel", "B CoatLink panel"],
          [phase["phase"] for phase in report["phases"]])
    check("phase A samples before anything is opened",
          report["phases"][0]["samples"], report["phases"][0]["samples"])

    check("the probe imports nothing", coat.scene_imports == [], coat.scene_imports)
    check("the probe scales nothing", coat.transforms == [], coat.transforms)
    check("the probe sets no slider", not [c for c in cmd.calls if isinstance(c, tuple)],
          cmd.calls)
    check("the probe exports nothing", cmd.calls == [], cmd.calls)
    check("the probe deletes nothing from any queue",
          not os.path.exists(os.path.join(tmp, "Documents", "3DCoat", "Exchange", "import.txt")))
    steps = [name for name, _args in coat.dialog_log]
    check("the only dialog work is the panel itself",
          steps == ["caption", "noModal", "topRight", "width", "buttons", "params", "onPress", "show"],
          steps)
    check("the probe installs no per-frame callback",
          not any(name == "process" for name in steps), steps)

    print("\nRESULT: %s" % ("the panel probe is read-only" if not FAILURES
                            else "FAILED: " + ", ".join(FAILURES)))
    sys.stdout.flush()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
