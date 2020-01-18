import datetime
import logging

from databases.core import Connection

from tothc import models


log = logging.getLogger(__name__)


class TwitterSubscriptionManager:
    @classmethod
    async def subscribe(
        cls,
        connection: Connection,
        *,
        user_id: int,
        screen_name: str,
    ) -> None:
        async with connection.transaction():
            # This subscription might be inactive.
            existing_subscription = await connection.fetch_one(
                models.twitter_subscriptions
                .select()
                .where(models.twitter_subscriptions.c.user_id == user_id),
            )

            if existing_subscription:
                if existing_subscription[models.twitter_subscriptions.c.unsubscribed_at]:
                    log.info('Re-enabling existing subscription for user ID %s (%s)', user_id, screen_name)
                    await connection.execute(
                        models.twitter_subscriptions
                        .update()
                        .where(models.twitter_subscriptions.c.user_id == user_id)
                        .values(
                            screen_name=screen_name,
                            subscribed_at=datetime.datetime.utcnow(),
                            unsubscribed_at=None,
                        ),
                    )
                else:
                    log.info('User ID %s (%s) already has an active subscription', user_id, screen_name)
            else:
                log.info('Adding new subscription for user ID %s (%s)', user_id, screen_name)
                await connection.execute(
                    models.twitter_subscriptions
                    .insert()
                    .values(
                        user_id=user_id,
                        screen_name=screen_name,
                        subscribed_at=datetime.datetime.utcnow(),
                    ),
                )

    @classmethod
    async def unsubscribe(
        cls,
        connection: Connection,
        *,
        screen_name: str,
    ) -> None:
        """We unsubscribe based on the screen name in our DB instead of the user ID because
        screen names can change, and users can get into bad states (ex: suspended) that prevent
        us from fetching their ID.
        """
        log.info('Unsubscribing from screen name %s', screen_name)
        await connection.execute(
            models.twitter_subscriptions
            .update()
            .where(models.twitter_subscriptions.c.screen_name.ilike(screen_name))
            .values(
                unsubscribed_at=datetime.datetime.utcnow(),
                latest_tweet_id=None,
                refreshed_latest_tweet_id_at=None,
            ),
        )

    @classmethod
    async def update_screen_name(
        cls,
        connection: Connection,
        *,
        user_id: int,
        screen_name: str,
    ) -> None:
        await connection.execute(
            models.twitter_subscriptions
            .update()
            .where(models.twitter_subscriptions.c.user_id == user_id)
            .values(
                screen_name=screen_name,
            ),
        )

    @classmethod
    async def get_latest_tweet_id_for_user_id(
        cls,
        connection: Connection,
        *,
        user_id: int
    ) -> int:
        subscription = await connection.fetch_one(
            models.twitter_subscriptions
            .select()
            .where(models.twitter_subscriptions.c.user_id == user_id),
        )

        return subscription[models.twitter_subscriptions.c.latest_tweet_id]

    @classmethod
    async def update_latest_tweet_id(
        cls,
        connection: Connection,
        *,
        user_id: int,
        latest_tweet_id: int,
    ) -> None:
        log.info('Updating latest tweet ID of user %s to %s', user_id, latest_tweet_id)
        await connection.execute(
            models.twitter_subscriptions
            .update()
            .where(models.twitter_subscriptions.c.user_id == user_id)
            .values(
                refreshed_latest_tweet_id_at=datetime.datetime.utcnow(),
                latest_tweet_id=latest_tweet_id,
            ),
        )
