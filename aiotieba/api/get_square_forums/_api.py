import yarl

from ...const import APP_BASE_HOST, APP_SECURE_SCHEME, MAIN_VERSION
from ...core import Account, HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import SquareForums
from .protobuf import GetForumSquareReqIdl_pb2, GetForumSquareResIdl_pb2

CMD = 309653


def pack_proto(core: Account, cname: str, pn: int, rn: int) -> bytes:
    req_proto = GetForumSquareReqIdl_pb2.GetForumSquareReqIdl()
    req_proto.data.common.BDUSS = core._BDUSS
    req_proto.data.common._client_version = MAIN_VERSION
    req_proto.data.class_name = cname
    req_proto.data.pn = pn
    req_proto.data.rn = rn

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> SquareForums:
    res_proto = GetForumSquareResIdl_pb2.GetForumSquareResIdl()
    res_proto.ParseFromString(body)

    if code := res_proto.error.errorno:
        raise TiebaServerError(code, res_proto.error.errmsg)

    data_proto = res_proto.data
    square_forums = SquareForums(data_proto)

    return square_forums


async def request_http(http_core: HttpCore, cname: str, pn: int, rn: int) -> SquareForums:
    data = pack_proto(http_core.account, cname, pn, rn)

    request = pack_proto_request(
        http_core,
        yarl.URL.build(
            scheme=APP_SECURE_SCHEME, host=APP_BASE_HOST, path="/c/f/forum/getForumSquare", query_string=f"cmd={CMD}"
        ),
        data,
    )

    __log__ = "cname={cname}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=16 * 1024)
    return parse_body(body)


async def request_ws(ws_core: WsCore, cname: str, pn: int, rn: int) -> SquareForums:
    data = pack_proto(ws_core.account, cname, pn, rn)

    __log__ = "cname={cname}"  # noqa: F841

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
