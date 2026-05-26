from datetime import datetime, timezone

from db import db
from flask_login import UserMixin


post_likes = db.Table(
    'post_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('posts.id'), primary_key=True),
)


followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    mail = db.Column(db.String(100), unique=True)
    password = db.Column(db.String())
    avatar_filename = db.Column(db.String(255), nullable=True)

    posts = db.relationship('Post', back_populates='author', lazy='dynamic', cascade='all, delete-orphan', foreign_keys='Post.author_id')

    following = db.relationship(
        'User',
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'),
        lazy='dynamic',
    )

    def is_following(self, other) -> bool:
        if other is None:
            return False
        return self.following.filter(followers.c.followed_id == other.id).count() > 0

    def follow(self, other) -> None:
        if other is None or other.id == self.id:
            return
        if not self.is_following(other):
            self.following.append(other)

    def unfollow(self, other) -> None:
        if other is None:
            return
        if self.is_following(other):
            self.following.remove(other)

    @property
    def followers_count(self) -> int:
        return self.followers.count()

    @property
    def following_count(self) -> int:
        return self.following.count()


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
    comments = db.relationship(
        'Comment',
        back_populates='post',
        cascade='all, delete-orphan',
        order_by='Comment.created_at.asc()',
    )

    def is_liked_by(self, user) -> bool:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return user in self.liked_by

    @property
    def like_count(self) -> int:
        return len(self.liked_by)

    @property
    def comment_count(self) -> int:
        return len(self.comments)


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)

    author = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))
    post = db.relationship('Post', back_populates='comments')
