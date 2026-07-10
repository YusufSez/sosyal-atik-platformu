from collections import defaultdict

_connection_counts: defaultdict[int, int] = defaultdict(int)
_rate_buckets: defaultdict[int, defaultdict[str, list]] = defaultdict(lambda: defaultdict(list))
_sid_users: dict[str, int] = {}
_user_sids: defaultdict[int, set] = defaultdict(set)
_sid_conversations: defaultdict[str, list] = defaultdict(list)
