from typing import NamedTuple

from peony import PeonyClient


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
