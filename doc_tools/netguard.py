"""The only network code in this package. It exists for check_site and nothing else.
It refuses addresses that point into your own network (home router, other computers, cloud metadata), also after redirects.
Loopback (localhost) is allowed so you can check a site you are building."""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request


class Blocked(Exception):
    pass


def check_url(url: str) -> str:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise Blocked("only http and https addresses are allowed")
    if u.username or u.password:
        raise Blocked("addresses with a login in them are not allowed")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise Blocked(f"cannot find {u.hostname}: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_loopback:
            continue
        if not ip.is_global:
            raise Blocked(f"{u.hostname} points into a private network ({ip}); refused")
    return url


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(_Redirects)


def open_url(req: urllib.request.Request, timeout: float):
    check_url(req.full_url)
    return OPENER.open(req, timeout=timeout)
