from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List
from typing import NamedTuple
from typing import Optional

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


class Tweet(NamedTuple):
    data: Dict[str, Any]

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> Tweet:
        return cls(data=data)

    def has_media(self) -> bool:
        return bool(self.data.get('entities', {}).get('media'))

    def is_retweet(self) -> bool:
        return bool(self.data.get('retweeted_status'))

    def url_of_content(self) -> str:
        """Either the URL of the tweet itself, or the URL of the tweet it's a retweet of.
        """
        if self.is_retweet():
            screen_name = self.data['retweeted_status']['user']['screen_name']
            tweet_id = self.data['retweeted_status']['id']
        else:
            screen_name = self.data['user']['screen_name']
            tweet_id = self.data['id']
        return f'https://www.twitter.com/{screen_name}/status/{tweet_id}'


class Timeline(NamedTuple):
    tweets: List[Tweet]

    @classmethod
    def from_data(cls, data: List[Dict[str, Any]]) -> Timeline:
        return cls(
            tweets=[
                Tweet.from_data(tweet)
                for tweet in data
            ],
        )


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

    async def get_user_timeline_by_user_id(
        self,
        user_id: int,
        since_id: Optional[int] = None,
    ) -> Timeline:
        try:
            response = await self._peony_client.api.statuses.user_timeline.get(
                user_id=user_id,
                since_id=since_id,
                count=200,
                include_retweets=True,
                tweet_mode='extended',
            )
        except peony.exceptions.DoesNotExist:
            raise

        return Timeline.from_data(response.data)
