import yarl

from ...const import APP_BASE_HOST, APP_SECURE_SCHEME, MAIN_VERSION
from ...core import HttpCore
from ...exception import TiebaServerError
from ...helper import parse_json
from ...request import pack_form_request, send_request
from ._classdef import Follows


def parse_body(body: bytes) -> Follows:
    res_json = parse_json(body)
    if code := int(res_json['error_code']):
        raise TiebaServerError(code, res_json['error_msg'])

    follows = Follows(res_json)

    return follows


async def request(http_core: HttpCore, user_id: int, pn: int) -> Follows:
    data = [
        ('BDUSS', http_core.account._BDUSS),
        ('_client_version', MAIN_VERSION),
        ('pn', pn),
        ('uid', user_id),
    ]

    request = pack_form_request(
        http_core,
        yarl.URL.build(scheme=APP_SECURE_SCHEME, host=APP_BASE_HOST, path="/c/u/follow/followList"),
        data,
    )

    __log__ = "user_id={user_id}"  # noqa: F841

    body = await send_request(request, http_core.network, read_bufsize=8 * 1024)
    return parse_body(body)
