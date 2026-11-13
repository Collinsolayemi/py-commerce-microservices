"""Verify the local storefront gateway against an actual local HTTP upstream."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from frontend.server import StorefrontHandler


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/orders/denied':
            data = b'{"detail":"Token expired"}'
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Bearer')
        else:
            data = json.dumps({'path': self.path, 'authorization': self.headers.get('Authorization')}).encode()
            self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.send_response(201)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class QuietStorefront(StorefrontHandler):
    def log_message(self, *args):
        pass


class TestStorefrontProxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        cls.storefront = ThreadingHTTPServer(('127.0.0.1', 0), QuietStorefront)
        cls.base = f'http://127.0.0.1:{cls.storefront.server_port}'
        address = f'http://127.0.0.1:{cls.upstream.server_port}'
        cls.patcher = patch('frontend.server.SERVICES', {name: address for name in ('users', 'products', 'orders')})
        cls.patcher.start()
        cls.threads = []
        for server in (cls.upstream, cls.storefront):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.storefront, cls.upstream):
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=2)
        cls.patcher.stop()

    def test_serves_storefront_and_assets(self):
        with urlopen(self.base) as response:
            self.assertIn(b'Everyday,', response.read())
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        with urlopen(self.base + '/assets/chair.svg') as response:
            self.assertIn(b'<svg', response.read())

    def test_does_not_serve_configuration_source_or_tests(self):
        for path in ('/server.py', '/package.json', '/.env', '/tests/store.test.js', '/assets/../server.py'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + path)
            self.assertEqual(caught.exception.code, 404)

    def test_forwards_authentication_and_query_parameters(self):
        request = Request(self.base + '/api/orders?skip=2&limit=10', headers={'Authorization': 'Bearer signed-token'})
        with urlopen(request) as response:
            data = json.load(response)
        self.assertEqual(data, {'path': '/orders?skip=2&limit=10', 'authorization': 'Bearer signed-token'})

    def test_forwards_creation_body_and_status(self):
        payload = b'{"items":[{"product_id":"p1","quantity":2,"unit_price":89}]}'
        request = Request(self.base + '/api/orders', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request) as response:
            self.assertEqual(response.status, 201)
            self.assertEqual(response.read(), payload)

    def test_preserves_upstream_errors_and_authentication_challenge(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/api/orders/denied')
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(caught.exception.headers['WWW-Authenticate'], 'Bearer')
        self.assertEqual(json.load(caught.exception), {'detail': 'Token expired'})

    def test_unknown_api_routes_are_not_proxied(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + '/api/secrets')
        self.assertEqual(caught.exception.code, 404)

    def test_offline_services_return_a_json_error(self):
        with patch('frontend.server.SERVICES', {'products': 'http://127.0.0.1:1'}):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + '/api/products')
            self.assertEqual(caught.exception.code, 502)
            self.assertIn('unavailable', json.load(caught.exception)['detail'])
