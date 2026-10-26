"""Local manual execution gate; hashes are never included in execution records."""
import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def valid_hash(value):
    if not isinstance(value, str):
        return False
    parts = value.split('$')
    try:
        return (len(parts) == 4 and parts[0] == 'pbkdf2-sha256'
                and ITERATIONS <= int(parts[1]) <= 2_000_000
                and len(bytes.fromhex(parts[2])) == 32
                and len(bytes.fromhex(parts[3])) == 32)
    except (ValueError, IndexError):
        return False


def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('Authorization password must contain 12–1024 characters')
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'pbkdf2-sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def authorize(profile, password):
    value = profile.get('manual_configuration_auth', {}).get('password_hash')
    if not valid_hash(value) or not isinstance(password, str) or len(password) > 1024:
        raise ValueError('Manual authorization unavailable or denied')
    _, work, salt, expected = value.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(work))
    if not hmac.compare_digest(actual, bytes.fromhex(expected)):
        raise ValueError('Manual authorization unavailable or denied')
