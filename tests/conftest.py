import os

import pytest

from app import create_app
from db import db


@pytest.fixture
def app():
    application = create_app(testing=True)
    upload = application.config['AVATAR_UPLOAD_FOLDER']
    os.makedirs(upload, exist_ok=True)
    with application.app_context():
        db.create_all()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()
    if os.path.isdir(upload):
        for name in os.listdir(upload):
            path = os.path.join(upload, name)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


@pytest.fixture
def client(app):
    return app.test_client()
