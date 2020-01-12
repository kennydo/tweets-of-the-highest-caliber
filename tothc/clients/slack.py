from typing import Any
from typing import Dict

from slack import WebClient


class Client:
    _webclient: WebClient

    def __init__(
        self,
        *,
        token: str,
    ) -> None:
        self._webclient = WebClient(
            token=token,
            run_async=True,
        )

    async def post_message(
        self,
        channel: str,
        text: str,
    ) -> Dict[str, Any]:
        return await self._webclient.chat_postMessage(
            channel=channel,
            text=text,
            icon_emoji='robot_face',
        )
