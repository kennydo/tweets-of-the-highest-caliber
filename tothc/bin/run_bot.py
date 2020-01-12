import argparse
import asyncio
import os
import sys

from tothc.bots import TOTHCBot
from tothc.clients import twitter
from tothc.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

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

    bot = TOTHCBot(
        twitter_tokens=twitter_tokens,
        slack_token=args.slack_token,
    )

    loop = asyncio.get_event_loop()
    sys.exit(loop.run_until_complete(bot.run()))


if __name__ == '__main__':
    main()
