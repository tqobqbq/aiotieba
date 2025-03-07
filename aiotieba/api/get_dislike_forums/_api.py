import yarl

from ...const import APP_BASE_HOST, APP_SECURE_SCHEME, MAIN_VERSION
from ...core import Account, HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import DislikeForums
from .protobuf import GetDislikeListReqIdl_pb2, GetDislikeListResIdl_pb2

CMD = 309692


def pack_proto(core: Account, pn: int, rn: int) -> bytes:
    req_proto = GetDislikeListReqIdl_pb2.GetDislikeListReqIdl()
    req_proto.data.common.BDUSS = core._BDUSS
    req_proto.data.common._client_version = MAIN_VERSION
    req_proto.data.pn = pn
    req_proto.data.rn = rn

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> DislikeForums:
    res_proto = GetDislikeListResIdl_pb2.GetDislikeListResIdl()
    res_proto.ParseFromString(body)

    if code := res_proto.error.errorno:
        raise TiebaServerError(code, res_proto.error.errmsg)

    data_proto = res_proto.data
    dislike_forums = DislikeForums(data_proto)

    return dislike_forums


async def request_http(http_core: HttpCore, pn: int, rn: int) -> DislikeForums:
    data = pack_proto(http_core.account, pn, rn)

    request = pack_proto_request(
        http_core,
        yarl.URL.build(
            scheme=APP_SECURE_SCHEME, host=APP_BASE_HOST, path="/c/u/user/getDislikeList", query_string=f"cmd={CMD}"
        ),
        data,
    )

    body = await send_request(request, http_core.network, read_bufsize=8 * 1024)
    return parse_body(body)


async def request_ws(ws_core: WsCore, pn: int, rn: int) -> DislikeForums:
    data = pack_proto(ws_core.account, pn, rn)

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
