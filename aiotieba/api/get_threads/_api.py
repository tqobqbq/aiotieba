import yarl

from ...const import APP_BASE_HOST, APP_INSECURE_SCHEME, MAIN_VERSION
from ...core import Account, HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import Threads
from .protobuf import FrsPageReqIdl_pb2, FrsPageResIdl_pb2

CMD = 301001


def pack_proto(core: Account, fname: str, pn: int, rn: int, sort: int, is_good: bool) -> bytes:
    req_proto = FrsPageReqIdl_pb2.FrsPageReqIdl()
    req_proto.data.common._client_type = 2
    req_proto.data.common._client_version = MAIN_VERSION
    req_proto.data.fname = fname
    req_proto.data.pn = pn
    req_proto.data.rn = 105
    req_proto.data.rn_need = rn if rn > 0 else 1
    req_proto.data.is_good = is_good
    req_proto.data.sort = sort

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> Threads:
    res_proto = FrsPageResIdl_pb2.FrsPageResIdl()
    res_proto.ParseFromString(body)

    if code := res_proto.error.errorno:
        raise TiebaServerError(code, res_proto.error.errmsg)

    data_proto = res_proto.data
    threads = Threads(data_proto)

    return threads


async def request_http(http_core: HttpCore, fname: str, pn: int, rn: int, sort: int, is_good: bool) -> Threads:
    data = pack_proto(http_core.account, fname, pn, rn, sort, is_good)

    request = pack_proto_request(
        http_core,
        yarl.URL.build(scheme=APP_INSECURE_SCHEME, host=APP_BASE_HOST, path="/c/f/frs/page", query_string=f"cmd={CMD}"),
        data,
    )

    __log__ = "fname={fname}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=256 * 1024)
    return parse_body(body)


async def request_ws(ws_core: WsCore, fname: str, pn: int, rn: int, sort: int, is_good: bool) -> Threads:
    data = pack_proto(ws_core.account, fname, pn, rn, sort, is_good)

    __log__ = "fname={fname}"  # noqa: F841

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
