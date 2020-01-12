from typing import Any
from typing import Dict
from typing import NamedTuple

import peony.exceptions
from peony import PeonyClient


class ClientException(Exception):
    pass


class UserNotFound(ClientException):
    def __init__(self, screen_name: str) -> None:
        self.screen_name = screen_name
        self.message = f'User not found: {screen_name}'


class OAuth10aTokens(NamedTuple):
    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str


class Client:
    _peony_client: PeonyClient

    def __init__(
        self,
        *,
        auth: OAuth10aTokens,
    ) -> None:
        self._peony_client = PeonyClient(
            consumer_key=auth.consumer_key,
            consumer_secret=auth.consumer_secret,
            access_token=auth.access_token,
            access_token_secret=auth.access_token_secret,
        )

    async def get_user_by_screen_name(self, screen_name: str) -> Dict[str, Any]:
        try:
            response = await self._peony_client.api.users.show.get(screen_name=screen_name)
        except peony.exceptions.NotFound as e:
            raise UserNotFound(screen_name) from e

        return response
