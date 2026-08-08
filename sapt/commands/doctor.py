"""
sapt.commands.doctor
Handler for 'sapt doctor'.
"""

from sapt.commands._helpers import emit_json


def handle_doctor(args, config, display):
    """Handle 'sapt doctor'."""
    from sapt.execution.apt import AptBackend
    from sapt.security.audit import AuditLogger
    from sapt.ai.cache import ResponseCache
    from sapt.ai.usage import UsageTracker
    from sapt.config.manager import ConfigManager
    from sapt.utils.constants import CACHE_DIR

    display.banner_mini()
    checks = {}
    score = 100

    # Check APT
    try:
        AptBackend()
        checks["APT available"] = {"ok": True, "detail": "apt is installed and working"}
    except Exception:
        checks["APT available"] = {"ok": False, "detail": "apt not found"}
        score -= 20

    # Check audit log
    audit = AuditLogger()
    valid, msg = audit.verify_chain()
    checks["Audit log integrity"] = {"ok": valid, "detail": msg}
    if not valid:
        score -= 15

    # Check cache
    cache = ResponseCache()
    stats = cache.stats()
    checks["AI response cache"] = {
        "ok": True,
        "detail": f"{stats['entries']} entries, {stats['size_kb']} KB",
    }

    usage = UsageTracker().monthly_summary()
    budget = float(config.get("monthly_budget_usd") or 0.0) if config else 0.0
    usage_detail = (
        f"{usage['calls']} calls, "
        f"${usage['estimated_spend_usd']:.4f} estimated this month"
    )
    if budget > 0:
        usage_detail += f" / ${budget:.4f} budget"
    checks["AI usage budget"] = {
        "ok": budget <= 0 or usage["estimated_spend_usd"] <= budget,
        "detail": usage_detail,
    }
    if budget > 0 and usage["estimated_spend_usd"] > budget:
        score -= 10

    # Check config
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        checks["Config file"] = {"ok": False, "detail": "No config found"}
        score -= 10
    else:
        try:
            config_mgr.load()
            checks["Config file"] = {"ok": True, "detail": "Config exists and is valid"}
        except (ValueError, FileNotFoundError):
            checks["Config file"] = {
                "ok": False,
                "detail": "Config exists but is invalid",
            }
            score -= 10

    # Check disk usage of cache dir
    cache_size = (
        sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
        if CACHE_DIR.exists()
        else 0
    )
    cache_mb = cache_size / (1024 * 1024)
    checks["Cache disk usage"] = {
        "ok": cache_mb < 100,
        "detail": f"{cache_mb:.1f} MB"
        + (" (consider clearing)" if cache_mb > 100 else ""),
    }
    if cache_mb > 100:
        score -= 5

    report = {"score": max(0, score), "checks": checks}
    if args.json:
        emit_json(report)
    else:
        display.show_doctor(report)
    return 0
