"""CoatLink panel isolation probe - run inside 3D-Coat, read-only.

Question being answered: the user sees the sculpt-tree face counts climbing
while the CoatLink panel is open, and stopping when it closes. Our panel's
draw path now touches no host API (proven with a fake host), so this probe
finds out whether the *panel being open at all* is what drives the number.

It does NOT export, import, select, transform, reduce or save anything. The only
host call it makes is reading the current object's face count, and that is
deliberately coarse: one sample every 4 seconds, so the sampling itself cannot be
mistaken for our old per-frame reads.

  phase A (24 s) - no panel open at all           -> baseline
  phase B (24 s) - the CoatLink panel open        -> the reported condition

Run it from 3D-Coat's Python console:

  exec(open(r"H:\\Misc\\Blender-CoatLink\\coat_side\\diagnostics\\panel_probe.py",
            encoding="utf-8").read())

Keep the 3D-Coat window visible while it runs and watch the sculpt tree. Close
the CoatLink panel yourself afterwards (it has no close API).
"""

import json
import os
import sys
import tempfile
import time
import traceback

import coat

sys.path.insert(0, r'H:\Misc\Blender-CoatLink\coat_side')
import CoatBridgeLib  # noqa: E402

PHASE_SECONDS = 24.0
INTERVAL = 4.0


def sample():
    try:
        return int(coat.Scene.current().Volume().getPolycount())
    except Exception as exc:                       # noqa: BLE001 - report it, do not fail
        return "unavailable: %s" % exc


def run_phase(label, seconds, opener=None):
    if opener is not None:
        opener()
    started = time.time()
    samples = [{"t": 0.0, "faces": sample()}]
    while time.time() - started < seconds:
        coat.io.step(1)                            # keep frames flowing, stay responsive
        time.sleep(0.05)
        elapsed = time.time() - started
        if elapsed - samples[-1]["t"] >= INTERVAL:
            samples.append({"t": round(elapsed, 1), "faces": sample()})
            print("  %s %5.1fs  faces=%s" % (label, samples[-1]["t"], samples[-1]["faces"]))
    return {"phase": label, "seconds": round(time.time() - started, 1), "samples": samples}


def main():
    report = {"object": None, "phases": [], "success": False}
    try:
        report["object"] = CoatBridgeLib._element_name(coat.Scene.current())
        print("Probe object: %s" % report["object"])
        print("Phase A: no panel. Watch the sculpt tree.")
        report["phases"].append(run_phase("A no panel", PHASE_SECONDS))
        print("Phase B: opening the CoatLink panel - watch the same object.")
        report["phases"].append(run_phase("B CoatLink panel", PHASE_SECONDS,
                                          opener=lambda: CoatBridgeLib.show_panel(force=True)))
        report["success"] = True
    except Exception:
        report["traceback"] = traceback.format_exc()
    finally:
        path = os.path.join(tempfile.gettempdir(), "CoatLink-panel-probe.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
        print("\nReport: %s" % path)
        for phase in report["phases"]:
            values = [s["faces"] for s in phase["samples"]]
            print("%-20s %s" % (phase["phase"], values))
    return report


REPORT = main()
