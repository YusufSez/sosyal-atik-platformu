from passlib.hash import argon2, sha256_crypt
from werkzeug.security import check_password_hash


def hash_password(password):
    return argon2.using(memory_cost=65536, time_cost=3, parallelism=2).hash(password)


def verify_password(password, hashed):
    if not hashed or not password:
        return False
    if hashed.startswith("$argon2"):
        try:
            return argon2.verify(password, hashed)
        except (ValueError, TypeError):
            return False
    try:
        if hashed.startswith("pbkdf2:") and check_password_hash(hashed, password):
            return True
    except ValueError:
        pass
    try:
        return sha256_crypt.verify(password, hashed)
    except ValueError:
        return False


def needs_password_update(hashed):
    return not (hashed or "").startswith("$argon2")
