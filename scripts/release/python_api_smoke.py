"""Run through scripts/run_offline_tests.py in the API-only dependency environment."""
from importlib.metadata import version
from api.index import app
from fastapi.testclient import TestClient

# Importing api.index can return a fallback service if cold start failed. These
# route assertions prove the real app loaded, not simply that an ASGI name exists.
client = TestClient(app)
assert client.get('/api/health').status_code == 200
assert client.get('/api/buyers/leaderboard').status_code == 401
assert client.post('/api/buyers/import').status_code == 401
assert client.post('/api/buyers/manual', json={'request_id':'00000000-0000-4000-8000-000000000001',
    'buyer':{'first_name':'Synthetic','last_name':'Smoke'}}).status_code == 401
assert version('twilio') == '9.11.2'
assert client.get('/api/buyers/analysis/config').status_code==401
print('API-only cold-start, health, protected buyer routes and Twilio SDK: passed; no provider calls')
