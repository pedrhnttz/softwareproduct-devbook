import os
import re
import uuid

from werkzeug.utils import secure_filename

STORED_AVATAR_NAME = re.compile(r'^[a-f0-9]{32}\.(?:png|jpg|jpeg|gif|webp)$', re.I)

ALLOWED_AVATAR_EXTENSIONS = frozenset({'png', 'jpg', 'jpeg', 'gif', 'webp'})
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def is_valid_stored_avatar_filename(name: str | None) -> bool:
    return bool(name and STORED_AVATAR_NAME.match(name))


def allowed_avatar_filename(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_AVATAR_EXTENSIONS


def save_avatar_file(storage, upload_folder: str) -> str | None:
    """Salva arquivo de imagem e retorna o nome único, ou None se inválido."""
    if storage is None or not getattr(storage, 'filename', None):
        return None
    if not allowed_avatar_filename(storage.filename):
        return None

    ext = storage.filename.rsplit('.', 1)[1].lower()
    safe_ext = secure_filename(f'x.{ext}').rsplit('.', 1)[-1].lower()
    if safe_ext not in ALLOWED_AVATAR_EXTENSIONS:
        return None

    name = f'{uuid.uuid4().hex}.{safe_ext}'
    os.makedirs(upload_folder, exist_ok=True)
    path = os.path.join(upload_folder, name)
    storage.save(path)

    if os.path.getsize(path) > MAX_AVATAR_BYTES:
        os.remove(path)
        return None
    return name


def delete_avatar_file(upload_folder: str, filename: str | None) -> None:
    if not filename:
        return
    path = os.path.join(upload_folder, filename)
    if os.path.isfile(path):
        os.remove(path)
