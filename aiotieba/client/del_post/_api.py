import httpx

from .._exception import TiebaServerError
from .._classdef.core import TiebaCore
from .._helper import APP_BASE_HOST, pack_form_request, parse_json, raise_for_status, sign, url


def pack_request(client: httpx.AsyncClient, core: TiebaCore, tbs: str, fid: int, pid: int) -> httpx.Request:

    data = [
        ('BDUSS', core.BDUSS),
        ('fid', fid),
        ('pid', pid),
        ('tbs', tbs),
        ('z', '6'),
    ]

    request = pack_form_request(
        client,
        url("http", APP_BASE_HOST, "/c/c/bawu/delpost"),
        sign(data),
    )

    return request


def parse_response(response: httpx.Response) -> None:
    raise_for_status(response)

    res_json = parse_json(response.content)
    if code := int(res_json['error_code']):
        raise TiebaServerError(code, res_json['error_msg'])
