import yarl

from ...const import APP_BASE_HOST, APP_SECURE_SCHEME, MAIN_VERSION
from ...core import Account, HttpCore, WsCore
from ...exception import TiebaServerError
from ...request import pack_proto_request, send_request
from ._classdef import Posts
from .protobuf import PbPageReqIdl_pb2, PbPageResIdl_pb2

CMD = 302001


def pack_proto(
    core: Account,
    tid: int,
    pn: int,
    rn: int,
    sort: int,
    only_thread_author: bool,
    with_comments: bool,
    comment_sort_by_agree: bool,
    comment_rn: int,
    is_fold: bool,
) -> bytes:
    req_proto = PbPageReqIdl_pb2.PbPageReqIdl()
    req_proto.data.common._client_type = 2
    req_proto.data.common._client_version = MAIN_VERSION
    req_proto.data.tid = tid
    req_proto.data.pn = pn
    req_proto.data.rn = rn if rn > 1 else 2
    req_proto.data.sort = sort
    req_proto.data.only_thread_author = only_thread_author
    req_proto.data.is_fold = is_fold
    if with_comments:
        req_proto.data.common.BDUSS = core._BDUSS
        req_proto.data.with_comments = with_comments
        req_proto.data.comment_sort_by_agree = comment_sort_by_agree
        req_proto.data.comment_rn = comment_rn

    return req_proto.SerializeToString()


def parse_body(body: bytes) -> Posts:
    res_proto = PbPageResIdl_pb2.PbPageResIdl()
    res_proto.ParseFromString(body)

    if code := res_proto.error.errorno:
        raise TiebaServerError(code, res_proto.error.errmsg)

    data_proto = res_proto.data
    posts = Posts(data_proto)

    return posts


async def request_http(
    http_core: HttpCore,
    tid: int,
    pn: int,
    rn: int,
    sort: int,
    only_thread_author: bool,
    with_comments: bool,
    comment_sort_by_agree: bool,
    comment_rn: int,
    is_fold: bool,
) -> Posts:
    data = pack_proto(
        http_core.account,
        tid,
        pn,
        rn,
        sort,
        only_thread_author,
        with_comments,
        comment_sort_by_agree,
        comment_rn,
        is_fold,
    )

    request = pack_proto_request(
        http_core,
        yarl.URL.build(scheme=APP_SECURE_SCHEME, host=APP_BASE_HOST, path="/c/f/pb/page", query_string=f"cmd={CMD}"),
        data,
    )

    __log__ = "tid={tid}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=128 * 1024)
    return parse_body(body)


async def request_ws(
    ws_core: WsCore,
    tid: int,
    pn: int,
    rn: int,
    sort: int,
    only_thread_author: bool,
    with_comments: bool,
    comment_sort_by_agree: bool,
    comment_rn: int,
    is_fold: bool,
) -> Posts:
    data = pack_proto(
        ws_core.account,
        tid,
        pn,
        rn,
        sort,
        only_thread_author,
        with_comments,
        comment_sort_by_agree,
        comment_rn,
        is_fold,
    )

    __log__ = "tid={tid}"  # noqa: F841

    response = await ws_core.send(data, CMD)
    return parse_body(await response.read())
