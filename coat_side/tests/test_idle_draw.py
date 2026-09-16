# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing the CoatLink panel must not touch the host at all.

The user reported the sculpt-tree face counts climbing while the panel was open
and stopping the moment it was closed. A redraw path that polls the host scene
(and the state file) is the only thing the panel controls, so this test pokes at
every callable the fake host exposes and fails if a redraw reaches any of them.

Fake host, no 3D-Coat: the numbers below prove what our code calls, not what
3D-Coat does with those calls.
"""

import importlib.util
import os
import sys
import tempfile
import types


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "coat_side"))
sys.path.insert(0, HERE)

import fake_coat  # noqa: E402

FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def _wrap(target, prefix, log):
    """Replace every callable attribute with a recorder; return the names."""
    wrapped = set()
    for attribute in dir(target):
        if attribute.startswith("__"):
            continue
        try:
            value = getattr(target, attribute)
        except Exception:
            continue
        if isinstance(value, types.SimpleNamespace):        # nested namespace
            wrapped |= _wrap(value, prefix + attribute + ".", log)
        elif callable(value):
            setattr(target, attribute, _recorder(prefix + attribute, value, log))
            wrapped.add(prefix + attribute)
    return wrapped


def _recorder(name, function, log):
    def call(*args, **kwargs):
        log.append(name)
        return function(*args, **kwargs)
    return call


def main():
    tmp = tempfile.mkdtemp(prefix="coatlink_idle_draw.")
    fake_coat.make_exchange_tree(tmp)
    coat, cmd = fake_coat.build_environment(tmp)
    host_calls = []
    watched = _wrap(coat, "coat.", host_calls)
    watched |= _wrap(cmd, "CMD.", host_calls)

    spec = importlib.util.spec_from_file_location(
        "idle_draw_lib", os.path.join(ROOT, "coat_side", "CoatBridgeLib.py"))
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    # State file access is disk I/O that must not happen on every redraw either.
    state_calls = []
    for name in ("load_state", "save_state"):
        setattr(bridge, name, _recorder("bridge." + name, getattr(bridge, name), state_calls))

    panel = bridge.CoatBridgePanel()
    panel.ui()                                  # first draw may read nothing host side
    host_calls[:] = []
    state_calls[:] = []

    for _ in range(500):
        panel.ui()
        panel.process()

    check("500 redraws touch no host API", host_calls == [], sorted(set(host_calls)))
    check("500 redraws touch no state file", state_calls == [], sorted(set(state_calls)))
    check("the host surface really was instrumented (>12 entry points)",
          len(watched) > 12, len(watched))

    # An edited control still persists, or the panel would silently drop settings.
    panel.ReductionPercent = 37
    panel.ui()
    check("editing a control still persists it", "bridge.save_state" in state_calls, state_calls)
    check("the persisted value is the edited one",
          bridge.reduction_percent() == 37, bridge.reduction_percent())
    state_calls[:] = []
    panel.ui()
    panel.ui()
    check("an unchanged control is not rewritten every frame", state_calls == [], state_calls)

    print("\nRESULT: %s" % ("all idle-draw checks passed" if not FAILURES
                            else "FAILED: " + ", ".join(FAILURES)))
    sys.stdout.flush()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
