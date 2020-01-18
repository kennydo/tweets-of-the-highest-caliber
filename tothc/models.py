import sqlalchemy as sa


metadata = sa.MetaData()

twitter_subscriptions = sa.Table(
    'twitter_subscriptions',
    metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('user_id', sa.Integer, nullable=False, unique=True),
    sa.Column('screen_name', sa.String),

    sa.Column('latest_tweet_id', sa.Integer),
    sa.Column('refreshed_latest_tweet_id_at', sa.DateTime),
)
