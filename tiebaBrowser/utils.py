# -*- coding:utf-8 -*-
__all__ = ('Browser',)

import hashlib
import re
import sys
from io import BytesIO

import requests as req
from bs4 import BeautifulSoup
from PIL import Image

from .config import config
from .data_structure import *
from .logger import log


class Sessions(object):
    """
    保持会话

    参数:
        BDUSS_key: str 用于获取BDUSS
    """

    __slots__ = ['app', 'web', 'BDUSS', 'STOKEN']

    def __init__(self, BDUSS_key):

        self.app = req.Session()
        self.app.headers = req.structures.CaseInsensitiveDict({'Content-Type': 'application/x-www-form-urlencoded',
                                                               'User-Agent': 'bdtb for Android 7.9.2',
                                                               'Connection': 'Keep-Alive',
                                                               'Accept-Encoding': 'gzip',
                                                               'Accept': '*/*',
                                                               'Host': 'c.tieba.baidu.com',
                                                               })

        self.web = req.Session()
        self.web.headers = req.structures.CaseInsensitiveDict({'Host': 'tieba.baidu.com',
                                                               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:96.0) Gecko/20100101 Firefox/96.0',
                                                               'Accept': '*/*',
                                                               'Accept-Encoding': 'gzip, deflate, br',
                                                               'DNT': '1',
                                                               'Cache-Control': 'no-cache',
                                                               'Connection': 'keep-alive',
                                                               'Upgrade-Insecure-Requests': '1'
                                                               })

        self.renew_BDUSS(BDUSS_key)

    def close(self):
        self.app.close()
        self.web.close()

    def set_host(self, url):
        try:
            self.web.headers['Host'] = re.search('://(.+?)/', url).group(1)
        except AttributeError:
            return False
        else:
            return True

    def renew_BDUSS(self, BDUSS_key):
        """
        更新BDUSS

        参数:
            BDUSS_key: str
        """

        self.BDUSS = config['BDUSS'][BDUSS_key]
        self.STOKEN = config['STOKEN'].get(BDUSS_key, '')
        self.web.cookies = req.cookies.cookiejar_from_dict(
            {'BDUSS': self.BDUSS, 'STOKEN': self.STOKEN})


class Browser(object):
    """
    贴吧浏览、参数获取等API的封装
    Browser(BDUSS_key)

    参数:
        BDUSS_key: str 用于获取BDUSS
    """

    __slots__ = ['fid_dict',
                 'sessions']

    def __init__(self, BDUSS_key):

        self.fid_dict = {}
        self.sessions = Sessions(BDUSS_key)

    def close(self):
        pass

    def set_host(self, url):
        """
        设置消息头的host字段
        set_host(url)
        参数:
            url: str 待请求的地址
        """

        if self.sessions.set_host(url):
            return True
        else:
            log.warning(f"Wrong type of url `{url}`")
            return False

    @staticmethod
    def app_sign(payload: dict):
        """
        计算字典payload的贴吧客户端签名值sign
        """

        raw_list = [f"{key}={value}" for key, value in payload.items()]
        raw_list.append("tiebaclient!!!")
        raw_str = "".join(raw_list)

        md5 = hashlib.md5()
        md5.update(raw_str.encode('utf-8'))
        sign = md5.hexdigest().upper()

        return sign

    def get_tbs(self):
        """
        获取贴吧反csrf校验码tbs
        get_tbs()

        返回值:
            tbs: str 反csrf校验码tbs
        """

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.get(
                "http://tieba.baidu.com/dc/common/tbs", timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            tbs = main_json['tbs']

        except Exception as err:
            log.error(f"Failed to get tbs reason: {err}")
            tbs = ''

        return tbs

    def get_fid(self, tieba_name):
        """
        通过贴吧名获取forum_id
        get_fid(tieba_name)

        参数:
            tieba_name: str 贴吧名

        返回值:
            fid: int 该贴吧的forum_id
        """

        fid = self.fid_dict.get(tieba_name, None)

        if not fid:
            try:
                self.set_host("http://tieba.baidu.com/")
                res = self.sessions.web.get("http://tieba.baidu.com/f/commit/share/fnameShareApi", params={
                                            'fname': tieba_name, 'ie': 'utf-8'}, timeout=(3, 10))

                if res.status_code != 200:
                    raise ValueError("status code is not 200")

                main_json = res.json()
                if int(main_json['no']):
                    raise ValueError(main_json['error'])

                fid = int(main_json['data']['fid'])

            except Exception as err:
                error_msg = f"Failed to get fid of {tieba_name} reason:{err}"
                log.critical(error_msg)
                raise ValueError(error_msg)

            self.fid_dict[tieba_name] = fid

        return fid

    def get_userinfo(self, id):
        """
        通过用户名或昵称或portrait获取用户信息
        get_userinfo(id)

        参数:
            id: str user_name或nick_name或portrait

        返回值:
            user: UserInfo 用户信息
        """

        if id.startswith('tb.'):
            params = {'id': id}
        else:
            params = {'un': id}

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.get(
                "https://tieba.baidu.com/home/get/panel", params=params, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['no']):
                raise ValueError(main_json['error'])

            data = main_json['data']
            sex = data['sex']
            if sex == 'male':
                gender = 1
            elif sex == 'female':
                gender = 2
            else:
                gender = 0
            user = UserInfo(user_name=data['name'],
                            nick_name=data['name_show'],
                            portrait=data['portrait'],
                            user_id=data['id'],
                            gender=gender,
                            is_vip=bool(data['vipInfo']))

        except Exception as err:
            log.error(f"Failed to get UserInfo of {id} reason:{err}")
            user = UserInfo()

        return user

    def get_userinfo_weak(self, id):
        """
        通过用户名或昵称或portrait获取简略版用户信息
        由于api的编码限制，返回结果仅包含user_id和portrait
        get_userinfo_weak(id)

        参数:
            id: str user_name或nick_name或portrait

        返回值:
            user: UserInfo 用户信息
        """

        if id.startswith('tb.'):
            params = {'id': id}
        else:
            params = {'un': id, 'ie': 'utf-8'}

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.get(
                "http://tieba.baidu.com/i/sys/user_json", params=params, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()

            data = main_json['creator']
            user = UserInfo(user_id=data['id'],
                            portrait=data['portrait'])

        except Exception as err:
            log.error(f"Failed to get UserInfo of {id} reason:{err}")
            user = UserInfo()

        return user

    def uid2userinfo(self, user_id):
        """
        通过user_id获取简略版用户信息（不包含gender）
        uid2userinfo(user_id)

        参数:
            user_id: int

        返回值:
            user: UserInfo 用户信息
        """

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.get(
                "http://tieba.baidu.com/im/pcmsg/query/getUserInfo", params={'chatUid': user_id}, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['errno']):
                raise ValueError(main_json['errmsg'])

            data = main_json['chatUser']
            user = UserInfo(user_name=data['uname'],
                            nick_name=data['show_nickname'],
                            user_id=user_id,
                            portrait=data['portrait'])

        except Exception as err:
            log.error(f"Failed to get UserInfo of {user_id} reason:{err}")
            user = UserInfo()

        return user

    def get_threads(self, tieba_name, pn=1, rn=30):
        """
        使用客户端api获取首页帖子
        get_threads(tieba_name,pn=1,rn=30)

        参数:
            tieba_name: str 贴吧名
            pn: int 页码
            rn: int 每页帖子数

        返回值:
            threads: Threads
        """

        payload = {'_client_version': '7.9.2',
                   'kw': tieba_name,
                   'pn': pn,
                   'rn': rn
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/f/frs/page", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

            threads = Threads(main_json)

        except Exception as err:
            log.error(f"Failed to get threads of {tieba_name} reason:{err}")
            threads = Threads()

        return threads

    def get_posts(self, tid, pn=1, rn=30):
        """
        使用客户端api获取主题帖内回复
        get_posts(tid,pn=1,rn=30)

        参数:
            tid: int 主题帖tid
            pn: int 页码
            rn: int 每页帖子数

        返回值:
            has_next: bool 是否还有下一页
            posts: Posts
        """

        payload = {'_client_version': '7.9.2',
                   'kz': tid,
                   'pn': pn,
                   'rn': rn
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/f/pb/page", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

            posts = Posts(main_json)

        except Exception as err:
            log.error(f"Failed to get posts of {tid} reason:{err}")
            posts = Posts()

        return posts

    def get_comments(self, tid, pid, pn=1):
        """
        使用客户端api获取楼中楼回复
        get_comments(tid,pid,pn=1)

        参数:
            tid: int 主题帖tid
            pid: int 回复pid
            pn: int 页码

        返回值:
            has_next: bool 是否还有下一页
            comments: Comments
        """

        payload = {'_client_version': '7.9.2',
                   'kz': tid,
                   'pid': pid,
                   'pn': pn
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/f/pb/floor", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

            comments = Comments(main_json)

        except Exception as err:
            log.error(f"Failed to get comments of {pid} in {tid} reason:{err}")
            comments = Comments()

        return comments

    def block(self, tieba_name, user, day, reason=''):
        """
        使用客户端api的封禁，支持小吧主、语音小编封10天
        block(tieba_name,user,day,reason='null')

        参数:
            tieba_name: str 吧名
            user: UserInfo 待封禁用户信息
            day: int 封禁天数
            reason: str 封禁理由（可选）

        返回值:
            flag: bool 操作是否成功
            user: UserInfo 补充后的用户信息
        """

        if not user.user_name:
            if user.portrait:
                user = self.get_userinfo(user.portrait)
            elif user.nick_name:
                user = self.get_userinfo(user.nick_name)
            else:
                log.error(f"Empty params in {tieba_name}")
                return False, user

        payload = {'BDUSS': self.sessions.BDUSS,
                   '_client_version': '7.9.2',
                   'day': day,
                   'fid': self.get_fid(tieba_name),
                   'nick_name': user.nick_name if user.nick_name else user.user_name,
                   'ntn': 'banid',
                   'portrait': user.portrait,
                   'post_id': 'null',
                   'reason': reason,
                   'tbs': self.get_tbs(),
                   'un': user.user_name,
                   'word': tieba_name,
                   'z': '9998732423',
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/c/bawu/commitprison", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

        except Exception as err:
            log.error(
                f"Failed to block {user.logname} in {tieba_name} reason:{err}")
            return False, user

        log.info(
            f"Successfully blocked {user.logname} in {tieba_name} for {payload['day']} days")
        return True, user

    def unblock(self, tieba_name, id):
        """
        解封用户
        unblock(tieba_name,id)

        参数:
            tieba_name: str 所在贴吧名
            id: str 用户名或昵称或portrait

        返回值:
            flag: bool 操作是否成功
        """

        user = self.get_userinfo(id)

        payload = {'fn': tieba_name,
                   'fid': self.get_fid(tieba_name),
                   'block_un': user.user_name,
                   'block_uid': user.user_id,
                   'block_nickname': user.nick_name,
                   'tbs': self.get_tbs()
                   }

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.post(
                "https://tieba.baidu.com/mo/q/bawublockclear", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['no']):
                raise ValueError(main_json['error'])

        except Exception as err:
            log.error(
                f"Failed to unblock {user.logname} in {tieba_name}. reason:{err}")
            return False

        log.info(f"Successfully unblocked {user.logname} in {tieba_name}")
        return True

    def del_thread(self, tieba_name, tid, is_frs_mask=False):
        """
        删除主题帖
        del_thread(tieba_name,tid)

        参数:
            tieba_name: str 帖子所在的贴吧名
            tid: int 待删除的主题帖tid
            is_frs_mask: bool False则删帖，True则屏蔽帖，默认为False

        返回值:
            flag: bool 操作是否成功
        """

        payload = {'BDUSS': self.sessions.BDUSS,
                   '_client_version': '7.9.2',
                   'fid': self.get_fid(tieba_name),
                   'is_frs_mask': int(is_frs_mask),
                   'tbs': self.get_tbs(),
                   'z': tid
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/c/bawu/delthread", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

        except Exception as err:
            log.error(
                f"Failed to delete thread {tid} in {tieba_name} reason:{err}")
            return False

        log.info(
            f"Successfully deleted thread {tid} hide:{is_frs_mask} in {tieba_name}")
        return True

    def del_post(self, tieba_name, tid, pid):
        """
        删除回复
        del_post(tieba_name,tid,pid)

        参数:
            tieba_name: str 帖子所在的贴吧名
            tid: int 回复所在的主题帖tid
            pid: int 待删除的回复pid

        返回值:
            flag: bool 操作是否成功
        """

        payload = {'BDUSS': self.sessions.BDUSS,
                   '_client_version': '7.9.2',
                   'fid': self.get_fid(tieba_name),
                   'pid': pid,
                   'tbs': self.get_tbs(),
                   'z': tid
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/c/bawu/delpost", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

        except Exception as err:
            log.error(
                f"Failed to delete post {pid} in {tid} in {tieba_name}. reason:{err}")
            return False

        log.info(f"Successfully deleted post {pid} in {tid} in {tieba_name}")
        return True

    def blacklist_add(self, tieba_name, id):
        """
        添加用户至黑名单
        blacklist_add(tieba_name,name)

        参数:
            tieba_name: str 所在贴吧名
            id: str 用户名或昵称或portrait

        返回值:
            flag: bool 操作是否成功
        """

        user = self.get_userinfo_weak(id)
        payload = {'tbs': self.get_tbs(),
                   'user_id': user.user_id,
                   'word': tieba_name,
                   'ie': 'utf-8'
                   }

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.post(
                "http://tieba.baidu.com/bawu2/platform/addBlack", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['errno']):
                raise ValueError(main_json['errmsg'])

        except Exception as err:
            log.error(
                f"Failed to add {user.logname} to black_list in {tieba_name}. reason:{err}")
            return False

        log.info(
            f"Successfully added {user.logname} to black_list in {tieba_name}")
        return True

    def blacklist_cancels(self, tieba_name, ids):
        """
        解除黑名单
        blacklist_cancels(tieba_name,ids)

        参数:
            tieba_name: str 所在贴吧名
            ids: List[str] 用户名或昵称或portrait的列表

        返回值:
            flag: bool 操作是否成功
        """

        payload = {'ie': 'utf-8',
                   'word': tieba_name,
                   'tbs': self.get_tbs(),
                   'list[]': []}

        for id in ids:
            user = self.get_userinfo_weak(id)
            if user.user_id:
                payload['list[]'].append(user.user_id)
        if not payload['list[]']:
            return False

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.post(
                "http://tieba.baidu.com/bawu2/platform/cancelBlack", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['errno']):
                raise ValueError(main_json['errmsg'])

        except Exception as err:
            log.error(
                f"Failed to delete {ids} from black_list in {tieba_name}. reason:{err}")
            return False

        log.info(f"Successfully deleted {ids} from black_list in {tieba_name}")
        return True

    def blacklist_cancel(self, tieba_name, id):
        """
        解除黑名单
        blacklist_cancel(tieba_name,id)

        参数:
            tieba_name: str 所在贴吧名
            id: str 用户名或昵称

        返回值:
            flag: bool 操作是否成功
        """

        if tieba_name and id:
            return self.blacklist_cancels(tieba_name, [str(id), ])
        else:
            return False

    def recover(self, tieba_name, tid, pid=0, is_frs_mask=False):
        """
        恢复帖子
        recover(tieba_name,tid,pid=0)

        参数:
            tieba_name: str 帖子所在的贴吧名
            tid: int 回复所在的主题帖tid
            pid: int 待恢复的回复pid
            is_frs_mask: bool False则恢复删帖，True则取消屏蔽帖，默认为False

        返回值:
            flag: bool 操作是否成功
        """

        payload = {'fn': tieba_name,
                   'fid': self.get_fid(tieba_name),
                   'tid_list[]': tid,
                   'pid_list[]': pid,
                   'type_list[]': 1 if pid else 0,
                   'is_frs_mask_list[]': int(is_frs_mask)
                   }

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.post(
                "https://tieba.baidu.com/mo/q/bawurecoverthread", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['no']):
                raise ValueError(main_json['error'])

        except Exception as err:
            log.error(
                f"Failed to recover tid:{tid} pid:{pid} in {tieba_name}. reason:{err}")
            return False

        log.info(
            f"Successfully recovered tid:{tid} pid:{pid} hide:{is_frs_mask} in {tieba_name}")
        return True

    def recommend(self, tieba_name, tid):
        """
        推荐上首页
        recommend(tieba_name,tid)

        参数:
            tieba_name: str 帖子所在贴吧名
            tid: int 待推荐的主题帖tid

        返回值:
            flag: bool 操作是否成功
        """

        payload = {'BDUSS': self.sessions.BDUSS,
                   '_client_version': '7.9.2',
                   'forum_id': self.get_fid(tieba_name),
                   'tbs': self.get_tbs(),
                   'thread_id': tid
                   }
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/c/bawu/pushRecomToPersonalized", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])
            if int(main_json['data']['is_push_success']) != 1:
                raise ValueError(main_json['data']['msg'])

        except Exception as err:
            log.error(
                f"Failed to recommend {tid} in {tieba_name}. reason:{err}")
            return False

        log.info(f"Successfully recommended {tid} in {tieba_name}")
        return True

    def refuse_appeals(self, tieba_name):
        """
        拒绝吧内所有解封申诉
        refuse_appeals(tieba_name)

        参数:
            tieba_name: str 所在贴吧名
        """

        def __appeal_handle(appeal_id, refuse=True):
            """
            拒绝或通过解封申诉
            __appeal_handle(appeal_id,refuse=True)

            参数:
                appeal_id: int 申诉请求的编号
                refuse: bool 是否拒绝申诉
            """

            payload = {'fn': tieba_name,
                       'fid': self.get_fid(tieba_name),
                       'status': 2 if refuse else 1,
                       'refuse_reason': 'Auto Refuse',
                       'appeal_id': appeal_id
                       }

            try:
                self.set_host("https://tieba.baidu.com/")
                res = self.sessions.web.post(
                    "https://tieba.baidu.com/mo/q/bawuappealhandle", data=payload, timeout=(3, 10))

                if res.status_code != 200:
                    raise ValueError("status code is not 200")

                main_json = res.json()
                if int(main_json['no']):
                    raise ValueError(main_json['error'])

            except Exception as err:
                log.error(
                    f"Failed to handle {appeal_id} in {tieba_name}. reason:{err}")
                return False

            log.info(
                f"Successfully handled {appeal_id} in {tieba_name}. refuse:{refuse}")
            return True

        def __get_appeal_list():
            """
            迭代返回申诉请求的编号(appeal_id)
            __get_appeal_list()

            迭代返回值:
                appeal_id: int 申诉请求的编号
            """

            params = {'fn': tieba_name,
                      'fid': self.get_fid(tieba_name)
                      }

            try:
                self.set_host("https://tieba.baidu.com/")
                while 1:
                    res = self.sessions.web.get(
                        "https://tieba.baidu.com/mo/q/bawuappeal", params=params, timeout=(3, 10))

                    if res.status_code != 200:
                        raise ValueError("status code is not 200")

                    soup = BeautifulSoup(res.text, 'lxml')

                    items = soup.find_all(
                        'li', class_='appeal_list_item j_appeal_list_item')
                    if not items:
                        return
                    for item in items:
                        appeal_id = int(
                            re.search('aid=(\d+)', item.a['href']).group(1))
                        yield appeal_id

            except Exception as err:
                log.error(
                    f"Failed to get appeal_list of {tieba_name}. reason:{err}")
                return

        for appeal_id in __get_appeal_list():
            __appeal_handle(appeal_id)

    def url2image(self, img_url):
        """
        从链接获取静态图像
        """
        try:
            if not re.search('\.(jpg|jpeg|png)', img_url):
                raise ValueError("Wrong image format")

            self.set_host(img_url)
            res = self.sessions.web.get(img_url, timeout=(3, 10))
            image = Image.open(BytesIO(res.content))

        except Exception as err:
            log.error(f"Failed to get image {img_url}. reason:{err}")
            image = None

        return image

    def get_ats(self):
        """
        获取@信息

        get_self_at()
        """

        payload = {'BDUSS': self.sessions.BDUSS}
        payload['sign'] = self.app_sign(payload)

        try:
            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/u/feed/atme", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

            ats = []
            for at_raw in main_json['at_list']:
                user_dict = at_raw['quote_user']
                user = UserInfo(user_name=user_dict['name'],
                                nick_name=user_dict['name_show'],
                                portrait=user_dict['portrait'])
                at = At(tieba_name=at_raw['fname'],
                        tid=int(at_raw['thread_id']),
                        pid=int(at_raw['post_id']),
                        text=at_raw['content'].lstrip(),
                        user=user,
                        create_time=int(at_raw['time']))
                ats.append(at)

        except Exception as err:
            log.error(f"Failed to get ats reason:{err}")
            ats = []

        return ats

    def get_adminlist(self, tieba_name):
        """
        获取吧务用户名列表
        get_adminlist(tieba_name)

        参数:
            tieba_name: str 所在贴吧名

        迭代返回值:
            user_name: str 用户名
        """

        try:
            self.set_host("http://tieba.baidu.com/")
            res = self.sessions.web.get(
                "http://tieba.baidu.com/f/bawu/admin_group", params={'kw': tieba_name, 'ie': 'utf-8'}, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            soup = BeautifulSoup(res.text, 'lxml')

            items = soup.find_all('a')
            if not items:
                return
            for item in items:
                user_name = item.text
                yield user_name

        except Exception as err:
            log.error(f"Failed to get admin list reason: {err}")

        return

    def get_rank(self, tieba_name, level_thre=4):
        """
        获得贴吧等级排行榜
        get_rank(tieba_name,level_thre=4)

        参数:
            tieba_name: str 贴吧名
            level_thre: int 等级下限阈值，等级大于等于该值的用户都会被采集

        迭代返回值:
            user_name: str 用户名
            level: int 等级
            exp: int 经验值
        """

        def __get_pn_rank(pn):
            """
            获得pn页的排行
            __get_pn_rank(pn)
            """

            try:
                res = self.sessions.web.get(
                    "http://tieba.baidu.com/f/like/furank", params={'kw': tieba_name, 'pn': pn, 'ie': 'utf-8'})

                if res.status_code != 200:
                    raise ValueError("status code is not 200")

                soup = BeautifulSoup(res.text, 'lxml')
                items = soup.select('tr[class^=drl_list_item]')
                if not items:
                    raise StopIteration

                for item in items:
                    user_name_item = item.td.next_sibling
                    user_name = user_name_item.text
                    level_item = user_name_item.next_sibling
                    # e.g. get level 16 from string "bg_lv16" by slicing [5:]
                    level = int(level_item.div['class'][0][5:])
                    if level < level_thre:
                        raise StopIteration
                    exp_item = level_item.next_sibling
                    exp = int(exp_item.text)
                    yield user_name, level, exp

            except StopIteration:
                raise
            except Exception as err:
                log.error(
                    f"Failed to get rank of {tieba_name} pn:{pn} reason:{err}")

        for pn in range(1, sys.maxsize):
            try:
                yield from __get_pn_rank(pn)
            except RuntimeError:  # need Python 3.7+ https://www.python.org/dev/peps/pep-0479/
                break

        return

    def get_member(self, tieba_name):
        """
        获得贴吧最新关注用户列表
        get_member(tieba_name)

        参数:
            tieba_name: str 贴吧名

        迭代返回值:
            user_name: str 用户名
            portrait: str
            level: int 等级
        """

        def __get_pn_member(pn):
            """
            获得pn页的最新关注用户列表
            __get_pn_member(pn)
            """

            try:
                res = self.sessions.web.get(
                    "http://tieba.baidu.com/bawu2/platform/listMemberInfo", params={'word': tieba_name, 'pn': pn, 'ie': 'utf-8'})

                if res.status_code != 200:
                    raise ValueError("status code is not 200")

                soup = BeautifulSoup(res.text, 'lxml')
                items = soup.find_all('div', class_='name_wrap')
                if not items:
                    raise StopIteration

                for item in items:
                    user_item = item.a
                    user_name = user_item['title']
                    portrait = user_item['href'][14:]
                    level_item = item.span
                    level = int(level_item['class'][1][12:])
                    yield user_name, portrait, level

            except StopIteration:
                raise
            except Exception as err:
                log.error(
                    f"Failed to get member of {tieba_name} pn:{pn} reason:{err}")

        for pn in range(1, sys.maxsize):
            try:
                yield from __get_pn_member(pn)
            except RuntimeError:  # need Python 3.7+ https://www.python.org/dev/peps/pep-0479/
                break

        return

    def set_privacy(self, tid, hide=True):
        """
        隐藏主题帖
        set_privacy(tid)

        参数:
            tid: int 主题帖tid
            hide: bool 是否设为隐藏

        返回值:
            flag: bool 操作是否成功
        """

        posts = self.get_posts(tid)
        if not posts:
            log.error(f"Failed to set privacy to {tid}")
            return False

        try:
            payload = {'BDUSS': self.sessions.BDUSS,
                       '_client_version': '7.9.2',
                       'forum_id': posts[0].fid,
                       'is_hide': int(hide),
                       'post_id': posts[0].pid,
                       'tbs': self.get_tbs(),
                       'thread_id': tid
                       }
            payload['sign'] = self.app_sign(payload)

            res = self.sessions.app.post(
                "http://c.tieba.baidu.com/c/c/thread/setPrivacy", data=payload, timeout=(3, 10))

            if res.status_code != 200:
                raise ValueError("status code is not 200")

            main_json = res.json()
            if int(main_json['error_code']):
                raise ValueError(main_json['error_msg'])

        except Exception as err:
            log.error(f"Failed to set privacy to {tid} reason:{err}")
            return False

        log.info(f"Successfully set privacy to {tid}")
        return True
