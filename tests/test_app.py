import io

from avatars import is_valid_stored_avatar_filename
from db import db
from models import Post, User

MINI_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


def test_home_redirects_when_anonymous(client):
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert '/landing' in response.location


def test_register_login_and_feed(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'Alice',
            'mailForm': 'alice@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )

    client.post('/', data={'body': 'Primeira publicação da Alice'}, follow_redirects=True)

    other = app.test_client()
    other.post(
        '/register',
        data={
            'nameForm': 'Bob',
            'mailForm': 'bob@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )

    feed = other.get('/')
    assert feed.status_code == 200
    body = feed.data.decode('utf-8')
    assert 'Primeira publicação da Alice' in body
    assert 'Alice' in body


def test_empty_post_is_not_persisted(app, client):
    with app.app_context():
        assert Post.query.count() == 0

    client.post(
        '/register',
        data={
            'nameForm': 'Carol',
            'mailForm': 'carol@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    client.post('/', data={'body': '   '}, follow_redirects=True)

    with app.app_context():
        assert Post.query.count() == 0


def test_logout_goes_to_landing(client):
    client.post(
        '/register',
        data={
            'nameForm': 'Dan',
            'mailForm': 'dan@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    response = client.get('/logout', follow_redirects=False)
    assert response.status_code == 302
    assert '/landing' in response.location


def test_login_failure_message(client):
    response = client.post(
        '/login',
        data={'mailForm': 'nope@example.com', 'passwordForm': 'wrong'},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert 'incorretos' in response.data.decode('utf-8')


def test_author_can_edit_own_post(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'Eve',
            'mailForm': 'eve@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    client.post('/', data={'body': 'Texto original'}, follow_redirects=True)

    with app.app_context():
        post = Post.query.first()
        post_id = post.id

    page = client.get(f'/post/{post_id}/edit')
    assert page.status_code == 200
    assert 'Texto original' in page.data.decode('utf-8')

    client.post(
        f'/post/{post_id}/edit',
        data={'body': 'Texto atualizado'},
        follow_redirects=True,
    )

    with app.app_context():
        updated = db.session.get(Post, post_id)
        assert updated.body == 'Texto atualizado'


def test_non_author_cannot_edit_post(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'Frank',
            'mailForm': 'frank@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    client.post('/', data={'body': 'Do Frank'}, follow_redirects=True)

    with app.app_context():
        post_id = Post.query.first().id

    intruder = app.test_client()
    intruder.post(
        '/register',
        data={
            'nameForm': 'Grace',
            'mailForm': 'grace@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )

    assert intruder.get(f'/post/{post_id}/edit').status_code == 403
    assert (
        intruder.post(
            f'/post/{post_id}/edit',
            data={'body': 'Tentativa'},
            follow_redirects=False,
        ).status_code
        == 403
    )

    with app.app_context():
        assert db.session.get(Post, post_id).body == 'Do Frank'


def test_edit_unknown_post_returns_404(client):
    client.post(
        '/register',
        data={
            'nameForm': 'Helen',
            'mailForm': 'helen@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    assert client.get('/post/999999/edit').status_code == 404


def test_register_invalid_avatar_ignored(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'Y',
            'mailForm': 'y@test.com',
            'passwordForm': 'p',
            'avatarForm': (io.BytesIO(b'not-an-image'), 'bad.txt'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    with app.app_context():
        user = User.query.filter_by(mail='y@test.com').first()
        assert user.avatar_filename is None


def test_register_with_avatar_visible_in_feed_and_media(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'AvatarUser',
            'mailForm': 'avatarfeed@example.com',
            'passwordForm': 'secret',
            'avatarForm': (io.BytesIO(MINI_PNG), 'face.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    client.post('/', data={'body': 'Olá com foto'}, follow_redirects=True)

    page = client.get('/').data.decode('utf-8')
    assert '/media/avatars/' in page

    with app.app_context():
        fn = User.query.filter_by(mail='avatarfeed@example.com').first().avatar_filename

    assert is_valid_stored_avatar_filename(fn)
    media = client.get(f'/media/avatars/{fn}')
    assert media.status_code == 200


def test_profile_updates_avatar(app, client):
    client.post(
        '/register',
        data={
            'nameForm': 'Ann',
            'mailForm': 'ann@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert User.query.filter_by(mail='ann@example.com').first().avatar_filename is None

    client.post(
        '/profile',
        data={
            'nameForm': 'Ann',
            'mailForm': 'ann@example.com',
            'passwordForm': 'secret',
            'avatarForm': (io.BytesIO(MINI_PNG), 'new.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    with app.app_context():
        assert User.query.filter_by(mail='ann@example.com').first().avatar_filename


def test_malicious_avatar_path_returns_404(client):
    client.post(
        '/register',
        data={
            'nameForm': 'Sec',
            'mailForm': 'sec@example.com',
            'passwordForm': 'secret',
        },
        follow_redirects=True,
    )
    assert client.get('/media/avatars/foo.png').status_code == 404
    assert client.get('/media/avatars/../database.db').status_code == 404
