from tothc.clients import slack
from tothc.clients import twitter


class TOTHCBot:
    _twitter_client: twitter.Client
    _slack_client: slack.Client

    def __init__(
        self,
        twitter_tokens: twitter.OAuth10aTokens,
        slack_token: str,
    ) -> None:
        self._twitter_client = twitter.Client(auth=twitter_tokens)
        self._slack_client = slack.Client(token=slack_token)

    async def run(self) -> int:
        await self._slack_client.post_message(
            channel='#kedo-dev-2',
            text='Hello World!',
        )

        return 0
