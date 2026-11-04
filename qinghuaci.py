# -*- coding: utf-8 -*-
"""
青花瓷影视 https://m.cj1nym.com/  狼壳(TVBox) 单条导入 py 源

用法：把本文件放进 /sdcard/PY源/，在狼壳里「单条导入」本 py 文件，不要配 json。
说明：站点是 App 风格的 Next.js 站，数据走站内接口 /api/mw-movie/*，
      接口强制签名(client-type / sign / t / deviceId)，本文件按站点真实算法实现。
仅使用 Python 标准库；模块级 import 与 init 阶段不联网。
"""

import sys
import json
import time
import uuid
import gzip
import ssl
import hashlib
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


HOST = "https://m.cj1nym.com"
API = HOST + "/api/mw-movie"
SIGN_KEY = "cb808529bae6b6be45ecfab29a4889bc"
UA = ("Mozilla/5.0 (Linux; Android 13; NX789J) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

REQ_TIMEOUT = 8          # 单次请求硬超时（秒）
OK_TTL = 300             # 成功结果缓存（秒）
BAD_TTL = 60             # 失败结果短缓存（秒）
PAGE_SIZE = 36


class Spider(_BaseSpider):

    def __init__(self):
        try:
            super(Spider, self).__init__()
        except Exception:
            pass
        self._uuid = str(uuid.uuid4())
        self._cache = {}

    # ---------------- 壳要求的固定方法 ----------------

    def getName(self):
        return "青花瓷影视"

    def init(self, extend=""):
        # 不联网
        return

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return (".m3u8" in u) or (".mp4" in u)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._cache = {}

    # ---------------- 缓存 ----------------

    def _cache_get(self, key):
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > (OK_TTL if val else BAD_TTL):
            self._cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key, val):
        self._cache[key] = (time.time(), val)

    # ---------------- 签名与请求 ----------------

    def _sign_headers(self, path, params):
        data = {}
        for k, v in (params or {}).items():
            if v is None:
                continue
            if isinstance(v, (list, dict, tuple)):
                continue
            if v == "":
                continue
            data[k] = v
        ts = str(int(time.time() * 1000))
        raw = "key=" + SIGN_KEY + "&t=" + ts
        if data:
            part = "&".join("%s=%s" % (k, data[k]) for k in sorted(data.keys()))
            raw = part + "&" + raw
        md5hex = hashlib.md5(raw.encode("utf-8")).hexdigest()
        sign = hashlib.sha1(md5hex.encode("utf-8")).hexdigest()
        return {
            "client-type": "3",
            "sign": sign,
            "t": ts,
            "deviceId": self._uuid,
            "authorization": "",
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        }

    def _open(self, url, headers):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers or {})
        resp = urllib.request.urlopen(req, timeout=REQ_TIMEOUT, context=ctx)
        raw = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return raw

    def _fetch(self, path, params=None, ttl=None):
        key = (path, json.dumps(params or {}, sort_keys=True, ensure_ascii=False))
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        url = API + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        out = None
        try:
            raw = self._open(url, self._sign_headers(path, params))
            body = json.loads(raw.decode("utf-8", "replace"))
            if isinstance(body, dict) and body.get("code") == 200:
                out = body.get("data")
        except Exception:
            out = None
        self._cache_set(key, out)
        return out

    # ---------------- 数据整形 ----------------

    def _mk_item(self, it):
        return {
            "vod_id": str(it.get("vodId") or ""),
            "vod_name": str(it.get("vodName") or ""),
            "vod_pic": str(it.get("vodPic") or ""),
            "vod_remarks": str(it.get("vodRemarks") or it.get("vodVersion") or ""),
        }

    def _collect(self, obj, out=None, seen=None):
        if out is None:
            out, seen = [], set()
        if isinstance(obj, dict):
            vid = obj.get("vodId")
            name = obj.get("vodName")
            if vid is not None and name:
                if vid not in seen:
                    seen.add(vid)
                    out.append(self._mk_item(obj))
            else:
                for v in obj.values():
                    self._collect(v, out, seen)
        elif isinstance(obj, list):
            for v in obj:
                self._collect(v, out, seen)
        return out

    def _norm_list(self, lst):
        out = []
        for it in (lst or []):
            if isinstance(it, dict) and it.get("vodId") is not None:
                out.append(self._mk_item(it))
        return out

    def _paged(self, data, pg):
        if not isinstance(data, dict):
            return None, None, None
        lst = data.get("list")
        if isinstance(lst, list):
            lst = self._norm_list(lst)
        else:
            lst = self._collect(data)
        total = data.get("totalCount")
        pages = data.get("totalPage")
        try:
            pages = int(pages)
        except Exception:
            pages = None
        try:
            total = int(total)
        except Exception:
            total = None
        return lst, pages, total

    # ---------------- 壳接口 ----------------

    def homeContent(self, filter=False):
        classes = []
        t0 = time.time()
        cats = self._fetch("/anonymous/get/filer/type")
        if isinstance(cats, list):
            for c in cats:
                if not isinstance(c, dict):
                    continue
                if c.get("typeJumpurl"):
                    continue
                tid = c.get("typeId")
                name = c.get("typeName")
                if tid is None or not name:
                    continue
                classes.append({"type_id": str(tid), "type_name": str(name)})
        videos = []
        home = self._fetch("/anonymous/v1/home/all/list", {"clientType": 3, "pageNum": 1})
        if home is not None:
            videos = self._collect(home)
        self._last_home_cost = round(time.time() - t0, 2)
        return {"class": classes, "filters": {}, "list": videos}

    def homeVideoContent(self):
        home = self._fetch("/anonymous/v1/home/all/list", {"clientType": 3, "pageNum": 1})
        return {"list": self._collect(home) if home is not None else []}

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        params = {"pageNum": page, "pageSize": PAGE_SIZE, "type1": str(tid), "sort": 1, "sortBy": 1}
        for k, v in (extend or {}).items():
            if v not in (None, "") and k not in params:
                params[k] = v
        data = self._fetch("/anonymous/video/list", params)
        lst, pages, total = self._paged(data, page)
        if not lst:
            return {"list": [], "page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0}
        return {
            "list": lst,
            "page": page,
            "pagecount": pages if pages else page,
            "limit": PAGE_SIZE,
            "total": total if total else len(lst),
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        data = self._fetch("/anonymous/video/searchByWordPageable",
                           {"keyword": key, "pageNum": page, "pageSize": 18})
        lst, pages, total = self._paged(data, page)
        if not lst:
            return {"list": [], "page": page, "pagecount": page, "limit": 18, "total": 0}
        return {
            "list": lst,
            "page": page,
            "pagecount": pages if pages else page,
            "limit": 18,
            "total": total if total else len(lst),
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or "")
        data = self._fetch("/anonymous/video/detail", {"id": vid})
        if not isinstance(data, dict):
            return {"list": []}
        name = str(data.get("vodName") or "")
        eps = data.get("episodeList")
        play_url = []
        if isinstance(eps, list):
            for e in eps:
                if not isinstance(e, dict):
                    continue
                nid = e.get("nid")
                if nid is None:
                    continue
                label = str(e.get("name") or "")
                if not label:
                    label = "第%s集" % (e.get("sort") or len(play_url) + 1)
                play_url.append("%s$%s|%s" % (label.replace("$", ""), vid, nid))
        if not play_url:
            play_url.append("立即播放$%s|" % vid)

        version = str(data.get("vodVersion") or "")
        from_name = "青花瓷4K" if "4K" in version.upper() else ("青花瓷" + version if version else "青花瓷")

        remark = str(data.get("vodRemarks") or "")
        content = str(data.get("vodContent") or "")
        actor = str(data.get("vodActor") or "")
        director = str(data.get("vodDirector") or "")
        area = str(data.get("vodArea") or "")
        year = str(data.get("vodYear") or "")
        score = data.get("vodScore")
        extra = []
        if year:
            extra.append(year)
        if area:
            extra.append(area)
        if director:
            extra.append("导演:" + director)
        if actor:
            extra.append("主演:" + actor)
        if score:
            extra.append("评分:%s" % score)
        des = content
        if extra:
            des = content + "\n" + " / ".join(extra)

        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": str(data.get("vodPic") or ""),
            "vod_remarks": remark or version,
            "vod_content": des,
            "vod_play_from": from_name,
            "vod_play_url": "#".join(play_url),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        vid, _, nid = str(id or "").partition("|")
        out = {"parse": 0, "playUrl": "", "url": "", "header": {"User-Agent": UA}}
        data = self._fetch("/anonymous/v2/video/episode/url",
                           {"clientType": 3, "id": vid, "nid": nid}, ttl=60)
        items = (data or {}).get("list") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return out
        good = [i for i in items if isinstance(i, dict) and str(i.get("url") or "").startswith("http")]
        if not good:
            return out
        # 线路排序：名字带 4K 的排最前，其余保持源站原顺序（稳定排序）
        good.sort(key=lambda i: 0 if "4K" in str(i.get("resolutionName") or "").upper() else 1)
        picked = good[0]
        out["url"] = str(picked.get("url") or "")
        # 实测：该 CDN 对部分请求会返 403（与 header 无关，样片三种 header 结果一致），
        # 按手机浏览器习惯带上移动 UA，不带 Referer（实测两者都不比空 header 差）
        out["header"] = {"User-Agent": UA}
        return out


if __name__ == "__main__":
    s = Spider()
    s.init()
    print(json.dumps(s.homeContent(), ensure_ascii=False)[:400])
