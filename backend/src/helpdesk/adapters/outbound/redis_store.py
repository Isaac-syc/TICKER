import json
from datetime import datetime
from uuid import UUID

from redis.asyncio import Redis

from helpdesk.application.ports import TabLease

# Renueva el TTL solo si el lease sigue siendo de esta pestaña; si está libre, lo toma.
# Devuelve nil si se obtuvo o el valor actual si pertenece a otra pestaña.
_ACQUIRE = """
local current = redis.call('GET', KEYS[1])
if not current then
  redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
  return nil
end
local ok, data = pcall(cjson.decode, current)
if ok and data['tab_id'] == ARGV[1] then
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  return nil
end
return current
"""

_RELEASE = """
local current = redis.call('GET', KEYS[1])
if current then
  local ok, data = pcall(cjson.decode, current)
  if ok and data['tab_id'] == ARGV[1] then
    return redis.call('DEL', KEYS[1])
  end
end
return 0
"""


def _encode(lease: TabLease) -> str:
    return json.dumps(
        {
            "tab_id": lease.tab_id,
            "session_id": str(lease.session_id),
            "acquired_at": lease.acquired_at.isoformat(),
        }
    )


def _decode(raw: str | bytes) -> TabLease:
    data = json.loads(raw)
    return TabLease(
        tab_id=data["tab_id"],
        session_id=UUID(data["session_id"]),
        acquired_at=datetime.fromisoformat(data["acquired_at"]),
    )


class RedisTabLeaseStore:
    """Operaciones atómicas con scripts Lua para evitar carreras entre pestañas."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._r = redis
        self._ttl = ttl_seconds
        self._acquire = redis.register_script(_ACQUIRE)
        self._release = redis.register_script(_RELEASE)

    @staticmethod
    def _key(user_id: UUID) -> str:
        return f"hd:tab-lease:{user_id}"

    async def acquire(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        current = await self._acquire(
            keys=[self._key(user_id)], args=[lease.tab_id, _encode(lease), self._ttl]
        )
        return _decode(current) if current else None

    async def takeover(self, user_id: UUID, lease: TabLease) -> TabLease | None:
        previous = await self._r.set(self._key(user_id), _encode(lease), ex=self._ttl, get=True)
        if not isinstance(previous, (str, bytes)) or not previous:
            return None
        old = _decode(previous)
        return None if old.tab_id == lease.tab_id else old

    async def release(self, user_id: UUID, tab_id: str) -> None:
        await self._release(keys=[self._key(user_id)], args=[tab_id])


class RedisLoginRateLimiter:
    """Ventana fija: tras N fallos, bloquea la cuenta (por correo) durante `lock_seconds`."""

    def __init__(self, redis: Redis, max_attempts: int, lock_seconds: int) -> None:
        self._r = redis
        self._max = max_attempts
        self._lock = lock_seconds

    @staticmethod
    def _key(key: str) -> str:
        return f"hd:login-fail:{key}"

    async def is_locked(self, key: str) -> bool:
        count = await self._r.get(self._key(key))
        return count is not None and int(count) >= self._max

    async def register_failure(self, key: str) -> int:
        k = self._key(key)
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.incr(k)
            pipe.expire(k, self._lock)
            count, _ = await pipe.execute()
        return int(count)

    async def reset(self, key: str) -> None:
        await self._r.delete(self._key(key))
