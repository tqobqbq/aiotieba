import yarl

from ...const import APP_BASE_HOST, APP_INSECURE_SCHEME
from ...core import HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import UserInfo_guinfo_app
from .protobuf import GetUserInfoReqIdl_pb2, GetUserInfoResIdl_pb2

CMD = 303024


def pack_proto(user_id: int) -> bytes:
    req_proto = GetUserInfoReqIdl_pb2.GetUserInfoReqIdl()
    req_proto.data.user_id = user_id

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> UserInfo_guinfo_app:
    res_proto = GetUserInfoResIdl_pb2.GetUserInfoResIdl()
    res_proto.ParseFromString(body)

    if error_code := res_proto.error.errorno:
        raise TiebaServerError(error_code, res_proto.error.errmsg)

    user_proto = res_proto.data.user
    user = UserInfo_guinfo_app(user_proto)

    return user


async def request_http(http_core: HttpCore, user_id: int) -> UserInfo_guinfo_app:
    data = pack_proto(user_id)

    request = pack_proto_request(
        http_core,
        yarl.URL.build(
            scheme=APP_INSECURE_SCHEME, host=APP_BASE_HOST, path="/c/u/user/getuserinfo", query_string=f"cmd={CMD}"
        ),
        data,
    )

    __log__ = "user_id={user_id}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=1024)
    return parse_body(body)


async def request_ws(ws_core: WsCore, user_id: int) -> UserInfo_guinfo_app:
    data = pack_proto(user_id)

    __log__ = "user_id={user_id}"  # noqa: F841

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
