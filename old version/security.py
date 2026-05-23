from cryptography.fernet import Fernet, InvalidToken


def _to_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode('utf-8')


def encrypt_secret(value, key):
    if value is None or value == '':
        return value
    if not key:
        raise ValueError('Missing encryption key')
    return Fernet(_to_bytes(key)).encrypt(_to_bytes(value)).decode('utf-8')


def decrypt_secret(value, key):
    if value is None or value == '':
        return value
    if not key:
        raise ValueError('Missing encryption key')
    try:
        return Fernet(_to_bytes(key)).decrypt(_to_bytes(value)).decode('utf-8')
    except InvalidToken:
        return value