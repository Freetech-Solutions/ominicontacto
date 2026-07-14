import logging
from base64 import urlsafe_b64encode
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from cryptography.fernet import MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings

log = logging.getLogger(__name__)


keys = [
    urlsafe_b64encode(
        PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_key.encode("utf-8"),
            iterations=480_000,
        ).derive(secret_key.encode("utf-8"))
    )
    for salt_key in tuple((settings.SALT_KEY, *settings.SALT_KEY_FALLBACKS))
    for secret_key in tuple((settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS))
]


crypter = Fernet(keys[0]) if len(keys) == 1 else MultiFernet([Fernet(key) for key in keys])


def decrypt(value: str, raise_exception=False) -> str:
    try:
        return crypter.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        if raise_exception:
            raise ValueError("Unable to decrypt value", value)
        else:
            return None


def encrypt(value: str) -> str:
    return crypter.encrypt(value.encode("utf-8")).decode("utf-8")
