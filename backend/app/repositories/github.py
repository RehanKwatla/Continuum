"""GitHub connection data access."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.github_connection import GitHubConnection
from app.repositories.base import BaseRepository


class GitHubRepository(BaseRepository[GitHubConnection]):
    model = GitHubConnection

    def get_for_user(self, user_id: uuid.UUID) -> GitHubConnection | None:
        return self.db.execute(
            select(GitHubConnection).where(GitHubConnection.user_id == user_id)
        ).scalar_one_or_none()

    def upsert(
        self,
        *,
        user_id: uuid.UUID,
        encrypted_access_token: str,
        github_user_id: str | None,
        github_login: str | None,
        github_avatar_url: str | None,
        scopes: str | None,
        token_type: str = "bearer",
    ) -> GitHubConnection:
        connection = self.get_for_user(user_id)
        if connection is None:
            connection = GitHubConnection(
                user_id=user_id,
                encrypted_access_token=encrypted_access_token,
                github_user_id=github_user_id,
                github_login=github_login,
                github_avatar_url=github_avatar_url,
                scopes=scopes,
                token_type=token_type,
            )
            self.db.add(connection)
            return connection

        connection.encrypted_access_token = encrypted_access_token
        connection.github_user_id = github_user_id
        connection.github_login = github_login
        connection.github_avatar_url = github_avatar_url
        connection.scopes = scopes
        connection.token_type = token_type
        return connection

    def delete_for_user(self, user_id: uuid.UUID) -> bool:
        connection = self.get_for_user(user_id)
        if connection is None:
            return False
        self.db.delete(connection)
        return True
