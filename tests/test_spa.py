from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.spa import SPAFiles


def test_direct_navigation_and_missing_resources(tmp_path):
    (tmp_path / 'index.html').write_text('<html>release shell</html>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app.js').write_text('window.loaded=true;')
    app = FastAPI()
    app.mount('/', SPAFiles(directory=str(tmp_path), html=True))
    client = TestClient(app)
    for path in ('/', '/buyers', '/buyer-sms', '/buyer-sms/privacy',
                 '/buyer-sms/terms', '/form/fresh-inquiry', '/admin/users'):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == '<html>release shell</html>'
        assert client.head(path).status_code == 200
    assert client.get('/assets/app.js').text == 'window.loaded=true;'
    for path in ('/api/missing', '/webhooks/missing', '/v1/missing',
                 '/assets/missing', '/missing.js', '/assets/unknown.js',
                 '/nested/file.json/missing'):
        assert client.get(path).status_code == 404, path
    assert client.post('/buyer-sms/privacy').status_code == 405
