import asyncio
import binascii
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp
import async_timeout
import yarl

from .._helper import _send_request, pack_ws_bytes, parse_ws_bytes
from ..const import TIME_CONFIG
from ..exception import HTTPStatusError
from . import TbCore

TypeWebsocketCallback = Callable[["WsCore", bytes, int], Awaitable[None]]


class WsResponse(object):
    """
    websocket响应

    Args:
        data_future (asyncio.Future): 用于等待读事件到来的Future
        read_timeout (float): 读超时时间
    """

    __slots__ = [
        'future',
        'read_timeout',
    ]

    def __init__(self, data_future: asyncio.Future, read_timeout: float) -> None:
        self.future = data_future
        self.read_timeout = read_timeout

    def _cancel(self) -> None:
        self.future.cancel()

    async def read(self) -> bytes:
        """
        读取websocket响应

        Returns:
            bytes

        Raises:
            asyncio.TimeoutError: 读取超时
        """

        try:
            with async_timeout.timeout(self.read_timeout):
                return await self.future
        except asyncio.TimeoutError as err:
            self._cancel()
            raise asyncio.TimeoutError("Timeout to read") from err


class MsgIDPair(object):
    __slots__ = [
        'last_id',
        'curr_id',
    ]

    def __init__(self, last_id: int, curr_id: int) -> None:
        self.last_id = last_id
        self.curr_id = curr_id

    def update_msg_id(self, curr_id: int) -> None:
        """
        更新msg_id

        Args:
            curr_id (int): 当前消息的msg_id
        """

        self.last_id = self.curr_id
        self.curr_id = curr_id


class MsgIDManager(object):
    __slots__ = [
        'priv_gid',
        'gid2mid',
    ]

    def __init__(self) -> None:
        self.priv_gid: int = None
        self.gid2mid: Dict[int, MsgIDPair] = None

    def update_msg_id(self, group_id: int, msg_id: int) -> None:
        """
        更新group_id对应的msg_id

        Args:
            group_id (int): 消息组id
            msg_id (int): 当前消息的msg_id
        """

        mid_pair = self.gid2mid.get(group_id, None)
        if mid_pair is not None:
            mid_pair.update_msg_id(msg_id)
        else:
            mid_pair = MsgIDPair(msg_id, msg_id)

    def get_msg_id(self, group_id: int) -> int:
        """
        获取group_id对应的msg_id

        Args:
            group_id (int): 消息组id

        Returns:
            int: 上一条消息的msg_id
        """

        return self.gid2mid[group_id].last_id

    def get_record_id(self) -> int:
        """
        获取record_id

        Returns:
            int: record_id
        """

        return self.get_msg_id(self.priv_gid) * 100 + 1


class WsCore(object):
    """
    保存websocket接口相关状态的核心容器
    """

    __slots__ = [
        'core',
        'connector',
        'heartbeat',
        'waiter',
        'callbacks',
        'websocket',
        'ws_dispatcher',
        '_req_id',
        'mid_manager',
        'loop',
    ]

    def __init__(
        self,
        core: TbCore,
        connector: aiohttp.TCPConnector,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.core = core
        self.connector = connector
        self.loop: asyncio.AbstractEventLoop = loop

        self.callbacks: Dict[int, TypeWebsocketCallback] = {}
        self.websocket: aiohttp.ClientWebSocketResponse = None

    async def __websocket_connect(self) -> None:
        from aiohttp import hdrs

        ws_url = yarl.URL.build(scheme="ws", host="im.tieba.baidu.com", port=8000)
        sec_key_bytes = binascii.b2a_base64(secrets.token_bytes(16), newline=False)
        headers = {
            hdrs.UPGRADE: "websocket",
            hdrs.CONNECTION: "upgrade",
            hdrs.SEC_WEBSOCKET_EXTENSIONS: "im_version=2.3",
            hdrs.SEC_WEBSOCKET_VERSION: "13",
            hdrs.SEC_WEBSOCKET_KEY: sec_key_bytes.decode('ascii'),
            hdrs.ACCEPT_ENCODING: "gzip",
            hdrs.HOST: "im.tieba.baidu.com:8000",
        }
        request = aiohttp.ClientRequest(
            hdrs.METH_GET,
            ws_url,
            headers=headers,
            loop=self.loop,
            proxy=self.core._proxy,
            proxy_auth=self.core._proxy_auth,
            ssl=False,
        )

        response = await _send_request(request, self.connector, False, 2 * 1024)

        if response.status != 101:
            raise HTTPStatusError(response.status, response.reason)

        try:
            conn = response.connection
            conn_proto = conn.protocol
            transport = conn.transport
            reader = aiohttp.FlowControlDataQueue(conn_proto, 1 << 16, loop=self.loop)
            conn_proto.set_parser(aiohttp.http.WebSocketReader(reader, 4 * 1024 * 1024), reader)
            writer = aiohttp.http.WebSocketWriter(conn_proto, transport, use_mask=True)
        except BaseException:
            response.close()
            raise
        else:
            self.websocket = aiohttp.ClientWebSocketResponse(
                reader,
                writer,
                'chat',
                response,
                TIME_CONFIG.ws_keepalive,
                True,
                True,
                self.loop,
                receive_timeout=TIME_CONFIG.ws_read,
                heartbeat=self.heartbeat,
            )

        self.ws_dispatcher = self.loop.create_task(self.__ws_dispatch(), name="ws_dispatcher")

    async def connect(self) -> None:
        """
        建立weboscket连接

        Raises:
            aiohttp.WSServerHandshakeError: websocket握手失败
        """

        self.waiter: Dict[int, asyncio.Future] = {}
        self._req_id = int(time.time())
        self.mid_manager: MsgIDManager = MsgIDManager()
        await self.__websocket_connect()

    async def reconnect(self) -> None:
        """
        重新建立weboscket连接

        Raises:
            aiohttp.WSServerHandshakeError: websocket握手失败
        """

        if not self.ws_dispatcher.done():
            self.ws_dispatcher.cancel()
        await self.__websocket_connect()

    async def close(self) -> None:
        if self.is_aviliable:
            await self.websocket.close()
            self.ws_dispatcher.cancel()

    def __default_callback(self, req_id: int, data: bytes) -> None:
        self.set_done(req_id, data)

    def __generate_default_callback(self, req_id: int) -> Callable[[asyncio.Future], Any]:
        """
        生成一个req_id对应的默认回调

        Args:
            req_id (int): 唯一请求id

        Returns:
            Callable[[asyncio.Future], Any]: 回调
        """

        def done_callback(_):
            del self.waiter[req_id]

        return done_callback

    def register(self, req_id: int) -> WsResponse:
        """
        将一个req_id注册到等待器 此方法会创建Future对象

        Args:
            req_id (int): 请求id

        Returns:
            WsResponse: websocket响应
        """

        data_future = self.loop.create_future()
        data_future.add_done_callback(self.__generate_default_callback(req_id))
        self.waiter[req_id] = data_future
        return WsResponse(data_future, TIME_CONFIG.ws_read)

    def set_done(self, req_id: int, data: bytes) -> None:
        """
        将req_id对应的Future设置为已完成

        Args:
            req_id (int): 请求id
            data (bytes): 填入的数据
        """

        data_future = self.waiter.get(req_id, None)
        if data_future is None:
            return
        data_future.set_result(data)

    async def __ws_dispatch(self) -> None:
        try:
            async for msg in self.websocket:
                data, cmd, req_id = parse_ws_bytes(self.core, msg.data)
                res_callback = self.callbacks.get(cmd, None)
                if res_callback is None:
                    self.__default_callback(req_id, data)
                else:
                    self.loop.create_task(res_callback(self, data, req_id))

        except asyncio.CancelledError:
            return

    @property
    def is_aviliable(self) -> bool:
        """
        websocket是否可用
        """

        return not (self.websocket is None or self.websocket._writer.transport.is_closing())

    @property
    def req_id(self) -> int:
        """
        用作请求参数的id

        Note:
            每个websocket请求都有一个唯一的req_id
            每次调用都会使其自增1
        """

        self._req_id += 1
        return self._req_id

    async def send(self, data: bytes, cmd: int, *, compress: bool = False, encrypt: bool = True) -> WsResponse:
        """
        将protobuf序列化结果打包发送

        Args:
            data (bytes): 待发送的数据
            cmd (int): 请求的cmd类型
            compress (bool, optional): 是否需要gzip压缩. Defaults to False.
            encrypt (bool, optional): 是否需要aes加密. Defaults to True.

        Returns:
            WsResponse: websocket响应对象

        Raises:
            asyncio.TimeoutError: 发送超时
        """

        req_id = self.req_id
        req_data = pack_ws_bytes(self.core, data, cmd, req_id, compress=compress, encrypt=encrypt)
        response = self.register(req_id)

        try:
            with async_timeout.timeout(TIME_CONFIG.ws_send):
                await self.websocket.send_bytes(req_data)
        except asyncio.TimeoutError as err:
            response._cancel()
            raise asyncio.TimeoutError("Timeout to send") from err
        else:
            return response