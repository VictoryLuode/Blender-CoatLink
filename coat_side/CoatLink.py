# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - 3D-Coat extension entry point.
#
# 3D-Coat imports this module *by name* - the folder under
# ``UserPrefs/Scripts/cExtensions`` whose name is listed in
# ``cExtensions/startup.txt`` - and keeps the ``cExtension`` instance alive for the
# session.  Everything an installer used to do is done in ``onStartup`` below,
# because a ``.3dcpack`` has no installer to run: the two ``ExtraMenuItems`` XML
# files are written per machine (they hold absolute paths), and what older builds
# left behind is cleared away.
#
# Rules taken from this 3D-Coat install:
#
#   * 3D-Coat imports scripts by module name, so ``__name__`` is never
#     ``"__main__"`` - never guard an entry point with ``if __name__ == ...``.
#   * Everything except ``cPy.cCore`` is imported lazily: a broken helper must
#     leave the extension loadable, so 3D-Coat can report the problem instead of
#     losing the extension silently.
#   * Nothing here touches the scene; it writes two small files and returns.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cPy.cCore  # noqa: E402  (3D-Coat's own module, only present inside 3D-Coat)

EXTENSION_NAME = "CoatLink"


def _log(message, exc=False):
    try:
        import CoatLinkLib
        CoatLinkLib.log(message, exc=exc)
    except Exception:
        pass


class CoatLinkExtension(cPy.cCore.cExtension):
    """Keeps the bridge's menu entry and tool buttons in place."""

    def __init__(self):
        cPy.cCore.cExtension.__init__(self)
        _log("%s extension created (source: %s)" % (EXTENSION_NAME, _HERE))

    def onStartup(self):
        """Write our menu files and clear out the leftovers of older builds.

        Runs before the user can click anything, which is why the cleanup belongs
        here rather than in the panel: a machine upgrading from the installer build
        still has a second copy of these scripts and a menu pointing at it.
        """
        try:
            import CoatLinkLib
            added = CoatLinkLib.ensure_launcher()
            _log("%s onStartup (%s)" % (
                EXTENSION_NAME, "wrote " + ", ".join(added) if added else "files current"))
        except Exception:
            _log("%s onStartup failed" % EXTENSION_NAME, exc=True)

    def onExit(self):
        _log("%s exiting" % EXTENSION_NAME)
