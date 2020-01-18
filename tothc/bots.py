import asyncio
import logging
import re
import signal
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

import databases
import sqlalchemy

from tothc import managers
from tothc import models
from tothc.clients import slack
from tothc.clients import twitter


log = logging.getLogger(__name__)

SUBSCRIBE_PATTERNS = [
    re.compile(r'subscribe (?P<username>[a-zA-Z0-9_]{1,15})\b'),
    re.compile(r'subscribe .*twitter\.com/(?P<username>[a-zA-Z0-9_]{1,15})\b'),
]


class Datastore:
    _sqlite_db_path: Path
    _database_url: str
    db: databases.Database

    def __init__(
        self,
        sqlite_db_path: Path,
    ) -> None:
        self._sqlite_db_path = sqlite_db_path
        self._database_url = f'sqlite:///{sqlite_db_path}'
        self.db = databases.Database(self._database_url)

    def ensure_initialized(self) -> None:
        if self._sqlite_db_path.exists():
            log.info("Assuming that DB doesn't need to be initialized because file exists: %s", self._sqlite_db_path)
            return

        log.info('Creating fresh DB: %s', self._sqlite_db_path)
        engine = sqlalchemy.create_engine(self._database_url)
        models.metadata.create_all(engine)


class TOTHCBot:
    _twitter_client: twitter.Client
    _slack_client: slack.Client
    _datastore: Datastore
    _loop: asyncio.AbstractEventLoop
    _stopped: bool

    def __init__(
        self,
        twitter_tokens: twitter.OAuth10aTokens,
        slack_token: str,
        sqlite_db_path: Path,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._twitter_client = twitter.Client(auth=twitter_tokens)
        self._slack_client = slack.Client(token=slack_token)

        self._datastore = Datastore(sqlite_db_path)
        self._loop = loop
        self._stopped = False

    def initialize(self) -> None:
        self._datastore.ensure_initialized()

    async def subscribe_to_twitter_user(self, screen_name: str) -> int:
        try:
            twitter_user = await self._twitter_client.get_user_by_screen_name(screen_name)
        except twitter.UserNotFound:
            log.exception('Could not find user with screen name %s', screen_name)
            raise

        user_id = twitter_user['id']
        screen_name = twitter_user['screen_name']

        await managers.TwitterSubscriptionManager.upsert_subscription(
            self._datastore.db.connection(),
            user_id=user_id,
            screen_name=screen_name,
        )

        return user_id

    async def fetch_new_tweets_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        since_id = await managers.TwitterSubscriptionManager.get_latest_tweet_id_for_user_id(
            self._datastore.db.connection(),
            user_id=user_id,
        )

        timeline = await self._twitter_client.get_user_timeline_by_user_id(user_id, since_id=since_id)
        log.info('Fetched %s tweets in timeline of user %s since ID %s', len(timeline), user_id, since_id)

        if since_id:
            new_tweets = timeline
        else:
            # This is our first fetch for the user, so don't consider anything new
            new_tweets = []

        latest_tweet_id = since_id
        if timeline:
            latest_tweet_id = timeline[0]['id']

        # Now we must update our subscription information
        await managers.TwitterSubscriptionManager.update_latest_tweet_id(
            self._datastore.db.connection(),
            user_id=user_id,
            latest_tweet_id=latest_tweet_id,
        )
        return new_tweets

    async def _twitter_loop(self) -> None:
        return

    async def _slack_loop(self):
        message_queue = self._slack_client.get_message_queue()

        while not self._stopped:
            message = await message_queue.get()
            log.info('Popped message from the Slack queue: %s', message)

            await self._handle_slack_message(message)

            message_queue.task_done()

        return

    async def _handle_slack_message(self, message: Dict[str, Any]) -> None:
        if not message.get('text'):
            return

        text = message['text']
        channel_id = message['channel']

        for pattern in SUBSCRIBE_PATTERNS:
            match = pattern.match(text)
            if match:
                twitter_username = match.groupdict()['username']
                log.info('Subscribing to twitter user %s due to text: %s', twitter_username, text)

                await self.subscribe_to_twitter_user(twitter_username)

                await self._slack_client.post_message(
                    channel=channel_id,
                    text=f'Subscribed to https://www.twitter.com/{twitter_username}',
                )
                break

    def _loop_exception_handler(self, loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        log.error('Caught exception: %s', context)

        self._loop.default_exception_handler(context)
        asyncio.create_task(self.stop())

    async def run(self) -> int:
        self._loop.set_exception_handler(self._loop_exception_handler)

        await self._datastore.db.connect()

        log.info('Starting the RTM client')
        self._slack_client.start_rtm_client()

        # The Slack RTM client's start function registers signal handlers for shutdown, so we must register ours after it.
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self._loop.add_signal_handler(s, self._create_signal_handler(s))

        log.info('Starting the loops')
        await asyncio.gather(
            self._slack_loop(),
            self._twitter_loop(),
        )

        return 0

    def _create_signal_handler(self, s: signal.Signals):
        def signal_handler():
            async def handle_signal():
                log.info('Received signal %s', s.name)
                await self.stop()

            return asyncio.create_task(handle_signal())

        return signal_handler

    async def stop(self) -> None:
        log.info('Stopping the bot')
        self._stopped = True

        tasks = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
        ]

        log.info('Cancelling %s tasks', len(tasks))
        [task.cancel() for task in tasks]

        log.info('Waiting for tasks to finish')
        await asyncio.gather(*tasks, return_exceptions=True)

        log.info('Stopping the loop')
        self._loop.stop()
