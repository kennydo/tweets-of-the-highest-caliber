import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from tothc.bots import TOTHCBot
from tothc.clients import twitter
from tothc.logging import configure_logging


log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--sqlite-db',
        help="Where the SQLite DB file is. If it doesn't exist, a new file will be created.",
    )

    # Twitter arguments
    parser.add_argument(
        '--twitter-consumer-key',
        default=os.environ.get('TWITTER_CONSUMER_KEY'),
    )
    parser.add_argument(
        '--twitter-consumer-secret',
        default=os.environ.get('TWITTER_CONSUMER_SECRET'),
    )
    parser.add_argument(
        '--twitter-access-token',
        default=os.environ.get('TWITTER_ACCESS_TOKEN'),
    )
    parser.add_argument(
        '--twitter-access-token-secret',
        default=os.environ.get('TWITTER_ACCESS_TOKEN_SECRET'),
    )

    # Slack arguments
    parser.add_argument('--slack-token', default=os.environ.get('SLACK_TOKEN'))

    return parser.parse_args()


def main():
    configure_logging()

    args = parse_args()

    assert args.sqlite_db
    assert args.twitter_consumer_key
    assert args.twitter_consumer_secret
    assert args.twitter_access_token
    assert args.twitter_access_token_secret
    assert args.slack_token

    twitter_tokens = twitter.OAuth10aTokens(
        consumer_key=args.twitter_consumer_key,
        consumer_secret=args.twitter_consumer_secret,
        access_token=args.twitter_access_token,
        access_token_secret=args.twitter_access_token_secret,
    )

    loop = asyncio.get_event_loop()

    bot = TOTHCBot(
        twitter_tokens=twitter_tokens,
        slack_token=args.slack_token,
        sqlite_db_path=Path(args.sqlite_db),
        loop=loop,
    )
    bot.initialize()

    try:
        loop.run_until_complete(bot.run())
    finally:
        loop.close()
        log.info('Successfuly shut down')

    sys.exit(0)


if __name__ == '__main__':
    main()
