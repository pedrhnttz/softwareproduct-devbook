import io

from avatars import is_valid_stored_avatar_filename
from db import db
from models import Comment, Post, User

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


def _register(client, name, mail='user@example.com', password='secret'):
    return client.post(
        '/register',
        data={'nameForm': name, 'mailForm': mail, 'passwordForm': password},
        follow_redirects=True,
    )


def test_search_filters_by_body_and_author(app, client):
    _register(client, 'Ivy', 'ivy@example.com')
    client.post('/', data={'body': 'Aprendendo Flask hoje'}, follow_redirects=True)
    client.post('/', data={'body': 'Outro assunto qualquer'}, follow_redirects=True)

    other = app.test_client()
    _register(other, 'Jorge', 'jorge@example.com')
    other.post('/', data={'body': 'Mensagem do Jorge sobre Django'}, follow_redirects=True)

    # Filter by body content
    page = client.get('/?q=Flask').data.decode('utf-8')
    assert 'Aprendendo Flask hoje' in page
    assert 'Outro assunto qualquer' not in page
    assert 'Mensagem do Jorge sobre Django' not in page

    # Filter by author name
    page = client.get('/?q=Jorge').data.decode('utf-8')
    assert 'Mensagem do Jorge sobre Django' in page
    assert 'Aprendendo Flask hoje' not in page

    # No matches
    page = client.get('/?q=zzznotfound').data.decode('utf-8')
    assert 'Nenhuma publicação encontrada' in page


def test_user_portfolio_lists_only_that_users_posts(app, client):
    _register(client, 'Kira', 'kira@example.com')
    client.post('/', data={'body': 'Post da Kira'}, follow_redirects=True)

    other = app.test_client()
    _register(other, 'Leo', 'leo@example.com')
    other.post('/', data={'body': 'Post do Leo'}, follow_redirects=True)

    with app.app_context():
        kira = User.query.filter_by(mail='kira@example.com').first()
        kira_id = kira.id

    page = client.get(f'/user/{kira_id}')
    assert page.status_code == 200
    body = page.data.decode('utf-8')
    assert 'Kira' in body
    assert 'Post da Kira' in body
    assert 'Post do Leo' not in body


def test_user_portfolio_unknown_user_returns_404(client):
    _register(client, 'Mia', 'mia@example.com')
    assert client.get('/user/999999').status_code == 404


def test_home_renders_author_as_portfolio_link(app, client):
    _register(client, 'Nina', 'nina@example.com')
    client.post('/', data={'body': 'Olá mundo'}, follow_redirects=True)

    with app.app_context():
        nina_id = User.query.filter_by(mail='nina@example.com').first().id

    body = client.get('/').data.decode('utf-8')
    assert f'/user/{nina_id}' in body


def test_like_toggles_persistence(app, client):
    _register(client, 'Olivia', 'olivia@example.com')
    client.post('/', data={'body': 'Curte aí'}, follow_redirects=True)

    with app.app_context():
        post_id = Post.query.first().id
        assert db.session.get(Post, post_id).like_count == 0

    other = app.test_client()
    _register(other, 'Pedro', 'pedro@example.com')

    # First click: like is added
    other.post(f'/post/{post_id}/like', follow_redirects=False)
    with app.app_context():
        post = db.session.get(Post, post_id)
        assert post.like_count == 1
        liker = User.query.filter_by(mail='pedro@example.com').first()
        assert liker in post.liked_by

    # Second click: like is removed (toggle)
    other.post(f'/post/{post_id}/like', follow_redirects=False)
    with app.app_context():
        post = db.session.get(Post, post_id)
        assert post.like_count == 0


def test_like_requires_login(client):
    response = client.post('/post/1/like', follow_redirects=False)
    assert response.status_code == 302
    assert '/landing' in response.location


def test_like_unknown_post_returns_404(client):
    _register(client, 'Quentin', 'quentin@example.com')
    assert client.post('/post/999999/like').status_code == 404


def test_share_creates_repost_with_parent_id(app, client):
    _register(client, 'Rita', 'rita@example.com')
    client.post('/', data={'body': 'Publicação original da Rita'}, follow_redirects=True)

    with app.app_context():
        original = Post.query.first()
        original_id = original.id
        original_author_id = original.author_id

    other = app.test_client()
    _register(other, 'Sam', 'sam@example.com')

    other.post(
        f'/post/{original_id}/share',
        data={'body': 'Vejam isso!'},
        follow_redirects=False,
    )

    with app.app_context():
        sam = User.query.filter_by(mail='sam@example.com').first()
        repost = Post.query.filter_by(author_id=sam.id).first()
        assert repost is not None
        assert repost.parent_id == original_id
        assert repost.body == 'Vejam isso!'
        # Author of the parent is preserved
        assert repost.parent.author_id == original_author_id


def test_share_without_comment_is_allowed(app, client):
    _register(client, 'Tina', 'tina@example.com')
    client.post('/', data={'body': 'Texto da Tina'}, follow_redirects=True)

    with app.app_context():
        original_id = Post.query.first().id

    other = app.test_client()
    _register(other, 'Ugo', 'ugo@example.com')
    other.post(f'/post/{original_id}/share', data={'body': '   '}, follow_redirects=False)

    with app.app_context():
        ugo = User.query.filter_by(mail='ugo@example.com').first()
        repost = Post.query.filter_by(author_id=ugo.id).first()
        assert repost is not None
        assert repost.parent_id == original_id
        assert repost.body == ''


def test_share_of_share_flattens_to_original(app, client):
    _register(client, 'Vera', 'vera@example.com')
    client.post('/', data={'body': 'Origem'}, follow_redirects=True)

    with app.app_context():
        original_id = Post.query.first().id

    sharer = app.test_client()
    _register(sharer, 'Will', 'will@example.com')
    sharer.post(f'/post/{original_id}/share', data={'body': 'Compartilhando'}, follow_redirects=False)

    with app.app_context():
        will = User.query.filter_by(mail='will@example.com').first()
        repost_id = Post.query.filter_by(author_id=will.id).first().id

    re_sharer = app.test_client()
    _register(re_sharer, 'Xena', 'xena@example.com')
    re_sharer.post(f'/post/{repost_id}/share', follow_redirects=False)

    with app.app_context():
        xena = User.query.filter_by(mail='xena@example.com').first()
        re_repost = Post.query.filter_by(author_id=xena.id).first()
        assert re_repost.parent_id == original_id


def test_share_renders_in_feed_with_original_author_label(app, client):
    _register(client, 'Yara', 'yara@example.com')
    client.post('/', data={'body': 'Texto original'}, follow_redirects=True)

    with app.app_context():
        original_id = Post.query.first().id

    other = app.test_client()
    _register(other, 'Zac', 'zac@example.com')
    other.post(f'/post/{original_id}/share', data={'body': 'Olha só'}, follow_redirects=False)

    body = other.get('/').data.decode('utf-8')
    assert 'Partilhou uma publicação de' in body
    assert 'Yara' in body
    assert 'Texto original' in body


def test_user_can_comment_on_post(app, client):
    _register(client, 'Anna', 'anna@example.com')
    client.post('/', data={'body': 'Post para comentar'}, follow_redirects=True)

    with app.app_context():
        post_id = Post.query.first().id

    other = app.test_client()
    _register(other, 'Bruno', 'bruno@example.com')
    other.post(
        f'/post/{post_id}/comment',
        data={'body': 'Excelente publicação!'},
        follow_redirects=False,
    )

    with app.app_context():
        post = db.session.get(Post, post_id)
        assert post.comment_count == 1
        comment = post.comments[0]
        assert comment.body == 'Excelente publicação!'
        assert comment.author.name == 'Bruno'


def test_empty_comment_is_not_persisted(app, client):
    _register(client, 'Cris', 'cris@example.com')
    client.post('/', data={'body': 'Post da Cris'}, follow_redirects=True)

    with app.app_context():
        post_id = Post.query.first().id

    client.post(f'/post/{post_id}/comment', data={'body': '   '}, follow_redirects=False)

    with app.app_context():
        assert Comment.query.count() == 0
        assert db.session.get(Post, post_id).comment_count == 0


def test_comment_count_matches_multiple_comments(app, client):
    _register(client, 'Dora', 'dora@example.com')
    client.post('/', data={'body': 'Várias respostas'}, follow_redirects=True)

    with app.app_context():
        post_id = Post.query.first().id

    other = app.test_client()
    _register(other, 'Eli', 'eli@example.com')
    other.post(f'/post/{post_id}/comment', data={'body': 'Primeiro'}, follow_redirects=False)
    other.post(f'/post/{post_id}/comment', data={'body': 'Segundo'}, follow_redirects=False)
    client.post(f'/post/{post_id}/comment', data={'body': 'Terceiro'}, follow_redirects=False)

    with app.app_context():
        post = db.session.get(Post, post_id)
        assert post.comment_count == 3

    body = client.get('/').data.decode('utf-8')
    assert 'Primeiro' in body
    assert 'Segundo' in body
    assert 'Terceiro' in body


def test_comment_on_unknown_post_returns_404(client):
    _register(client, 'Fabio', 'fabio@example.com')
    assert client.post('/post/999999/comment', data={'body': 'x'}).status_code == 404


def test_comment_requires_login(client):
    response = client.post('/post/1/comment', data={'body': 'x'}, follow_redirects=False)
    assert response.status_code == 302
    assert '/landing' in response.location


def test_follow_and_unfollow_toggle(app, client):
    _register(client, 'Gina', 'gina@example.com')
    other = app.test_client()
    _register(other, 'Hugo', 'hugo@example.com')

    with app.app_context():
        gina = User.query.filter_by(mail='gina@example.com').first()
        hugo = User.query.filter_by(mail='hugo@example.com').first()
        gina_id, hugo_id = gina.id, hugo.id
        assert not gina.is_following(hugo)

    # First click: follow
    client.post(f'/user/{hugo_id}/follow', follow_redirects=False)
    with app.app_context():
        gina = db.session.get(User, gina_id)
        hugo = db.session.get(User, hugo_id)
        assert gina.is_following(hugo)
        assert hugo.followers_count == 1
        assert gina.following_count == 1

    # Second click: unfollow
    client.post(f'/user/{hugo_id}/follow', follow_redirects=False)
    with app.app_context():
        gina = db.session.get(User, gina_id)
        hugo = db.session.get(User, hugo_id)
        assert not gina.is_following(hugo)
        assert hugo.followers_count == 0
        assert gina.following_count == 0


def test_cannot_follow_self(app, client):
    _register(client, 'Iris', 'iris@example.com')
    with app.app_context():
        iris_id = User.query.filter_by(mail='iris@example.com').first().id

    response = client.post(f'/user/{iris_id}/follow', follow_redirects=False)
    assert response.status_code == 400

    with app.app_context():
        iris = db.session.get(User, iris_id)
        assert iris.followers_count == 0
        assert iris.following_count == 0


def test_follow_unknown_user_returns_404(client):
    _register(client, 'Joao', 'joao@example.com')
    assert client.post('/user/999999/follow').status_code == 404


def test_follow_requires_login(client):
    response = client.post('/user/1/follow', follow_redirects=False)
    assert response.status_code == 302
    assert '/landing' in response.location


def test_following_feed_filters_posts(app, client):
    _register(client, 'Karen', 'karen@example.com')

    bob = app.test_client()
    _register(bob, 'Bob', 'bob_feed@example.com')
    bob.post('/', data={'body': 'Publicação do Bob'}, follow_redirects=True)

    carol = app.test_client()
    _register(carol, 'Carol', 'carol_feed@example.com')
    carol.post('/', data={'body': 'Publicação da Carol'}, follow_redirects=True)

    with app.app_context():
        bob_id = User.query.filter_by(mail='bob_feed@example.com').first().id

    # Karen follows only Bob
    client.post(f'/user/{bob_id}/follow', follow_redirects=False)

    # Global feed sees both posts
    global_body = client.get('/').data.decode('utf-8')
    assert 'Publicação do Bob' in global_body
    assert 'Publicação da Carol' in global_body

    # Following feed sees only Bob's post
    following_body = client.get('/?feed=following').data.decode('utf-8')
    assert 'Publicação do Bob' in following_body
    assert 'Publicação da Carol' not in following_body


def test_following_feed_empty_when_following_nobody(app, client):
    _register(client, 'Lara', 'lara@example.com')

    other = app.test_client()
    _register(other, 'Mauro', 'mauro@example.com')
    other.post('/', data={'body': 'Texto do Mauro'}, follow_redirects=True)

    body = client.get('/?feed=following').data.decode('utf-8')
    assert 'Texto do Mauro' not in body
    assert 'ainda não segue ninguém' in body


def test_portfolio_shows_follow_button_for_other_user(app, client):
    _register(client, 'Nora', 'nora@example.com')
    other = app.test_client()
    _register(other, 'Otto', 'otto@example.com')

    with app.app_context():
        otto_id = User.query.filter_by(mail='otto@example.com').first().id

    page = client.get(f'/user/{otto_id}').data.decode('utf-8')
    assert 'Seguir' in page
    assert f'/user/{otto_id}/follow' in page


def test_portfolio_hides_follow_button_for_own_profile(app, client):
    _register(client, 'Paula', 'paula@example.com')
    with app.app_context():
        paula_id = User.query.filter_by(mail='paula@example.com').first().id

    page = client.get(f'/user/{paula_id}').data.decode('utf-8')
    assert f'/user/{paula_id}/follow' not in page


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
