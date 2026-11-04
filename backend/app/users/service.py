"""Staff users: shared by the CLI (scripts/create_user.py) and the /users API."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import ApiError
from app.core.security import hash_password
from app.database.models.user import User, UserRole

MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"'{email}' is not a valid email address")
    return email


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def user_out(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ----------------------------------------------------------------------- CLI
async def create_user(
    db: AsyncSession, *, email: str, password: str, role: UserRole, full_name: str | None = None, update: bool = False
) -> str:
    """Returns 'created' or 'updated'. Raises ValueError for bad input or a duplicate email."""
    email = normalize_email(email)
    validate_password(password)

    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        if not update:
            raise ValueError(f"user '{email}' already exists (add --update to change its password / role)")
        existing.hashed_password = hash_password(password)
        existing.role = role
        existing.is_active = True
        existing.refresh_token_hash = None
        if full_name:
            existing.full_name = full_name
        await db.commit()
        return "updated"

    db.add(
        User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name or email.split("@")[0],
            role=role,
            is_active=True,
        )
    )
    await db.commit()
    return "created"


# ----------------------------------------------------------------------- API
def _forbidden(message: str) -> ApiError:
    return ApiError("INSUFFICIENT_ROLE", message, status_code=403)


def _require_super_admin_for(actor: User, *roles: UserRole) -> None:
    """Only a SUPER_ADMIN may create, grant, change or deactivate SUPER_ADMIN accounts."""
    if UserRole.SUPER_ADMIN in roles and actor.role != UserRole.SUPER_ADMIN:
        raise _forbidden("Only a Super Admin can manage Super Admin accounts")


async def list_users(db: AsyncSession) -> list[User]:
    return list((await db.execute(select(User).order_by(User.created_at, User.email))).scalars().all())


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def _total_super_admins(db: AsyncSession) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(User).where(User.role == UserRole.SUPER_ADMIN)
            )
        ).scalar_one()
    )


async def _active_super_admins(db: AsyncSession, excluding: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(User).where(
                    User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True), User.id != excluding
                )
            )
        ).scalar_one()
    )


async def create_user_checked(db: AsyncSession, actor: User, *, email: str, password: str, full_name: str | None, role: UserRole) -> User:
    _require_super_admin_for(actor, role)
    if role == UserRole.SUPER_ADMIN and await _total_super_admins(db) >= 1:
        raise ApiError("ONLY_ONE_SUPER_ADMIN", "Only one Super Admin can exist in the system", status_code=409)
    try:
        email = normalize_email(email)
        validate_password(password)
    except ValueError as exc:
        raise ApiError("VALIDATION_ERROR", str(exc), status_code=422) from exc
    if (await db.execute(select(User.id).where(User.email == email))).first() is not None:
        raise ApiError("EMAIL_ALREADY_EXISTS", f"A user with email '{email}' already exists", status_code=409)
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=(full_name or email.split("@")[0]).strip(),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_checked(
    db: AsyncSession,
    actor: User,
    user: User,
    *,
    email: str | None = None,
    full_name: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> User:
    # Super Admin protection: Non-super-admins cannot edit the Super Admin account
    if user.role == UserRole.SUPER_ADMIN and actor.role != UserRole.SUPER_ADMIN:
        raise ApiError("SUPER_ADMIN_PROTECTED", "Only the Super Admin can modify the Super Admin account", status_code=403)

    new_role = role if role is not None else user.role
    _require_super_admin_for(actor, user.role, new_role)

    # Only 1 Super Admin allowed in the system
    if role == UserRole.SUPER_ADMIN and user.role != UserRole.SUPER_ADMIN:
        if await _total_super_admins(db) >= 1:
            raise ApiError("ONLY_ONE_SUPER_ADMIN", "Only one Super Admin can exist in the system", status_code=409)

    role_changes = role is not None and role != user.role
    deactivates = is_active is False and user.is_active
    if user.id == actor.id and (role_changes or is_active is False):
        raise ApiError("CANNOT_MODIFY_SELF", "You cannot change your own role or deactivate your own account", status_code=409)

    losing_super_admin = user.role == UserRole.SUPER_ADMIN and user.is_active and (role_changes or deactivates)
    if losing_super_admin and await _active_super_admins(db, excluding=user.id) == 0:
        raise ApiError("LAST_SUPER_ADMIN", "There must always be at least one active Super Admin", status_code=409)

    email_changed = False
    if email is not None:
        try:
            email = normalize_email(email)
        except ValueError as exc:
            raise ApiError("VALIDATION_ERROR", str(exc), status_code=422) from exc
        if email != user.email:
            existing = (await db.execute(select(User.id).where(User.email == email, User.id != user.id))).first()
            if existing is not None:
                raise ApiError("EMAIL_ALREADY_EXISTS", f"A user with email '{email}' already exists", status_code=409)
            user.email = email
            email_changed = True

    if password is not None:
        try:
            validate_password(password)
        except ValueError as exc:
            raise ApiError("VALIDATION_ERROR", str(exc), status_code=422) from exc
        user.hashed_password = hash_password(password)
    if full_name is not None:
        user.full_name = full_name.strip()
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if password is not None or role_changes or deactivates or email_changed:
        user.refresh_token_hash = None  # forces a fresh login with the new credentials / permissions

    await db.commit()
    await db.refresh(user)
    return user


async def delete_user_checked(db: AsyncSession, actor: User, user: User) -> None:
    if user.role == UserRole.SUPER_ADMIN:
        raise ApiError("CANNOT_DELETE_SUPER_ADMIN", "The Super Admin account cannot be deleted", status_code=409)
    if user.id == actor.id:
        raise ApiError("CANNOT_DELETE_SELF", "You cannot delete your own account", status_code=409)
    if actor.role != UserRole.SUPER_ADMIN and user.role == UserRole.SUPER_ADMIN:
        raise ApiError("SUPER_ADMIN_PROTECTED", "Only the Super Admin can delete the Super Admin account", status_code=403)
    await db.delete(user)
    await db.commit()
