# utils/cooldown.py
# Simple per-user cooldown manager (in-memory).
import time
from typing import Tuple, Dict

# key: (guild_id, user_id) -> last_attempt_epoch
_last_attempt: Dict[Tuple[int, int], float] = {}

def remaining_cooldown(guild_id: int, user_id: int, cooldown_seconds: int) -> int:
    """Return remaining seconds if on cooldown, else 0."""
    if cooldown_seconds <= 0:
        return 0
    key = (guild_id, user_id)
    now = time.time()
    last = _last_attempt.get(key, 0)
    delta = now - last
    if delta < cooldown_seconds:
        return int(round(cooldown_seconds - delta))
    return 0

def stamp_attempt(guild_id: int, user_id: int):
    _last_attempt[(guild_id, user_id)] = time.time()
