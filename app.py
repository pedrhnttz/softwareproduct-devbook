import os

from flask import Flask, abort, render_template, request, redirect, url_for, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import joinedload

from avatars import delete_avatar_file, is_valid_stored_avatar_filename, save_avatar_file
from db import db
from models import Post, User

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
        posts_query = (
            Post.query.options(joinedload(Post.author), joinedload(Post.parent).joinedload(Post.author))
            .join(User, Post.author_id == User.id)
        )
        if search_query:
            like = f'%{search_query}%'
            posts_query = posts_query.filter(
                or_(Post.body.ilike(like), User.name.ilike(like))
            )
        posts = posts_query.order_by(Post.created_at.desc()).all()
        return render_template('home.html', posts=posts, search_query=search_query)

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

    @app.route('/post/<int:post_id>/like', methods=['POST'])
    @login_required
    def toggle_like(post_id):
        post = db.session.get(Post, post_id)
        if post is None:
            abort(404)
        if current_user in post.liked_by:
            post.liked_by.remove(current_user)
        else:
            post.liked_by.append(current_user)
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
        db.session.commit()
        return redirect(request.referrer or url_for('home'))

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

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
