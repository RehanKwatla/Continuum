"""User data access."""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UsersRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.db.execute(
            select(User).where(User.email == email.lower().strip())
        ).scalar_one_or_none()

    def get_by_supabase_id(self, supabase_user_id: str) -> User | None:
        return self.db.execute(
            select(User).where(User.supabase_user_id == supabase_user_id)
        ).scalar_one_or_none()

    def create(
        self, *, email: str, full_name: str | None, supabase_user_id: str | None
    ) -> User:
        user = User(
            email=email.lower().strip(),
            full_name=full_name,
            supabase_user_id=supabase_user_id,
        )
        self.db.add(user)
        return user
