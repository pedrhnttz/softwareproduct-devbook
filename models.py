from datetime import datetime, timezone

from db import db
from flask_login import UserMixin


post_likes = db.Table(
    'post_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.id'), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    mail = db.Column(db.String(100), unique=True)
    password = db.Column(db.String())
    avatar_filename = db.Column(db.String(255), nullable=True)

    posts = db.relationship('Post', back_populates='author', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Post.author_id')


class Post(db.Model):
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)

    author = db.relationship('User', back_populates='posts', foreign_keys=[author_id])
    parent = db.relationship('Post', remote_side=[id], backref='shares')
    liked_by = db.relationship(
        'User',
        secondary=post_likes,
        lazy='select',
        backref=db.backref('liked_posts', lazy='dynamic'),
    )

    def is_liked_by(self, user) -> bool:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return user in self.liked_by

    @property
    def like_count(self) -> int:
        return len(self.liked_by)
