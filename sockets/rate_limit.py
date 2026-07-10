import time

from .state import _connection_counts, _rate_buckets


def _check_rate_limit(user_id: int, event: str, max_per_second: int) -> bool:
    now = time.time()
    bucket = _rate_buckets[user_id][event]
    bucket[:] = [stamp for stamp in bucket if now - stamp < 1]
    if len(bucket) >= max_per_second:
        return False
    bucket.append(now)
    return True


def _cleanup_user_rate_limit(user_id: int) -> None:
    if _connection_counts.get(user_id, 0) == 0:
        _rate_buckets.pop(user_id, None)
