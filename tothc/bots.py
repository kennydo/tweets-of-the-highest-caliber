import logging
from pathlib import Path

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

    def __init__(
        self,
        twitter_tokens: twitter.OAuth10aTokens,
        slack_token: str,
        sqlite_db_path: Path,
    ) -> None:
        self._twitter_client = twitter.Client(auth=twitter_tokens)
        self._slack_client = slack.Client(token=slack_token)

        self._datastore = Datastore(sqlite_db_path)

    def initialize(self) -> None:
        self._datastore.ensure_initialized()

    async def subscribe_to_twitter_user(self, screen_name: str) -> None:
        try:
            twitter_user = await self._twitter_client.get_user_by_screen_name(screen_name)
        except twitter.UserNotFound:
            log.exception('Could not find user with screen name %s', screen_name)
            return

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

    async def run(self) -> int:
        await self._datastore.db.connect()

        print(await self._datastore.db.fetch_all("select date('now')"))

        await self.subscribe_to_twitter_user('kedo48')
        await self.subscribe_to_twitter_user('nontedissdfsdfsdf')
        await self.subscribe_to_twitter_user('kedo48')

        await self._slack_client.post_message(
            channel='#kedo-dev-2',
            text='Hello World!',
        )

        return 0
