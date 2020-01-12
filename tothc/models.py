import sqlalchemy as sa


metadata = sa.MetaData()

twitter_subscriptions = sa.Table(
    'twitter_subscriptions',
    metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('user_id', sa.Integer, nullable=False, unique=True),
    sa.Column('refreshed_at', sa.DateTime),
    sa.Column('latest_screen_name', sa.String),
    sa.Column('latest_tweet_id', sa.Integer),
)
