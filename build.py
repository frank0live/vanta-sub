#!/usr/bin/env python3
"""
VANTA — data.json builder.

Pulls a subscription URL, decodes the payload, and writes data.json next to
index.html. The page never talks to the panel directly: it only reads this
file, so the page stays a plain static site (works on GitHub Pages, any CDN,
or even file:// with a tiny local server).

Usage
-----
    python3 build.py "https://panel.example.com/sub/TOKEN"
    python3 build.py "https://..." --name VANTA --plan PREMIUM --tagline "عبور امن از سانسور"
    python3 build.py --demo          # regenerate the sample data.json

Options
-------
    --out PATH        output file (default: data.json next to this script)
    --name NAME       brand name shown in the header
    --subtitle TEXT   small caps line under the brand
    --plan TEXT       plan label on the hero card (e.g. PREMIUM)
    --plan-code TEXT  short code under the plan label (e.g. 80GB / 30D)
    --tagline TEXT    one-line description
    --logo PATH       relative path to the logo image
    --timeout N       HTTP timeout in seconds (default 20)
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #
def fetch(url: str, timeout: int = 20):
    """Return (body_text, headers). Falls back to unverified TLS for panels
    that ship self-signed certificates (common on subscription hosts)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
        headers = {k.lower(): v for k, v in r.headers.items()}
    return raw, headers


def decode_payload(raw: bytes) -> str:
    """Subscription payloads are base64 (sometimes URL-safe, sometimes with
    line breaks). If it already looks like plain links, keep it as-is."""
    text = raw.decode("utf-8", "replace").strip()
    if "://" in text:
        return text
    compact = re.sub(r"\s+", "", text)
    compact += "=" * (-len(compact) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            out = decoder(compact).decode("utf-8", "replace")
            if "://" in out:
                return out
        except Exception:
            continue
    return text


def parse_userinfo(headers: dict) -> dict:
    """Subscription-Userinfo: upload=..; download=..; total=..; expire=.."""
    raw = headers.get("subscription-userinfo", "")
    out = {}
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k and v.strip().isdigit():
            out[k.strip()] = int(v.strip())
    return out


# --------------------------------------------------------------------------- #
# link parsing
# --------------------------------------------------------------------------- #
def split_link(link: str):
    """Return (scheme, fragment) with the fragment URL-decoded."""
    scheme = link.split("://", 1)[0].lower()
    frag = ""
    if "#" in link:
        frag = urllib.parse.unquote(link.rsplit("#", 1)[1])
    return scheme, frag


def parse_vmess(link: str) -> dict:
    body = link.split("://", 1)[1].split("#", 1)[0]
    body += "=" * (-len(body) % 4)
    j = json.loads(base64.b64decode(body).decode("utf-8", "replace"))
    return {
        "protocol": "vmess",
        "host": j.get("add", ""),
        "port": j.get("port", ""),
        "net": j.get("net", "tcp"),
        "tls": (j.get("tls") or "none"),
        "sni": j.get("sni") or j.get("host") or "",
    }


def parse_uri(link: str) -> dict:
    """vless / trojan / ss / hysteria2 style: scheme://userinfo@host:port?query"""
    scheme, _ = split_link(link)
    body = link.split("://", 1)[1]
    body = body.split("#", 1)[0]
    pre, _, qs = body.partition("?")
    hostport = pre.rsplit("@", 1)[-1]
    # strip any trailing path (trojan/ws style)
    hostport = hostport.split("/", 1)[0]
    host, _, port = hostport.rpartition(":")
    if not host:  # no port given
        host, port = hostport, ""
    q = dict(urllib.parse.parse_qsl(qs))
    return {
        "protocol": "ss" if scheme == "ss" else scheme,
        "host": host.strip("[]"),
        "port": port,
        "net": q.get("type") or q.get("net") or "tcp",
        "tls": q.get("security") or ("tls" if scheme in ("trojan", "hysteria2", "hy2") else "none"),
        "sni": q.get("sni") or q.get("peer") or q.get("host") or "",
    }


def parse_configs(text: str) -> list[dict]:
    configs = []
    for line in text.splitlines():
        link = line.strip()
        if "://" not in link:
            continue
        scheme, frag = split_link(link)
        if scheme not in ("vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic"):
            continue
        try:
            info = parse_vmess(link) if scheme == "vmess" else parse_uri(link)
        except Exception:
            info = {"protocol": scheme, "host": "", "port": "", "net": "", "tls": "", "sni": ""}
        info["name"] = frag or f"{info['host']}:{info['port']}"
        info["link"] = link
        configs.append(info)
    return configs


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(args) -> dict:
    if args.demo:
        demo_path = Path(__file__).with_name("demo.json")
        return json.loads(demo_path.read_text(encoding="utf-8"))

    raw, headers = fetch(args.url, timeout=args.timeout)
    text = decode_payload(raw)
    configs = parse_configs(text)
    ui = parse_userinfo(headers)

    used = ui.get("download", 0) + ui.get("upload", 0)
    total = ui.get("total", 0)
    expire = ui.get("expire", 0)

    now = int(time.time())
    data = {
        "brand": {
            "name": args.name,
            "subtitle": args.subtitle,
            "plan": args.plan,
            "planCode": args.plan_code,
            "tagline": args.tagline,
            "logo": args.logo,
        },
        "user": {
            "username": headers.get("x-username") or "",
            "id": headers.get("x-user-id") or "",
            "status": "active",
            "used": used,
            "total": total,
            "lifetime": used,
            "expire": expire or None,
            "created": None,
            "online": now,
            "sub_url": args.url,
        },
        "configs": configs,
        "apps": json.loads(Path(__file__).with_name("apps.json").read_text(encoding="utf-8")),
        "build": "built " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    return data


def main():
    p = argparse.ArgumentParser(description="Build VANTA data.json from a subscription URL")
    p.add_argument("url", nargs="?", help="subscription URL")
    p.add_argument("--demo", action="store_true", help="write the bundled sample data")
    p.add_argument("--out", default=None)
    p.add_argument("--name", default="VANTA")
    p.add_argument("--subtitle", default="PRIVATE NETWORK")
    p.add_argument("--plan", default="PREMIUM")
    p.add_argument("--plan-code", default="")
    p.add_argument("--tagline", default="عبور امن از سانسور")
    p.add_argument("--logo", default=None,
                   help="optional SQUARE brand icon (e.g. assets/icon.png); "
                        "omit to use the built-in SVG monogram")
    p.add_argument("--timeout", type=int, default=20)
    args = p.parse_args()

    if not args.demo and not args.url:
        p.error("give a subscription URL or --demo")

    try:
        data = build(args)
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else Path(__file__).with_name("data.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}  ({len(data['configs'])} configs, "
          f"{data['user']['used']} / {data['user']['total']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
