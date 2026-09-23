"""Scoped sculpt export. No UI commands and no whole-scene fallback."""
import os
import tempfile


def export_subtree(coat, path, reduction=0):
    element = coat.Scene.current()
    if element is None:
        raise RuntimeError('Select a sculpt Tree node first')
    volume = element.Volume()
    mesh = coat.Mesh()
    percent = max(0.0, min(99.0, float(reduction)))
    if percent:
        mesh.fromReducedVolume(volume, percent, True, False)
    else:
        mesh.fromVolume(volume, True, False)
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
        groups = set()
        with open(temporary, encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if line.startswith('v '):
                    vertices += 1
                elif line.startswith('f '):
                    faces += 1
                elif line.startswith(('o ', 'g ')):
                    label = line[2:].strip()
                    if label:
                        groups.add(label)
        if not vertices or not faces:
            raise RuntimeError('Exported OBJ contains no geometry; previous return preserved')
        if len(names) > 1 and len(groups) < len(set(names)):
            raise RuntimeError('OBJ lost object groups; refusing a merged subtree export')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return names, mesh.facesCount()
