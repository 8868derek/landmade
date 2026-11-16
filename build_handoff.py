"""Export source and current content without local credentials or machine binaries."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def references(value):
    found = set()
    if isinstance(value, str) and value.startswith(('/uploads/', '/assets/')):
        found.add(value)
    elif isinstance(value, list):
        for item in value:
            found.update(references(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.update(references(key))
            found.update(references(item))
    return found


def build(output_folder):
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now().astimezone()
    destination = output_folder / ('LANDMADE-网站交接-' + now.strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    members = {}
    prefix = 'landmade-local/'
    docs = ['上线交接说明.md', '后台操作指南.md', '图片压缩说明.md', '浏览器兼容说明.md']
    for file in list(ROOT.glob('*.py')) + list(ROOT.glob('check_*.js')) + list(ROOT.glob('requirements*.txt')) + list(ROOT.glob('*.command')) + [ROOT / name for name in docs]:
        if file.is_file():
            members[file.name] = file
    for file in (ROOT / 'static').rglob('*'):
        if file.is_file() and not any(part.startswith('.') or part == '__pycache__' for part in file.relative_to(ROOT / 'static').parts):
            members[file.relative_to(ROOT).as_posix()] = file

    with tempfile.TemporaryDirectory(prefix='landmade-handoff-') as folder:
        snapshot = Path(folder) / 'catalog.sqlite3'
        with sqlite3.connect(ROOT / 'data/catalog.sqlite3') as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        with sqlite3.connect(snapshot) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed')
            catalog = json.loads(db.execute('SELECT body FROM catalog WHERE id=1').fetchone()[0])
        members['data/catalog.sqlite3'] = snapshot
        uploads = {file.name: file for file in (ROOT / 'data/uploads').iterdir() if file.is_file() and not file.name.startswith('.')}
        for name, file in uploads.items():
            members['data/uploads/' + name] = file
        for ref in references(catalog):
            relative = 'data' + ref if ref.startswith('/uploads/') else 'static' + ref
            if relative not in members:
                raise ValueError('Missing referenced media: ' + ref)

        manifest_path = ROOT / 'data/optimized/manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'version': 1, 'files': {}}
        selected = {}
        for original, entry in manifest.get('files', {}).items():
            if original.removeprefix('/uploads/') not in uploads:
                continue
            valid = True
            for variant in entry.get('variants', {}).values():
                relative = 'data' + variant['url']
                file = (ROOT / relative).resolve()
                if not file.is_relative_to((ROOT / 'data/optimized').resolve()) or not file.is_file():
                    valid = False
                    break
            if valid:
                selected[original] = entry
                for variant in entry['variants'].values():
                    members['data' + variant['url']] = ROOT / ('data' + variant['url'])
        manifest['files'] = selected
        summary = {
            'snapshotAt': now.isoformat(),
            'products': len(catalog['products']),
            'publishedProducts': sum(bool(p.get('published')) for p in catalog['products']),
            'categories': len(catalog['categories']),
            'uploadedFiles': len(uploads),
            'uploadedBytes': sum(file.stat().st_size for file in uploads.values()),
            'optimizedImages': len(selected),
            'referencedMediaVerified': len(references(catalog)),
            'databaseIntegrity': 'ok',
            'credentialsIncluded': False,
            'machineDependenciesIncluded': False,
            'excluded': ['data/auth.json', 'data/sharing.json', 'image_tools/', 'old snapshots', 'debug screenshots'],
            'productionReady': False,
            'readFirst': '上线交接说明.md',
        }
        handle, temporary = tempfile.mkstemp(prefix='.landmade-package-', suffix='.zip', dir=output_folder)
        os.close(handle)
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for relative, file in sorted(members.items()):
                    kind = zipfile.ZIP_DEFLATED if file.suffix.lower() in ('.py', '.js', '.css', '.html', '.json', '.md', '.txt', '.command', '.sqlite3') else zipfile.ZIP_STORED
                    archive.write(file, prefix + relative, compress_type=kind)
                archive.writestr(prefix + 'data/catalog-export.json', json.dumps(catalog, ensure_ascii=False, indent=2), compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr(prefix + 'data/optimized/manifest.json', json.dumps(manifest, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
                archive.writestr(prefix + '交接清单.json', json.dumps(summary, ensure_ascii=False, indent=2), compress_type=zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(temporary) as archive:
                failed = archive.testzip()
                if failed:
                    raise ValueError('ZIP integrity check failed: ' + failed)
                names = set(archive.namelist())
                if any(name.endswith(('/auth.json', '/sharing.json')) for name in names):
                    raise ValueError('Local credential configuration must not be exported')
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    digest = hashlib.sha256()
    with destination.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    destination.with_suffix('.sha256.txt').write_text(digest.hexdigest() + '  ' + destination.name + '\n', encoding='utf-8')
    print(json.dumps({'package': str(destination), 'bytes': destination.stat().st_size, 'sha256': digest.hexdigest(), **summary}, ensure_ascii=False, indent=2))
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-folder', type=Path, default=ROOT.parent)
    build(parser.parse_args().output_folder)
