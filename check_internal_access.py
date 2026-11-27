"""Exercise the public and internal scopes over HTTP using disposable credentials."""
import json
import secrets
import sqlite3
import tempfile
import threading
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import server


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


def make_product(pid, cover, stage, extra=(), published=True):
    return {
        'id': pid, 'en': pid, 'zh': pid, 'category': 'gifts', 'cover': cover,
        'images': [cover, *extra], 'imageStatuses': {cover: stage} if stage else {},
        'published': published, 'created': 0,
    }


def verify():
    with tempfile.TemporaryDirectory(prefix='landmade-internal-test-') as folder:
        root = Path(folder)
        server.ROOT = root
        server.DATA = root / 'data'
        server.DB = server.DATA / 'catalog.sqlite3'
        server.UP = server.DATA / 'uploads'
        server.AUTH_FILE = server.DATA / 'auth.json'
        assets = root / 'static' / 'assets'
        optimized = server.DATA / 'optimized'
        for directory in (server.UP, assets, optimized):
            directory.mkdir(parents=True)
        for directory, names in (
            (server.UP, ('public.png', 'listed.png', 'private.png', 'private.mp4', 'untagged.png', 'draft.png')),
            (assets, ('logo.png', 'private-static.png')),
            (optimized, ('public.webp', 'private.webp')),
        ):
            for name in names:
                (directory / name).write_bytes(b'test fixture')
        (optimized / 'manifest.json').write_text(json.dumps({'files': {
            '/uploads/public.png': {'variants': {'card': {'url': '/optimized/public.webp'}}},
            '/uploads/private.png': {'variants': {'card': {'url': '/optimized/private.webp'}}},
        }}))
        making = make_product('making', '/uploads/public.png', 'making')
        listed = make_product('listed', '/uploads/listed.png', 'listed')
        design = make_product('design', '/uploads/private.png', 'design', ('/uploads/private.mp4', '/assets/private-static.png'))
        untagged = make_product('untagged', '/uploads/untagged.png', '')
        draft = make_product('draft', '/uploads/draft.png', 'listed', published=False)
        ids = ['design', 'making', 'listed', 'untagged', 'draft']
        catalog = {
            'categories': [
                {'id': 'gifts', 'en': 'Gifts', 'zh': '商务礼赠', 'hero': design['cover'],
                 'heroMode': 'custom', 'productOrder': ids},
            ],
            'products': [making, listed, design, untagged, draft],
            'settings': {
                'slides': [
                    {'product': 'design', 'image': design['cover'], 'title': 'Private banner'},
                    {'product': 'making', 'image': design['cover'], 'title': 'Private image on another slide'},
                    {'product': 'listed', 'image': listed['cover'], 'title': 'Public banner'},
                ],
                'newArrivals': ['design', 'listed'],
                'homeCollectionOrder': ids,
            },
        }
        with sqlite3.connect(server.DB) as db:
            db.execute('CREATE TABLE catalog(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('INSERT INTO catalog VALUES(1,?)', (json.dumps(catalog),))
        admin_password = secrets.token_urlsafe(20)
        password = secrets.token_hex(3)
        new_password = secrets.token_hex(3)
        while new_password == password:
            new_password = secrets.token_hex(3)
        server.write_auth(server.secret_record(admin_password))

        http = server.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:' + str(http.server_port)
        guest, internal, admin = [
            build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
            for _ in range(3)
        ]

        def request(path, payload=None, client=guest, method=None, **headers):
            body = None if payload is None else json.dumps(payload).encode()
            headers = {'X-Landmade': 'local', 'Content-Type': 'application/json', 'Origin': url, **headers}
            req = Request(url + path, body, headers, method=method)
            try:
                with client.open(req, timeout=5) as response:
                    return response.status, response.read(), response.headers
            except HTTPError as error:
                return error.code, error.read(), error.headers

        def state(client=guest):
            status, body, headers = request('/api/state', client=client)
            assert status == 200 and 'no-store' in headers['Cache-Control']
            return json.loads(body)

        def set_password(value, client=admin):
            return request('/api/auth/internal/settings', {'newPassword': value, 'confirmPassword': value}, client)

        try:
            public = state()
            assert not public['_internal']
            assert {p['id'] for p in public['products']} == {'making', 'listed'}
            assert public['categories'][0]['hero'] == ''
            assert public['categories'][0]['productOrder'] == ['making', 'listed']
            assert [s['title'] for s in public['settings']['slides']] == ['Public banner']
            assert public['settings']['newArrivals'] == ['listed', 'making']
            assert server.read_state()['settings']['newArrivals'] == ['design', 'listed']
            recent = dict(listed, id='recent', created=100)
            sample = dict(catalog, products=[*catalog['products'], recent])
            assert server.browsing_catalog(sample)['settings']['newArrivals'] == ['listed', 'recent', 'making']
            sample['settings'] = dict(catalog['settings'], newArrivals=['design'])
            assert server.browsing_catalog(sample)['settings']['newArrivals'] == ['recent', 'making', 'listed']
            sample['settings']['newArrivals'] = []
            assert server.browsing_catalog(sample)['settings']['newArrivals'] == []
            assert public['settings']['homeCollectionOrder'] == ['making', 'listed']
            assert set(public['mediaVariants']) == {'/uploads/public.png'}
            public_image = request('/uploads/public.png')
            assert public_image[0] == 200 and 'no-cache' in public_image[2]['Cache-Control']
            assert request('/optimized/public.webp')[0] == 200
            private_paths = (*design['images'], '/optimized/private.webp', untagged['cover'])
            for path in private_paths:
                assert request(path)[0] == request(path, method='HEAD')[0] == 404
            assert request('/uploads/private.mp4', Range='bytes=0-3')[0] == 404
            assert request('/api/auth/internal/login', {'password': password}, internal)[0] == 403
            assert set_password(password, guest)[0] == 401
            assert request('/api/auth/login', {'password': admin_password}, admin)[0] == 200
            assert set_password(admin_password)[0] == 400
            assert set_password(password[:5])[0] == 400
            assert set_password(password)[0] == 200
            assert password not in server.AUTH_FILE.read_text()

            assert request('/api/auth/internal/login', {'password': 'wrong-password'}, internal)[0] == 401
            result = request('/api/auth/internal/login', {'password': password}, internal)
            assert result[0] == 200 and 'HttpOnly' in result[2]['Set-Cookie'] and 'SameSite=Strict' in result[2]['Set-Cookie']
            full = state(internal)
            assert full['_internal'] and {p['id'] for p in full['products']} == {'making', 'listed', 'design', 'untagged'}
            assert full['settings']['newArrivals'] == ['design', 'listed']
            for path in private_paths:
                status, _, headers = request(path, client=internal)
                assert status == 200 and 'no-store' in headers['Cache-Control']
                assert request(path)[0] == 404
            assert request('/uploads/private.mp4', client=internal, Range='bytes=0-3')[:2] == (206, b'test')
            assert request(draft['cover'], client=internal)[0] == 404
            assert request('/api/state?admin=1', client=internal)[0] == 401
            assert request('/api/backup', client=internal)[0] == 401
            assert request('/api/upload', {}, internal)[0] == 401

            # Images are rechecked if the corresponding product is moved to design.
            making['imageStatuses'][making['cover']] = 'design'
            server.save_state(catalog)
            assert request(making['cover'], **{'If-None-Match': public_image[2]['ETag']})[0] == 404
            assert request(making['cover'], client=internal)[0] == 200
            assert request('/api/auth/internal/logout', {}, internal)[0] == 200
            assert not state(internal)['_internal']
            assert request(design['cover'], client=internal)[0] == 404

            assert request('/api/auth/internal/login', {'password': password}, internal)[0] == 200
            assert set_password(new_password)[0] == 200
            assert not state(internal)['_internal']
            assert request('/api/auth/internal/login', {'password': password}, internal)[0] == 401
            assert request('/api/auth/internal/login', {'password': new_password}, internal)[0] == 200
            assert request('/api/auth/session', client=admin)[0] == 200
        finally:
            http.shutdown()
            http.server_close()


if __name__ == '__main__':
    verify()
    print('PASS: scoped catalog and banners, protected original and optimized media, role separation, logout and password rotation.')
