"""
sapt.commands.cache_cmd
Handler for 'sapt cache'.
"""

from sapt.commands._helpers import emit_json


def handle_cache(args, config, display):
    """Inspect or explicitly clear the local AI response cache."""
    from sapt.ai.cache import ResponseCache

    cache = ResponseCache()
    if args.clear:
        deleted = cache.clear()
        payload = {"cleared": deleted}
        if args.json:
            emit_json(payload)
        else:
            display.success(f"Cleared {deleted} cached AI response(s).")
        return 0

    stats = cache.stats()
    if args.json:
        emit_json(stats)
    else:
        display.info(
            f"AI cache: {stats['entries']} entries, {stats['total_hits']} hits, "
            f"{stats['size_kb']} KB, {stats['ttl_hours']:.0f}h TTL."
        )
    return 0
