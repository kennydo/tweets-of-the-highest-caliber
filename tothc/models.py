from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base


# Since `Base` is a dynamically declared class, mypy doesn't understand it.
Base = declarative_base()  # type: Any


class TwitterSubscription(Base):
    __tablename__ = 'twitter_subscriptions'

    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, nullable=False, unique=True)
    refreshed_at = sa.Column(sa.DateTime)
    latest_screen_name = sa.Column(sa.String)
    latest_tweet_id = sa.Column(sa.Integer)
