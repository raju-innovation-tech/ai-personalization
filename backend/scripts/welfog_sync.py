"""
Sync Welfog's databases into the AI engine (see docs/WELFOG_INTEGRATION.md).

    python -m scripts.welfog_sync --dry-run
    python -m scripts.welfog_sync --sources products
    python -m scripts.welfog_sync
Inside Docker:  docker compose exec backend python -m scripts.welfog_sync ...
"""
from app.integrations.welfog.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
