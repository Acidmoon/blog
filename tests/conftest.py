import pytest
from app import create_app


@pytest.fixture(scope='session')
def app():
    """Create the Flask app for testing."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def login(client):
    """Log in and return the client with an active session."""
    client.post('/admin/login', data={'password': 'admin123'})
    return client
