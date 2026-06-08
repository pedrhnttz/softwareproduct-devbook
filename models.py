from datetime import datetime, timezone

from db import db
from flask_login import UserMixin


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Reações disponíveis (chave interna, emoji, rótulo) em ordem de exibição.
REACTION_TYPES = [
    ('like', '👍', 'Curtir'),
    ('love', '❤️', 'Amei'),
    ('haha', '😂', 'Haha'),
    ('wow', '😮', 'Uau'),
    ('sad', '😢', 'Triste'),
    ('angry', '😠', 'Grr'),
]
REACTION_EMOJI = {key: emoji for key, emoji, _ in REACTION_TYPES}
REACTION_LABEL = {key: label for key, _, label in REACTION_TYPES}


# Mantida apenas por compatibilidade com bancos antigos; os dados de curtidas
# agora vivem na tabela `reactions`.
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

    notifications = db.relationship(
        'Notification',
        foreign_keys='Notification.recipient_id',
        back_populates='recipient',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='Notification.created_at.desc()',
    )

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

    @property
    def unread_notifications_count(self) -> int:
        return self.notifications.filter_by(is_read=False).count()


class Post(db.Model):
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)

    author = db.relationship('User', back_populates='posts', foreign_keys=[author_id])
    parent = db.relationship('Post', remote_side=[id], backref='shares')
    reactions = db.relationship(
        'Reaction',
        back_populates='post',
        cascade='all, delete-orphan',
    )
    comments = db.relationship(
        'Comment',
        back_populates='post',
        cascade='all, delete-orphan',
        order_by='Comment.created_at.asc()',
    )

    def reaction_by(self, user):
        """Reação do usuário neste post, ou None."""
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        for reaction in self.reactions:
            if reaction.user_id == user.id:
                return reaction
        return None

    def user_reaction_type(self, user):
        reaction = self.reaction_by(user)
        return reaction.type if reaction else None

    def is_liked_by(self, user) -> bool:
        return self.reaction_by(user) is not None

    @property
    def liked_by(self):
        """Usuários que reagiram (compatibilidade com o sistema antigo de likes)."""
        return [reaction.user for reaction in self.reactions]

    @property
    def like_count(self) -> int:
        return len(self.reactions)

    @property
    def reaction_summary(self):
        """Lista de {type, emoji, label, count} para as reações presentes, ordenada por contagem."""
        counts = {}
        for reaction in self.reactions:
            counts[reaction.type] = counts.get(reaction.type, 0) + 1
        summary = []
        for key, emoji, label in REACTION_TYPES:
            if counts.get(key):
                summary.append({'type': key, 'emoji': emoji, 'label': label, 'count': counts[key]})
        summary.sort(key=lambda item: item['count'], reverse=True)
        return summary

    @property
    def comment_count(self) -> int:
        return len(self.comments)


class Reaction(db.Model):
    __tablename__ = 'reactions'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False, default='like')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('reactions', lazy='dynamic'))
    post = db.relationship('Post', back_populates='reactions')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='uq_reaction_user_post'),
    )

    @property
    def emoji(self) -> str:
        return REACTION_EMOJI.get(self.type, '👍')


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)

    author = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))
    post = db.relationship('Post', back_populates='comments')


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # reaction | comment | share | follow
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)

    recipient = db.relationship('User', foreign_keys=[recipient_id], back_populates='notifications')
    actor = db.relationship('User', foreign_keys=[actor_id])
    post = db.relationship('Post', foreign_keys=[post_id])


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    sender = db.relationship('User', foreign_keys=[sender_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])
