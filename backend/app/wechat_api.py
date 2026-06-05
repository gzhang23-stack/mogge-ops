from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings

WECHAT_API_BASE = "https://api.weixin.qq.com/cgi-bin"


class WeChatApiError(RuntimeError):
    pass


def account_credentials(account_name: str) -> tuple[str, str]:
    credentials = get_settings().wechat_credentials(account_name)
    appid = str(credentials.get("appid") or "")
    appsecret = str(credentials.get("appsecret") or "")
    if not appid or not appsecret:
        raise WeChatApiError(f"{account_name} 未配置 appid/appsecret")
    return appid, appsecret


def get_access_token(account_name: str) -> str:
    appid, appsecret = account_credentials(account_name)
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{WECHAT_API_BASE}/token",
            params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
        )
        data = response.json()
    token = data.get("access_token")
    if not token:
        raise WeChatApiError(f"获取 access_token 失败：{data}")
    return str(token)


def post_wechat(endpoint: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        response = client.post(f"{WECHAT_API_BASE}{endpoint}", params={"access_token": token}, json=payload)
        data = response.json()
    if data.get("errcode"):
        raise WeChatApiError(f"微信接口调用失败：{data}")
    return data


def date_windows(start: date, end: date, max_days: int = 1) -> list[tuple[date, date]]:
    windows = []
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=max_days - 1), end)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return windows


def sync_article_datacube(account_name: str, start: date, end: date) -> list[dict[str, Any]]:
    token = get_access_token(account_name)
    rows: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for begin, finish in date_windows(start, end, 1):
        payload = {"begin_date": begin.isoformat(), "end_date": finish.isoformat()}
        summary = post_wechat("/datacube/getarticlesummary", token, payload).get("list", [])
        total = post_wechat("/datacube/getarticletotal", token, payload).get("list", [])
        share = post_wechat("/datacube/getusershare", token, payload).get("list", [])
        for item in summary:
            url = item.get("url") or item.get("msgid") or item.get("title", "")
            row = by_url.setdefault(
                str(url),
                {
                    "account_name": account_name,
                    "title": item.get("title") or f"{account_name} {begin.isoformat()} 图文",
                    "published_at": datetime.combine(begin, datetime.min.time()),
                    "source_url": item.get("url") or "",
                    "column_name": "",
                    "reads": 0,
                    "likes": 0,
                    "wows": 0,
                    "favorites": 0,
                    "shares": 0,
                    "comments": 0,
                    "new_followers": 0,
                    "unfollows": 0,
                },
            )
            row["reads"] = max(int(row["reads"]), int(item.get("int_page_read_count") or item.get("ori_page_read_count") or 0))
            row["likes"] = max(int(row["likes"]), int(item.get("like_num") or 0))
        for item in total:
            url = item.get("url") or item.get("msgid") or item.get("title", "")
            details = item.get("details") or []
            detail = details[-1] if details else item
            row = by_url.setdefault(
                str(url),
                {
                    "account_name": account_name,
                    "title": item.get("title") or f"{account_name} {begin.isoformat()} 图文",
                    "published_at": datetime.combine(begin, datetime.min.time()),
                    "source_url": item.get("url") or "",
                    "column_name": "",
                    "reads": 0,
                    "likes": 0,
                    "wows": 0,
                    "favorites": 0,
                    "shares": 0,
                    "comments": 0,
                    "new_followers": 0,
                    "unfollows": 0,
                },
            )
            row["reads"] = max(int(row["reads"]), int(detail.get("int_page_read_count") or detail.get("ori_page_read_count") or 0))
            row["likes"] = max(int(row["likes"]), int(detail.get("like_num") or 0))
            row["favorites"] = max(int(row["favorites"]), int(detail.get("add_to_fav_count") or 0))
        for item in share:
            title = item.get("title") or f"{account_name} {begin.isoformat()} 分享数据"
            url = item.get("url") or item.get("msgid") or title
            row = by_url.setdefault(
                str(url),
                {
                    "account_name": account_name,
                    "title": title,
                    "published_at": datetime.combine(begin, datetime.min.time()),
                    "source_url": item.get("url") or "",
                    "column_name": "",
                    "reads": 0,
                    "likes": 0,
                    "wows": 0,
                    "favorites": 0,
                    "shares": 0,
                    "comments": 0,
                    "new_followers": 0,
                    "unfollows": 0,
                },
            )
            row["shares"] = max(int(row["shares"]), int(item.get("share_count") or 0))
    rows.extend(by_url.values())
    return rows
