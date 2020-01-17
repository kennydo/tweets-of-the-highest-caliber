import asyncio
import datetime
import logging
import signal
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

import databases
import sqlalchemy

from tothc import models
from tothc.clients import slack
from tothc.clients import twitter


log = logging.getLogger(__name__)


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
        latest_screen_name = twitter_user['screen_name']

        async with self._datastore.db.transaction():
            existing_subscription = await self._datastore.db.fetch_one(
                models.twitter_subscriptions
                .select()
                .where(models.twitter_subscriptions.c.user_id == user_id),
            )

            if existing_subscription:
                log.info('Updating existing subscription for user ID %s (%s)', user_id, latest_screen_name)
                await self._datastore.db.execute(
                    models.twitter_subscriptions
                    .update()
                    .where(models.twitter_subscriptions.c.user_id == user_id)
                    .values(latest_screen_name=latest_screen_name),
                )
            else:
                log.info('Adding new subscription for user ID %s (%s)', user_id, latest_screen_name)
                await self._datastore.db.execute(
                    models.twitter_subscriptions
                    .insert()
                    .values(
                        user_id=user_id,
                        latest_screen_name=latest_screen_name,
                    ),
                )

            return user_id

    async def fetch_new_tweets_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        subscription = await self._datastore.db.fetch_one(
            models.twitter_subscriptions
            .select()
            .where(models.twitter_subscriptions.c.user_id == user_id),
        )

        since_id = subscription[models.twitter_subscriptions.c.latest_tweet_id]

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
        log.info('Updating latest tweet ID of user %s to %s', user_id, latest_tweet_id)
        await self._datastore.db.execute(
            models.twitter_subscriptions
            .update()
            .where(models.twitter_subscriptions.c.user_id == user_id)
            .values(
                refreshed_at=datetime.datetime.utcnow(),
                latest_tweet_id=latest_tweet_id,
            ),
        )
        return new_tweets

    async def _twitter_loop(self) -> None:
        return

    async def _slack_loop(self):
        message_queue = self._slack_client.get_message_queue()

        while not self._stopped:
            message = await message_queue.get()
            log.info('Popped message from the Slack queue: %s', message)

            message_queue.task_done()

        return

    async def run(self) -> int:
        await self._datastore.db.connect()

        log.info('Starting the RTM client')
        self._slack_client.start_rtm_client()

        # The Slack RTM client's start function registers signal handlers for shutdown, so we must register ours after it.
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self._loop.add_signal_handler(s, lambda s=s: asyncio.create_task(self.stop()))

        log.info('Starting the loops')
        await asyncio.gather(
            self._slack_loop(),
            self._twitter_loop(),
            return_exceptions=True,
        )

        return 0

    async def stop(self) -> None:
        log.info('Stopping the bot')
        self._stopped = True

        tasks = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
        ]

        [task.cancel() for task in tasks]

        await asyncio.gather(*tasks)
        self._loop.stop()
