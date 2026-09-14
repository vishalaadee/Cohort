import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(*, user_id: int, role: str,
                 college_id: int | None, branch_id: int | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "college_id": college_id,
        "branch_id": branch_id,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


class RateLimiter:
    """Naive in-memory limiter for login/claim endpoints. Per-process only —
    good enough for a single-box POC; swap for Redis when you scale out."""

    def __init__(self, max_attempts: int = 10, window_seconds: int = 300):
        self.max = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True


login_limiter = RateLimiter()
