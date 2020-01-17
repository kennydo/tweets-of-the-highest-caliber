import asyncio
import logging
from typing import Any
from typing import Dict

from slack import RTMClient
from slack import WebClient

log = logging.getLogger(__name__)

_message_queue: asyncio.Queue = asyncio.Queue()


@RTMClient.run_on(event='message')
async def _enqueue_message(**payload) -> None:
    message_data = payload['data']

    if message_data.get('subtype') == 'bot_message':
        log.info('Ignoring bot message: %s', message_data)
        return

    await _message_queue.put(payload['data'])


class Client:
    _web_client: WebClient
    _rtm_client: RTMClient

    def __init__(
        self,
        *,
        token: str,
    ) -> None:
        self._webclient = WebClient(
            token=token,
            run_async=True,
        )
        self._rtm_client = RTMClient(
            token=token,
            run_async=True,
        )

    async def post_message(
        self,
        channel: str,
        text: str,
    ) -> Dict[str, Any]:
        log.info('Sending slack message to channel %s: %s', channel, text)
        return await self._webclient.chat_postMessage(
            channel=channel,
            text=text,
            icon_emoji='robot_face',
        )

    def start_rtm_client(self) -> asyncio.Future:
        return self._rtm_client.start()

    def stop_rtm_client(self) -> None:
        return self._rtm_client.stop()

    def get_message_queue(self) -> asyncio.Queue:
        return _message_queue
