import hmac
import hashlib
import config


def make_history_token(user_id: int, chat_id: int) -> str:
    key = config.TOKEN.encode()
    msg = f"{user_id}:{chat_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]


def verify_history_token(user_id: int, chat_id: int, token: str) -> bool:
    return hmac.compare_digest(make_history_token(user_id, chat_id), token)
