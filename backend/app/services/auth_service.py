"""Authentication service: maps a verified principal onto a local user row."""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.security import DEV_PROVIDER, AuthPrincipal
from app.models.user import User
from app.repositories.users import UsersRepository

logger = logging.getLogger("continuum.auth")


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UsersRepository(db)

    def resolve_user(self, principal: AuthPrincipal) -> User:
        """Find or create the local User for a verified principal.

        The frontend never supplies this identity — it always derives from a
        verified token.
        """
        if principal.provider == DEV_PROVIDER and not principal.email:
            raise AuthError("Development session is missing an email claim.")

        user: User | None = None
        if principal.provider != DEV_PROVIDER:
            user = self.users.get_by_supabase_id(principal.subject)

        if user is None and principal.email:
            # Fall back to email so a user created before Supabase linking still matches.
            user = self.users.get_by_email(principal.email)

        if user is not None:
            changed = False
            if principal.provider != DEV_PROVIDER and not user.supabase_user_id:
                user.supabase_user_id = principal.subject
                changed = True
            if principal.full_name and not user.full_name:
                user.full_name = principal.full_name
                changed = True
            if changed:
                try:
                    self.db.commit()
                    self.db.refresh(user)
                except IntegrityError:
                    self.db.rollback()
            return user

        email = principal.email
        if not email:
            raise AuthError(
                "Verified token does not contain an email claim; cannot provision a user.",
                code="invalid_token",
            )

        user = self.users.create(
            email=email,
            full_name=principal.full_name,
            supabase_user_id=None if principal.provider == DEV_PROVIDER else principal.subject,
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.users.get_by_email(email)
            if existing is None:
                raise AuthError("Could not provision the user record.") from None
            return existing

        self.db.refresh(user)
        logger.info("Provisioned local user record for %s", user.id)
        return user
