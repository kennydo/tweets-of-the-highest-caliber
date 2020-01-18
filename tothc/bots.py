import asyncio
import logging
import re
import signal
from pathlib import Path
from typing import Any
from typing import Dict

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
UNSUBSCRIBE_PATTERNS = [
    re.compile(r'unsubscribe (?P<username>[a-zA-Z0-9_]{1,15})\b'),
    re.compile(r'unsubscribe .*twitter\.com/(?P<username>[a-zA-Z0-9_]{1,15})\b'),
]

# The timeline endpoint has a rate limit of 900 requests per 15 minute window.
# This determines how long the bot waits between its batches of polling.
TWITTER_TIMELINE_POLL_PERIOD_SEC = 100


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
    _slack_channel: str
    _datastore: Datastore
    _loop: asyncio.AbstractEventLoop
    _stopped: bool

    def __init__(
        self,
        twitter_tokens: twitter.OAuth10aTokens,
        slack_token: str,
        slack_channel: str,
        sqlite_db_path: Path,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._twitter_client = twitter.Client(auth=twitter_tokens)
        self._slack_client = slack.Client(token=slack_token)
        self._slack_channel = slack_channel

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

        async with self._connection() as conn:
            await managers.TwitterSubscriptionManager.subscribe(
                conn,
                user_id=user_id,
                screen_name=screen_name,
            )

        return user_id

    async def unsubscribe_from_twitter_user(self, screen_name: str) -> None:
        async with self._connection() as conn:
            await managers.TwitterSubscriptionManager.unsubscribe(
                conn,
                screen_name=screen_name,
            )

    async def _handle_polling_twitter_user_id(self, user_id: int) -> None:
        async with self._connection() as conn:
            since_id = await managers.TwitterSubscriptionManager.get_latest_tweet_id_for_user_id(
                conn,
                user_id=user_id,
            )

        timeline = await self._twitter_client.get_user_timeline_by_user_id(user_id, since_id=since_id)
        log.info('Fetched %s tweets in timeline of user %s since ID %s', len(timeline), user_id, since_id)

        if since_id:
            new_tweets = timeline.tweets
        else:
            # This is our first fetch for the user, so don't consider anything new
            new_tweets = []

        latest_tweet_id = since_id
        if timeline.tweets:
            latest_tweet_id = timeline.tweets[0].data['id']

        # Now we must update our subscription information
        async with self._connection() as conn:
            await managers.TwitterSubscriptionManager.update_latest_tweet_id(
                conn,
                user_id=user_id,
                latest_tweet_id=latest_tweet_id,
            )

        # Now we deal with the new tweets
        for tweet in new_tweets:
            screen_name = tweet.data['user']['screen_name']
            log.info('New tweet from user %s (has_media=%s): %s', screen_name, tweet.has_media(), tweet.url_of_content())

            if not tweet.has_media():
                continue

            url = tweet.url_of_content()
            if tweet.is_retweet():
                text = f'<https://www.twitter.com/{screen_name}|{screen_name}> retweeted <{url}>'
            else:
                text = f'<https://www.twitter.com/{screen_name}|{screen_name}> tweeted <{url}>'

            await self._slack_client.post_message(
                channel=self._slack_channel,
                text=text,
            )

    async def _twitter_loop(self) -> None:
        while not self._stopped:
            async with self._connection() as conn:
                user_ids = await managers.TwitterSubscriptionManager.list_user_ids_of_active_subscriptions(
                    conn,
                )

                log.info('Got %s active twitter subscriptions: %s', len(user_ids), user_ids)

                tasks = {
                    asyncio.create_task(self._handle_polling_twitter_user_id(user_id))
                    for user_id in user_ids
                }
                await asyncio.wait(tasks)
                log.info('Finished polling tasks for %s user ids', len(user_ids))

            await asyncio.sleep(TWITTER_TIMELINE_POLL_PERIOD_SEC)
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

                text = f'Subscribed to <https://www.twitter.com/{twitter_username}|{twitter_username}>'

                try:
                    await self.subscribe_to_twitter_user(twitter_username)
                except twitter.UserNotFound:
                    text = f'No twitter user name {twitter_username} found'

                await self._slack_client.post_message(
                    channel=channel_id,
                    text=text,
                )
                return

        for pattern in UNSUBSCRIBE_PATTERNS:
            match = pattern.match(text)
            if match:
                twitter_username = match.groupdict()['username']
                log.info('Unubscribing from twitter user %s due to text: %s', twitter_username, text)

                await self.unsubscribe_from_twitter_user(twitter_username)
                await self._slack_client.post_message(
                    channel=channel_id,
                    text=f'Unsubscribed from https://www.twitter.com/{twitter_username}',
                )
                return

    def _connection(self) -> databases.core.Connection:
        return self._datastore.db.connection()

    def _loop_exception_handler(self, loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        log.info('Loop handled an exception, but might not actually be an issue: %s', context)

        self._loop.default_exception_handler(context)

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
