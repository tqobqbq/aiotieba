import yarl

from ...const import APP_BASE_HOST, APP_INSECURE_SCHEME, MAIN_VERSION
from ...core import Account, HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import Comments
from .protobuf import PbFloorReqIdl_pb2, PbFloorResIdl_pb2

CMD = 302002


def pack_proto(core: Account, tid: int, pid: int, pn: int, is_floor: bool) -> bytes:
    req_proto = PbFloorReqIdl_pb2.PbFloorReqIdl()
    req_proto.data.common._client_type = 2
    req_proto.data.common._client_version = MAIN_VERSION
    req_proto.data.tid = tid
    if is_floor:
        req_proto.data.spid = pid
    else:
        req_proto.data.pid = pid
    req_proto.data.pn = pn

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> Comments:
    res_proto = PbFloorResIdl_pb2.PbFloorResIdl()
    res_proto.ParseFromString(body)

    if code := res_proto.error.errorno:
        raise TiebaServerError(code, res_proto.error.errmsg)

    data_proto = res_proto.data
    comments = Comments(data_proto)

    return comments


async def request_http(http_core: HttpCore, tid: int, pid: int, pn: int, is_floor: bool) -> Comments:
    data = pack_proto(http_core.account, tid, pid, pn, is_floor)

    request = pack_proto_request(
        http_core,
        yarl.URL.build(scheme=APP_INSECURE_SCHEME, host=APP_BASE_HOST, path="/c/f/pb/floor", query_string=f"cmd={CMD}"),
        data,
    )

    __log__ = "tid={tid} pid={pid}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=8 * 1024)
    return parse_body(body)


async def request_ws(ws_core: WsCore, tid: int, pid: int, pn: int, is_floor: bool) -> Comments:
    data = pack_proto(ws_core.account, tid, pid, pn, is_floor)

    __log__ = "tid={tid} pid={pid}"  # noqa: F841

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
