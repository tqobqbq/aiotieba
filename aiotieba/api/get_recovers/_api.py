import yarl

from ...const import WEB_BASE_HOST
from ...core import HttpCore
from ...exception import TiebaServerError
from ...helper import parse_json
from ...request import pack_web_get_request, send_request
from ._classdef import Recovers


def parse_body(body: bytes) -> Recovers:
    res_json = parse_json(body)
    if code := res_json['no']:
        raise TiebaServerError(code, res_json['error'])

    recovers = Recovers(res_json)

    return recovers


async def request(http_core: HttpCore, fname: str, fid: int, name: str, pn: int) -> Recovers:
    params = [
        ('fn', fname),
        ('fid', fid),
        ('word', name),
        ('is_ajax', '1'),
        ('pn', pn),
    ]

    request = pack_web_get_request(
        http_core,
        yarl.URL.build(scheme="https", host=WEB_BASE_HOST, path="/mo/q/bawurecover"),
        params,
    )

    __log__ = "fname={fname}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=64 * 1024)
    return parse_body(body)
