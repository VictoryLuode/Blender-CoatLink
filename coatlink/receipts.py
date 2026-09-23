"""File-version receipts. Only receivers write acknowledgements after success."""
import hashlib
import json
import os
import time


_hash_cache = {}


def fingerprint(path):
    stat = os.stat(path)
    key = (os.path.realpath(path), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
    if key in _hash_cache:
        return dict(_hash_cache[key])
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    stat = os.stat(path)
    result = {'sha256': digest.hexdigest(), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
    if len(_hash_cache) > 64:
        _hash_cache.clear()
    _hash_cache[key] = result
    return dict(result)


def acknowledge(path, receiver, version, names):
    if not names or fingerprint(path) != version:
        return False
    target = path + '.receipt.json'
    temporary = target + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump({'receiver': receiver, 'version': version,
                   'objects': list(names), 'received_at': time.time()}, stream)
    os.replace(temporary, target)
    return True


def received(path, receiver):
    try:
        with open(path + '.receipt.json', encoding='utf-8') as stream:
            data = json.load(stream)
        if data.get('receiver') == receiver and data.get('objects') and data.get('version') == fingerprint(path):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return None
