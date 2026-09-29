import time
from collections import OrderedDict, deque
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


# A real bcrypt hash of a value nobody knows, used to burn the same ~250ms
# when the account does not exist. Without it, "no such user" returns in about
# 1ms while "wrong password" takes a full bcrypt round, and that 250x gap is a
# clean oracle for enumerating which emails have accounts.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12)).decode()


def burn_password_time() -> None:
    """Spend the same work as a real verification, then discard the result."""
    bcrypt.checkpw(b"not-a-real-password", _DUMMY_HASH.encode())


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


def client_ip(request) -> str:
    """The caller's address as seen through the reverse proxy.

    uvicorn is started with --proxy-headers, so Starlette's ProxyHeaders
    middleware already rewrites request.client.host from X-Forwarded-For for
    trusted hops. This helper stays as the single place the rate limiter asks
    the question, and degrades to a constant rather than raising when there is
    no client (ASGI test transports, for one).

    The header is attacker-controllable beyond the trusted hop count, so this
    is a fairness mechanism, not an authentication one. Never make an
    authorization decision from it.
    """
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


class RateLimiter:
    """Fixed-capacity in-memory limiter for login/claim endpoints.

    Two things the previous version got wrong:

    1. It used defaultdict, so every distinct key it ever saw stayed in memory
       forever. An attacker cycling unique emails grew the dict without bound.
       This version is an LRU capped at `max_keys` and evicts the coldest key
       once full.
    2. Callers keyed it on request.client.host, which behind Caddy is Caddy —
       one shared bucket for every user on the platform. That is fixed at the
       call sites, which now include a per-identity component.

    Still per-process: with multiple uvicorn workers the effective limit is
    multiplied by the worker count. Move to Redis before scaling out.
    """

    def __init__(self, max_attempts: int = 10, window_seconds: int = 300,
                 max_keys: int = 10_000):
        self.max = max_attempts
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: "OrderedDict[str, deque]" = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self.max_keys:
                self._hits.popitem(last=False)   # evict least-recently-used
            q = deque()
            self._hits[key] = q
        else:
            self._hits.move_to_end(key)

        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True


login_limiter = RateLimiter()

# Claiming an account is a first-time-only action, so a per-identity bucket is
# the right shape: it must not be possible for one caller to exhaust a bucket
# that every other student shares. Keyed per (college, roll_no) at the call
# site, with a separate, looser per-IP bucket as a blunt flood guard.
claim_limiter = RateLimiter(max_attempts=5, window_seconds=900)
claim_flood_limiter = RateLimiter(max_attempts=300, window_seconds=300)
