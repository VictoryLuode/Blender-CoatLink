"""Scoped sculpt export. No UI commands and no whole-scene fallback."""
import os
import tempfile

#: How many faces may be asked about, one cross-boundary call each, before the check gives
#: up and refuses the export rather than pretending it passed.  getFaceObject() has no
#: bulk form, and a mismatch caused by the packaging node - the usual one - never reaches
#: the scan at all, so this only bounds the genuinely suspicious case.
FACE_SCAN_BUDGET = 2000000


def selected_nodes(coat):
    """The nodes selected in the Sculpt Tree, when the build tells us about them.

    Scene.current() is one node; the tree's own selection is what says whether the
    artist picked several, and 3D-Coat's extraction takes them all when asked to
    (all_selected).  A build that cannot answer hands back nothing, and then a send
    stays what it always was: the current node plus its children.
    """
    try:
        root = coat.Scene.sculptRoot()
    except Exception:
        return []
    if root is None:
        return []
    try:
        found = root.collectSelected()
    except Exception:
        return []
    return [element for element in (found or []) if element is not None]


def _is_wrap(label, wrap_name):
    """Is this group the node 3D-Coat wraps a Blender import in ("bridge", "bridge1")?

    The name is the exchange model's own name, so it cannot collide with a sculpt object
    the artist made.  The node itself carries the name ("bridge"), and a second import of
    the same file gets a digit tail ("bridge1") - both are packaging.  An empty name means
    the caller does not want the rule at all.
    """
    name = str(label or "").strip().lower()
    wanted = str(wrap_name or "").strip().lower()
    if not wanted or not name.startswith(wanted):
        return False
    rest = name[len(wanted):]
    # the node itself ("bridge") and the ones 3D-Coat adds for a second import ("bridge1")
    # are both packaging; only a plain name with a digit tail counts as one
    return not rest or rest.isdigit()


def _read_text(path):
    """The text of an OBJ 3D-Coat wrote, whatever encoding it wrote it in.

    The file is rewritten after the packaging groups are taken out, so a byte the reader
    could not make sense of would be replaced by a question mark and *written back* - a
    name quietly damaged rather than a read that fails.  Object names are the artist's, so
    they are finished with whatever their machine types in.
    """
    with open(path, 'rb') as handle:
        blob = handle.read()
    if blob.startswith(b'\xef\xbb\xbf'):
        return blob.decode('utf-8-sig', 'replace')
    if blob.startswith(b'\xff\xfe') or blob.startswith(b'\xfe\xff'):
        return blob.decode('utf-16', 'replace')
    if b'\x00' in blob[:64]:
        return blob.decode('utf-16-le' if blob[1:2] == b'\x00' else 'utf-16-be', 'replace')
    try:
        return blob.decode('utf-8')
    except UnicodeDecodeError:
        pass
    for codec in ('mbcs', 'cp1252'):
        try:
            return blob.decode(codec)
        except (LookupError, UnicodeDecodeError):
            continue
    return blob.decode('latin-1', 'replace')


def _lines(path):
    return _read_text(path).splitlines(True)


def _drop_groups(path, drop):
    """Rewrite the OBJ without the named groups, and without their material lines.

    Used for the groups that are packaging rather than objects: the node 3D-Coat wrapped
    the last import in, and the carried-over wrap for the model Blender sent.
    """
    handle, cleaned = tempfile.mkstemp(prefix='bridge_clean_', suffix='.obj',
                                       dir=os.path.dirname(path))
    os.close(handle)
    group = None
    try:
        with open(cleaned, 'w', encoding='utf-8', newline='\n') as target:
            for line in _lines(path):
                if line.startswith(('o ', 'g ')):
                    group = (line[2:].strip() or None)
                    if group and group.lower() in drop:
                        continue
                    target.write(line)
                elif line.startswith('usemtl ') and group and group.lower() in drop:
                    continue          # it would otherwise land on the group before it
                else:
                    target.write(line)
        os.replace(cleaned, path)
    finally:
        if os.path.exists(cleaned):
            os.remove(cleaned)


def export_subtree(coat, path, reduction=0, wrap_name=""):
    """Extract what is selected, write it as OBJ, return (names, faces, node count).

    One node or several: the Sculpt Tree's own selection decides, and every selected
    node brings its children.  The names returned are those that really carry geometry,
    which is also what the shader map is written from.  ``wrap_name`` is the exchange
    model's own name, so 3D-Coat's packaging node for a Blender import can be left out.
    """
    element = coat.Scene.current()
    if element is None:
        raise RuntimeError('Select a sculpt Tree node first')
    volume = element.Volume()
    mesh = coat.Mesh()
    percent = max(0.0, min(99.0, float(reduction)))
    chosen = selected_nodes(coat)
    several = len(chosen) > 1
    if percent:
        mesh.fromReducedVolume(volume, percent, True, several)
    else:
        mesh.fromVolume(volume, True, several)
    if not mesh.valid() or mesh.facesCount() <= 0:
        raise RuntimeError('Selected Tree subtree contains no exportable sculpt mesh')
    names = [mesh.getObjectName(i) for i in range(mesh.getObjectsCount())]
    if not names:
        raise RuntimeError('Mesh extraction returned no object groups; export cancelled')
    fd, temporary = tempfile.mkstemp(prefix='bridge_export_', suffix='.obj', dir=os.path.dirname(path))
    os.close(fd)
    try:
        if not mesh.Write(temporary) or os.path.getsize(temporary) == 0:
            raise RuntimeError('Selected-subtree OBJ export failed')
        vertices = faces = 0
        order = []
        by_group = {}
        group = [None]
        for line in _lines(temporary):
                if line.startswith('v '):
                    vertices += 1
                elif line.startswith('f '):
                    faces += 1
                    by_group[group[0]] = by_group.get(group[0], 0) + 1
                elif line.startswith(('o ', 'g ')):
                    label = line[2:].strip()
                    if label:
                        order.append(label)
                        group[0] = label
        if not vertices or not faces:
            raise RuntimeError('Exported OBJ contains no geometry; previous return preserved')
        if by_group.get(None):
            raise RuntimeError('OBJ has geometry outside its object groups; export cancelled')
        kept = [label for label in order if by_group.get(label)]
        if not kept:
            raise RuntimeError('OBJ lost object groups; refusing a merged subtree export')
        if not set(kept).issubset(set(names)):
            raise RuntimeError('OBJ describes objects that were not exported; cancelled')
        # 3D-Coat wraps every model Blender sends in a node named after the file, and that
        # node comes back out as a group of its own ("bridge").  It is packaging, not an
        # object, and the artist asked for it not to travel - as long as something else in
        # the file carries geometry, which is what its children are.
        wraps = [label for label in kept if _is_wrap(label, wrap_name)]
        if wraps and len(kept) > len(wraps):
            kept = [label for label in kept if label not in wraps]
        if len(kept) != len(names):
            # Not every node the extraction named wrote a group carrying faces.  Two very
            # different things look like that: a node with no faces of its own (the
            # packaging 3D-Coat wraps the last import in - it goes from the file), and a
            # merge, where a node that does own faces lost its group (refused, because a
            # merged model cannot carry a material per object).
            #
            # Asking the mesh which object each face belongs to is the only way to tell
            # them apart, and the only call for it is per face - so it is asked *after*
            # the packaging nodes are taken out of the question, which is the usual
            # reason for the mismatch.  A mismatch that is only packaging costs nothing;
            # a real one costs one scan that stops at the first face it finds, and a
            # model too large to finish that scan inside the budget is refused rather
            # than waved through.
            unaccounted = [label for label in names
                           if label not in kept and not _is_wrap(label, wrap_name)]
            if unaccounted:
                owned = set()
                budget = FACE_SCAN_BUDGET
                scanned = 0
                try:
                    count = mesh.facesCount()
                    while scanned < count and scanned < budget:
                        which = mesh.getFaceObject(scanned)
                        scanned += 1
                        if 0 <= which < len(names):
                            owned.add(names[which])
                            if not owned.issubset(set(kept)):
                                break
                except Exception:
                    owned = set()
                    scanned = budget
                if owned and not owned.issubset(set(kept)):
                    raise RuntimeError('OBJ lost object groups; refusing a merged subtree export')
                if scanned >= budget and scanned < mesh.facesCount():
                    raise RuntimeError(
                        'model too large to check the lost object groups; export cancelled')
        gone = [label for label in order if label not in kept]
        if gone:
            _drop_groups(temporary, {label.lower() for label in gone})
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return kept, mesh.facesCount(), len(chosen)
