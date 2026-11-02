"""
Create (or update) a dashboard / service-account user.

    python -m scripts.create_user --email shop@example.com --password 'S3cret-pass!' --role ADMIN
    python -m scripts.create_user --email marketer@example.com --password '...' --role MARKETING_MANAGER --name "Maya"
    python -m scripts.create_user --email shop@example.com --password 'new-pass' --role ADMIN --update

Roles: SUPER_ADMIN, ADMIN, MARKETING_MANAGER, VIEWER (and any other value of UserRole).
Inside Docker:  docker compose exec backend python -m scripts.create_user ...
"""
import argparse
import asyncio
import sys

from app.database.database import AsyncSessionLocal
from app.database.models.user import UserRole
from app.users.service import create_user  # noqa: F401  (re-exported for tests and callers)


async def _main(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        try:
            outcome = await create_user(
                db,
                email=args.email,
                password=args.password,
                role=UserRole(args.role),
                full_name=args.name,
                update=args.update,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    print(f"User {args.email.strip().lower()} {outcome} with role {args.role}.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or update a user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="ADMIN", choices=[r.value for r in UserRole])
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument("--update", action="store_true", help="update password/role when the user exists")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))
