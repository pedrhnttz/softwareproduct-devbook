import os
from datetime import datetime, timezone

from flask import Flask, abort, render_template, request, redirect, url_for, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from sqlalchemy import inspect, or_, and_, text
from sqlalchemy.orm import joinedload

from avatars import delete_avatar_file, is_valid_stored_avatar_filename, save_avatar_file
from db import db
from models import (
    REACTION_EMOJI,
    REACTION_TYPES,
    Comment,
    Message,
    Notification,
    Post,
    Reaction,
    User,
)

lm = LoginManager()


def _ensure_sqlite_user_avatar_column(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users'):
        return
    cols = {c['name'] for c in inspector.get_columns('users')}
    if 'avatar_filename' in cols:
        return
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE users ADD COLUMN avatar_filename VARCHAR(255)'))
        conn.commit()


def _ensure_sqlite_post_parent_id_column(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('posts'):
        return
    cols = {c['name'] for c in inspector.get_columns('posts')}
    if 'parent_id' in cols:
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'ALTER TABLE posts ADD COLUMN parent_id INTEGER REFERENCES posts(id)'
        ))
        conn.commit()


def _ensure_sqlite_post_likes_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users') or not inspector.has_table('posts'):
        return
    if inspector.has_table('post_likes'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE post_likes ('
            'user_id INTEGER NOT NULL REFERENCES users(id), '
            'post_id INTEGER NOT NULL REFERENCES posts(id), '
            'PRIMARY KEY (user_id, post_id))'
        ))
        conn.commit()


def _ensure_sqlite_followers_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users'):
        return
    if inspector.has_table('followers'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE followers ('
            'follower_id INTEGER NOT NULL REFERENCES users(id), '
            'followed_id INTEGER NOT NULL REFERENCES users(id), '
            'PRIMARY KEY (follower_id, followed_id))'
        ))
        conn.commit()


def _ensure_sqlite_comments_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users') or not inspector.has_table('posts'):
        return
    if inspector.has_table('comments'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE comments ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'body TEXT NOT NULL, '
            'created_at DATETIME NOT NULL, '
            'author_id INTEGER NOT NULL REFERENCES users(id), '
            'post_id INTEGER NOT NULL REFERENCES posts(id))'
        ))
        conn.commit()


def _ensure_sqlite_reactions_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users') or not inspector.has_table('posts'):
        return
    if inspector.has_table('reactions'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE reactions ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'type VARCHAR(20) NOT NULL, '
            'created_at DATETIME NOT NULL, '
            'user_id INTEGER NOT NULL REFERENCES users(id), '
            'post_id INTEGER NOT NULL REFERENCES posts(id), '
            'UNIQUE (user_id, post_id))'
        ))
        # Preserva curtidas antigas migrando-as como reação "like".
        if inspector.has_table('post_likes'):
            now = datetime.now(timezone.utc).isoformat(sep=' ')
            conn.execute(
                text(
                    'INSERT INTO reactions (type, created_at, user_id, post_id) '
                    "SELECT 'like', :now, user_id, post_id FROM post_likes"
                ),
                {'now': now},
            )
        conn.commit()


def _ensure_sqlite_notifications_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users') or not inspector.has_table('posts'):
        return
    if inspector.has_table('notifications'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE notifications ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'type VARCHAR(20) NOT NULL, '
            'is_read BOOLEAN NOT NULL DEFAULT 0, '
            'created_at DATETIME NOT NULL, '
            'recipient_id INTEGER NOT NULL REFERENCES users(id), '
            'actor_id INTEGER NOT NULL REFERENCES users(id), '
            'post_id INTEGER REFERENCES posts(id))'
        ))
        conn.commit()


def _ensure_sqlite_messages_table(app: Flask) -> None:
    uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not uri.startswith('sqlite:'):
        return
    inspector = inspect(db.engine)
    if not inspector.has_table('users'):
        return
    if inspector.has_table('messages'):
        return
    with db.engine.connect() as conn:
        conn.execute(text(
            'CREATE TABLE messages ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'body TEXT NOT NULL, '
            'is_read BOOLEAN NOT NULL DEFAULT 0, '
            'created_at DATETIME NOT NULL, '
            'sender_id INTEGER NOT NULL REFERENCES users(id), '
            'recipient_id INTEGER NOT NULL REFERENCES users(id))'
        ))
        conn.commit()


def create_notification(recipient_id, actor_id, notif_type, post_id=None) -> None:
    """Cria uma notificação, ignorando ações do usuário sobre si mesmo."""
    if recipient_id is None or actor_id is None or recipient_id == actor_id:
        return
    notification = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=notif_type,
        post_id=post_id,
    )
    db.session.add(notification)


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.secret_key = 'secret_key'
    basedir = os.path.dirname(os.path.abspath(__file__))

    if testing:
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(
            basedir, 'instance', 'test_uploads', 'avatars'
        )
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
        app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(
            basedir, 'static', 'uploads', 'avatars'
        )

    app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

    db.init_app(app)
    lm.init_app(app)
    lm.login_view = 'landing'

    @lm.user_loader
    def user_loader(id):
        return db.session.query(User).filter_by(id=id).first()

    @app.template_filter('user_avatar_url')
    def user_avatar_url_filter(user):
        fn = getattr(user, 'avatar_filename', None) if user is not None else None
        if fn and is_valid_stored_avatar_filename(fn):
            return url_for('serve_avatar', filename=fn)
        return url_for('static', filename='images/default-avatar.svg')

    reaction_labels = {key: label for key, _, label in REACTION_TYPES}

    @app.template_filter('reaction_emoji')
    def reaction_emoji_filter(reaction_type):
        return REACTION_EMOJI.get(reaction_type, '👍')

    @app.template_filter('reaction_label')
    def reaction_label_filter(reaction_type):
        return reaction_labels.get(reaction_type, 'Curtir')

    @app.context_processor
    def inject_nav_counters():
        if not getattr(current_user, 'is_authenticated', False):
            return {}
        unread_messages = (
            db.session.query(Message)
            .filter(Message.recipient_id == current_user.id, Message.is_read == False)  # noqa: E712
            .count()
        )
        return {
            'unread_notifications': current_user.unread_notifications_count,
            'unread_messages': unread_messages,
            'reaction_types': REACTION_TYPES,
        }

    @app.route('/media/avatars/<filename>')
    def serve_avatar(filename):
        if not is_valid_stored_avatar_filename(filename):
            abort(404)
        folder = app.config['AVATAR_UPLOAD_FOLDER']
        return send_from_directory(folder, filename)

    @app.route('/', methods=['GET', 'POST'])
    @login_required
    def home():
        if request.method == 'POST':
            body = (request.form.get('body') or '').strip()
            if body:
                post = Post(body=body, author_id=current_user.id)
                db.session.add(post)
                db.session.commit()
            return redirect(url_for('home'))

        search_query = (request.args.get('q') or '').strip()
        feed_mode = (request.args.get('feed') or '').strip().lower()
        if feed_mode not in ('following', 'global'):
            feed_mode = 'global'

        posts_query = (
            Post.query.options(joinedload(Post.author), joinedload(Post.parent).joinedload(Post.author))
            .join(User, Post.author_id == User.id)
        )
        if feed_mode == 'following':
            following_ids = [u.id for u in current_user.following.all()]
            if following_ids:
                posts_query = posts_query.filter(Post.author_id.in_(following_ids))
            else:
                posts_query = posts_query.filter(db.false())
        if search_query:
            like = f'%{search_query}%'
            posts_query = posts_query.filter(
                or_(Post.body.ilike(like), User.name.ilike(like))
            )
        posts = posts_query.order_by(Post.created_at.desc()).all()
        return render_template(
            'home.html',
            posts=posts,
            search_query=search_query,
            feed_mode=feed_mode,
        )

    @app.route('/user/<int:user_id>')
    @login_required
    def user_portfolio(user_id):
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        posts = (
            Post.query.options(joinedload(Post.author), joinedload(Post.parent).joinedload(Post.author))
            .filter(Post.author_id == user.id)
            .order_by(Post.created_at.desc())
            .all()
        )
        return render_template('user_portfolio.html', portfolio_user=user, posts=posts)

    @app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_post(post_id):
        post = db.session.get(Post, post_id)
        if post is None:
            abort(404)
        if post.author_id != current_user.id:
            abort(403)

        if request.method == 'POST':
            body = (request.form.get('body') or '').strip()
            if body:
                post.body = body
                db.session.commit()
            return redirect(url_for('home'))

        return render_template('edit_post.html', post=post)

    def _apply_reaction(post, reaction_type):
        """Adiciona, troca ou remove (toggle) a reação do usuário atual no post.

        Retorna True se ao final existe uma reação (criada/trocada), False se removida.
        """
        existing = post.reaction_by(current_user)
        if existing is None:
            db.session.add(Reaction(
                user_id=current_user.id,
                post_id=post.id,
                type=reaction_type,
            ))
            return True
        if existing.type == reaction_type:
            # Clicar na mesma reação remove-a.
            db.session.delete(existing)
            return False
        existing.type = reaction_type
        return True

    @app.route('/post/<int:post_id>/like', methods=['POST'])
    @login_required
    def toggle_like(post_id):
        post = db.session.get(Post, post_id)
        if post is None:
            abort(404)
        reacted = _apply_reaction(post, 'like')
        if reacted:
            create_notification(post.author_id, current_user.id, 'reaction', post.id)
        db.session.commit()
        return redirect(request.referrer or url_for('home'))

    @app.route('/post/<int:post_id>/react', methods=['POST'])
    @login_required
    def react_post(post_id):
        post = db.session.get(Post, post_id)
        if post is None:
            abort(404)
        reaction_type = (request.form.get('type') or '').strip()
        if reaction_type not in REACTION_EMOJI:
            abort(400)
        reacted = _apply_reaction(post, reaction_type)
        if reacted:
            create_notification(post.author_id, current_user.id, 'reaction', post.id)
        db.session.commit()
        return redirect(request.referrer or url_for('home'))

    @app.route('/post/<int:post_id>/share', methods=['POST'])
    @login_required
    def share_post(post_id):
        original = db.session.get(Post, post_id)
        if original is None:
            abort(404)

        # If sharing an existing share, point to the underlying original.
        target = original.parent if original.parent_id else original

        comment = (request.form.get('body') or '').strip()
        repost = Post(body=comment, author_id=current_user.id, parent_id=target.id)
        db.session.add(repost)
        db.session.flush()
        create_notification(target.author_id, current_user.id, 'share', target.id)
        db.session.commit()
        return redirect(request.referrer or url_for('home'))

    @app.route('/post/<int:post_id>/comment', methods=['POST'])
    @login_required
    def add_comment(post_id):
        post = db.session.get(Post, post_id)
        if post is None:
            abort(404)
        body = (request.form.get('body') or '').strip()
        if body:
            comment = Comment(body=body, author_id=current_user.id, post_id=post.id)
            db.session.add(comment)
            create_notification(post.author_id, current_user.id, 'comment', post.id)
            db.session.commit()
        return redirect(request.referrer or url_for('home'))

    @app.route('/user/<int:user_id>/follow', methods=['POST'])
    @login_required
    def toggle_follow(user_id):
        target = db.session.get(User, user_id)
        if target is None:
            abort(404)
        if target.id == current_user.id:
            abort(400)
        if current_user.is_following(target):
            current_user.unfollow(target)
        else:
            current_user.follow(target)
            create_notification(target.id, current_user.id, 'follow')
        db.session.commit()
        return redirect(request.referrer or url_for('user_portfolio', user_id=target.id))

    @app.route('/notifications')
    @login_required
    def notifications():
        items = (
            current_user.notifications
            .options(joinedload(Notification.actor), joinedload(Notification.post))
            .all()
        )
        # Marca todas como lidas ao abrir a central.
        unread = [n for n in items if not n.is_read]
        for notification in unread:
            notification.is_read = True
        if unread:
            db.session.commit()
        return render_template('notifications.html', notifications=items)

    @app.route('/messages')
    @login_required
    def messages():
        sent = (
            db.session.query(Message)
            .filter(Message.sender_id == current_user.id)
            .all()
        )
        received = (
            db.session.query(Message)
            .filter(Message.recipient_id == current_user.id)
            .all()
        )

        # Agrupa por interlocutor, mantendo a última mensagem e contagem de não lidas.
        conversations = {}
        for message in sent + received:
            other_id = (
                message.recipient_id
                if message.sender_id == current_user.id
                else message.sender_id
            )
            entry = conversations.get(other_id)
            if entry is None:
                entry = {'last': message, 'unread': 0}
                conversations[other_id] = entry
            elif message.created_at > entry['last'].created_at:
                entry['last'] = message
            if message.recipient_id == current_user.id and not message.is_read:
                entry['unread'] += 1

        thread_list = []
        for other_id, data in conversations.items():
            other = db.session.get(User, other_id)
            if other is None:
                continue
            thread_list.append({
                'user': other,
                'last': data['last'],
                'unread': data['unread'],
            })
        thread_list.sort(key=lambda item: item['last'].created_at, reverse=True)

        return render_template('messages.html', conversations=thread_list)

    @app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
    @login_required
    def conversation(user_id):
        other = db.session.get(User, user_id)
        if other is None:
            abort(404)
        if other.id == current_user.id:
            abort(400)

        if request.method == 'POST':
            body = (request.form.get('body') or '').strip()
            if body:
                message = Message(
                    body=body,
                    sender_id=current_user.id,
                    recipient_id=other.id,
                )
                db.session.add(message)
                db.session.commit()
            return redirect(url_for('conversation', user_id=other.id))

        thread = (
            db.session.query(Message)
            .filter(
                or_(
                    and_(Message.sender_id == current_user.id, Message.recipient_id == other.id),
                    and_(Message.sender_id == other.id, Message.recipient_id == current_user.id),
                )
            )
            .order_by(Message.created_at.asc())
            .all()
        )

        # Marca como lidas as mensagens recebidas deste interlocutor.
        unread = [m for m in thread if m.recipient_id == current_user.id and not m.is_read]
        for message in unread:
            message.is_read = True
        if unread:
            db.session.commit()

        return render_template('conversation.html', other=other, thread=thread)

    @app.route('/landing')
    def landing():
        return render_template('landing.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            return render_template('login.html')
        mail = request.form['mailForm']
        password = request.form['passwordForm']

        user = db.session.query(User).filter_by(mail=mail, password=password).first()
        if not user:
            return 'Email ou senha incorretos.'

        login_user(user)
        return redirect(url_for('home'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'GET':
            return render_template('register.html')

        name = request.form['nameForm']
        mail = request.form['mailForm']
        password = request.form['passwordForm']
        upload_folder = app.config['AVATAR_UPLOAD_FOLDER']

        new_user = User(name=name, mail=mail, password=password)
        avatar_file = request.files.get('avatarForm')
        saved = save_avatar_file(avatar_file, upload_folder)
        if saved:
            new_user.avatar_filename = saved

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)

        return redirect(url_for('home'))

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('landing'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        upload_folder = app.config['AVATAR_UPLOAD_FOLDER']

        if request.method == 'GET':
            return render_template('profile.html', user=current_user)

        name = request.form['nameForm'].strip() or current_user.name
        mail = request.form['mailForm'].strip() or current_user.mail
        password = request.form['passwordForm'].strip() or current_user.password

        current_user.name = name
        current_user.mail = mail
        current_user.password = password

        avatar_file = request.files.get('avatarForm')
        saved = save_avatar_file(avatar_file, upload_folder)
        if saved:
            old = current_user.avatar_filename
            delete_avatar_file(upload_folder, old)
            current_user.avatar_filename = saved

        db.session.commit()

        return redirect(url_for('home'))

    with app.app_context():
        _ensure_sqlite_user_avatar_column(app)
        _ensure_sqlite_post_parent_id_column(app)
        _ensure_sqlite_post_likes_table(app)
        _ensure_sqlite_followers_table(app)
        _ensure_sqlite_comments_table(app)
        _ensure_sqlite_reactions_table(app)
        _ensure_sqlite_notifications_table(app)
        _ensure_sqlite_messages_table(app)

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
