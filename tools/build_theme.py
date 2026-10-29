#!/usr/bin/env python3
"""
Build the VANTA subscription theme for 3x-ui from the standalone site.

Takes /root/vanta-sub/index.html (the static, data.json-driven site) and emits
sub.html: a single self-contained file that 3x-ui renders through html/template.

Why a build step instead of editing by hand: the theme has to inline a font
subset, a logo, the QR encoder and the config parser, and it has to swap the
data layer from fetch('data.json') to server-injected template values. Doing
that in one pass keeps the source site untouched and the output reproducible.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

SRC = Path("/root/vanta-sub")
OUT = Path(__file__).with_name("sub.html")
FONT_REG = Path("/tmp/font_regular.b64")
FONT_BOLD = Path("/tmp/font_bold.b64")

SUB_URL_PREFIX_FALLBACK = ""

# --------------------------------------------------------------------------- #
# pieces
# --------------------------------------------------------------------------- #

def read_site():
    html = (SRC / "index.html").read_text(encoding="utf-8")
    lines = html.splitlines(keepends=True)

    # the <style> block is lines 13..252 in the source
    start = next(i for i, l in enumerate(lines) if l.strip() == "<style>")
    end = next(i for i, l in enumerate(lines) if l.strip() == "</style>")
    style = "".join(lines[start + 1:end])

    # body markup runs from <body> up to the first <script> tag
    bstart = next(i for i, l in enumerate(lines) if l.strip() == "<body>")
    sstart = next(i for i, l in enumerate(lines) if "<script" in l)
    markup = "".join(lines[bstart:sstart])

    # the app JS lives between the last <script> and its closing tag
    js_start = next(i for i, l in enumerate(lines) if l.strip() == "<script>" and i > sstart)
    js_end = next(i for i, l in enumerate(lines) if l.strip() == "</script>" and i > js_start)
    js = "".join(lines[js_start + 1:js_end])

    return style, markup, js


def build_logo() -> str:
    """A compact square mark lifted from wordmark.svg, as a data URI."""
    svg = (SRC / "assets" / "wordmark.svg").read_text(encoding="utf-8")
    # reuse the gradient defs and the V mark group verbatim
    defs = re.search(r"<defs>([\s\S]*?)</defs>", svg).group(1)
    mark = re.search(r'<!-- mark -->\s*(<g[\s\S]*?</g>)', svg).group(1)
    out = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="152" height="152" '
        'viewBox="0 0 148 148" role="img" aria-label="VANTA">'
        f"<defs>{defs}</defs>{mark}</svg>"
    )
    b64 = base64.b64encode(out.encode()).decode()
    return "data:image/svg+xml;base64," + b64


def font_faces() -> str:
    reg = FONT_REG.read_text().strip()
    bold = FONT_BOLD.read_text().strip()
    return (
        "@font-face{font-family:Vazirmatn;font-style:normal;font-weight:400;"
        "font-display:swap;src:url(data:font/woff2;base64,"
        + reg
        + ") format('woff2')}\n"
        "@font-face{font-family:Vazirmatn;font-style:normal;font-weight:600 900;"
        "font-display:swap;src:url(data:font/woff2;base64,"
        + bold
        + ") format('woff2')}\n"
    )


# --------------------------------------------------------------------------- #
# the data layer
# --------------------------------------------------------------------------- #

# Emitted inside a <script>, so every panel value that reaches JS goes through
# Go's JS escaper: quoted scalars for strings, raw numbers for byte counts.
# Arrays use the range-in-backtick form (proven on this panel); the trailing
# newline per element is what lets the page split them back apart.
DATA_LAYER = r"""
/* ---------------------------------------------------------------
   Server-injected account data. The panel renders this file itself,
   so everything below arrives with the response: no fetch, no XHR,
   no second request, and nothing the client can spoof.
   --------------------------------------------------------------- */
const P = {
  sId:        "{{ .sId }}",
  subTitle:   `{{ .subTitle }}`,
  announce:   `{{ .announce }}`,
  support:    `{{ .subSupportUrl }}`,
  subUrl:     "{{ .subUrl }}",
  subJsonUrl: "{{ .subJsonUrl }}",
  subClashUrl:"{{ .subClashUrl }}",
  enabled:    "{{ .enabled }}" === "true",
  isOnline:   "{{ .isOnline }}" === "true",
  datepicker: "{{ .datepicker }}",
  subUpdates: {{ .subUpdates }},
  downloadByte: {{ .downloadByte }},
  uploadByte:   {{ .uploadByte }},
  totalByte:    {{ .totalByte }},
  expire:       {{ .expire }},
  lastOnline:   {{ .lastOnline }},
  emails: `{{ range .emails }}{{ . }}
{{ end }}`,
  links: `{{ range .links }}{{ . }}
{{ end }}`
};
P.emails = P.emails.split("\n").map(s => s.trim()).filter(Boolean);
P.links  = P.links.split("\n").map(s => s.trim()).filter(Boolean);

const APPS = __APPS__;
const BRAND_ICON = "__ICON__";

/* ---------------------------------------------------------------
   Subscription link parsing, ported from build.py so the theme no
   longer needs a pre-built data.json.
   --------------------------------------------------------------- */
const SCHEMES = ['vless','vmess','trojan','ss','hysteria2','hy2','tuic'];

function qs(str){
  const out = {};
  String(str || '').split('&').forEach(part => {
    if (!part) return;
    const i = part.indexOf('=');
    const k = i < 0 ? part : part.slice(0, i);
    const v = i < 0 ? '' : part.slice(i + 1);
    try { out[decodeURIComponent(k)] = decodeURIComponent(v); } catch(e){ out[k] = v; }
  });
  return out;
}

function b64decode(str){
  const s = String(str).replace(/-/g,'+').replace(/_/g,'/').replace(/\s+/g,'');
  const pad = s + '='.repeat((4 - s.length % 4) % 4);
  const bin = atob(pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder('utf-8').decode(bytes);
}

function parseLink(link){
  const scheme = link.split('://', 1)[0].toLowerCase();
  if (!SCHEMES.includes(scheme)) return null;
  const frag = link.includes('#') ? decodeURIComponent(link.slice(link.lastIndexOf('#') + 1)) : '';
  let info = null;
  try {
    if (scheme === 'vmess') {
      const j = JSON.parse(b64decode(link.split('://',1)[1].split('#',1)[0]));
      info = { protocol:'vmess', host:j.add || '', port:j.port || '',
               net:j.net || 'tcp', tls:(j.tls || 'none'),
               sni:j.sni || j.host || '' };
    } else {
      const body = link.split('://', 1)[1].split('#', 1)[0];
      const qi = body.indexOf('?');
      const pre = qi < 0 ? body : body.slice(0, qi);
      const q = qs(qi < 0 ? '' : body.slice(qi + 1));
      let hostport = pre.lastIndexOf('@') >= 0 ? pre.slice(pre.lastIndexOf('@') + 1) : pre;
      hostport = hostport.split('/', 1)[0];
      const colon = hostport.lastIndexOf(':');
      let host = colon < 0 ? hostport : hostport.slice(0, colon);
      const port = colon < 0 ? '' : hostport.slice(colon + 1);
      host = host.replace(/^\[|\]$/g, '');
      info = { protocol: scheme === 'ss' ? 'ss' : scheme, host, port,
               net: q.type || q.net || 'tcp',
               tls: q.security || (['trojan','hysteria2','hy2'].includes(scheme) ? 'tls' : 'none'),
               sni: q.sni || q.peer || q.host || '' };
    }
  } catch(e) {
    info = { protocol:scheme, host:'', port:'', net:'', tls:'', sni:'' };
  }
  if (!info) return null;
  info.name = frag || (info.host ? info.host + ':' + info.port : scheme.toUpperCase());
  info.link = link;
  return info;
}
"""


# --------------------------------------------------------------------------- #
# replacements in the app JS
# --------------------------------------------------------------------------- #

OLD_BOOT_RE = re.compile(
    r"async function boot\(\)\{[\s\S]*?\n\}", re.MULTILINE)

NEW_BOOT = r"""function boot(){
  const used  = (P.downloadByte || 0) + (P.uploadByte || 0);
  const total = P.totalByte || 0;
  const created = null;

  /* the hero card carries the two numbers a subscriber actually looks for */
  const quota  = total > 0 ? fa(humanBytes(total)) : 'نامحدود';
  const expLbl = P.expire ? 'تا ' + tsFa(P.expire) : 'بدون تاریخ انقضا';

  DATA = {
    brand: {
      name: 'VANTA',
      subtitle: 'PRIVATE NETWORK',
      plan: quota,
      planCode: expLbl,
      tagline: 'عبور امن از سانسور',
      logo: BRAND_ICON
    },
    user: {
      username: P.emails[0] || P.sId,
      id: P.sId,
      status: P.enabled ? 'active' : 'inactive',
      used: used,
      total: total,
      lifetime: used,
      expire: P.expire || null,
      created: created,
      online: P.lastOnline || null,
      sub_url: P.subUrl || ''
    },
    configs: P.links.map(parseLink).filter(Boolean),
    apps: APPS,
    build: 'VANTA · بهروزرسانی هر ' + fa(P.subUpdates || 12) + ' ساعت'
  };

  if (P.subTitle) { document.title = P.subTitle; }

  render();
  announceInit();
}"""


ANNOUNCE_CSS = """
/* announce strip — only painted when the panel has something to say */
.announce{display:none;align-items:flex-start;gap:9px;margin:12px 0 2px;
  padding:11px 13px;border-radius:var(--radius-sm);
  background:linear-gradient(135deg,rgba(255,125,3,.13),rgba(76,201,240,.07));
  border:1px solid rgba(255,125,3,.28);font-size:12.5px;line-height:1.85}
.announce.on{display:flex}
.announce svg{width:15px;height:15px;flex-shrink:0;margin-top:4px;
  stroke:var(--brand-2);fill:none;stroke-width:2}
.announce b{color:var(--brand-2)}
"""

ANNOUNCE_JS = r"""
/* the panel's announcement text is operator-controlled; painted as text
   so it can never inject markup into the page */
function announceInit(){
  const box = $('announce');
  if (!box) return;
  if (!P.announce) return;
  $('announceTxt').textContent = P.announce;
  box.classList.add('on');
}
"""

ANNOUNCE_MARKUP = """  <div class="announce" id="announce">
    <svg viewBox="0 0 24 24"><path d="M12 8v5"/><circle cx="12" cy="16.5" r=".6"/><circle cx="12" cy="12" r="9"/></svg>
    <div id="announceTxt"></div>
  </div>
"""


def transform_js(js: str, apps_json: str, icon: str) -> str:
    js = js.replace("</script", "<\\/script")
    if not OLD_BOOT_RE.search(js):
        raise SystemExit("could not locate boot() in the source app JS")
    js = OLD_BOOT_RE.sub(NEW_BOOT, js, count=1)

    # the data layer goes above everything else, after the helper block
    anchor = "let DATA = null;"
    if anchor not in js:
        raise SystemExit("could not locate the DATA declaration")
    layer = DATA_LAYER.replace("__APPS__", apps_json).replace("__ICON__", icon)
    js = js.replace(anchor, layer + "\n\n" + anchor, 1)

    # announce helper, appended at the end so hoisting is irrelevant
    js = js.rstrip() + "\n" + ANNOUNCE_JS
    return js


def main():
    style, markup, js = read_site()
    icon = build_logo()
    apps = json.loads((SRC / "apps.json").read_text(encoding="utf-8"))
    apps_json = json.dumps(apps, ensure_ascii=False)

    js = transform_js(js, apps_json, icon)
    qr = (SRC / "assets" / "qrcode.js").read_text(encoding="utf-8")
    if "{{" in qr or "</script" in qr:
        raise SystemExit("qrcode.js is not template-safe")

    # announce strip sits right under the ambient background, above the wrap
    markup = markup.replace(
        '<div class="amb"></div><div class="grid"></div>',
        '<div class="amb"></div><div class="grid"></div>',
        1)
    markup = markup.replace('<div class="wrap">',
                            '<div class="wrap">\n' + ANNOUNCE_MARKUP, 1)

    style = font_faces() + style + ANNOUNCE_CSS

    head = (
        '<!DOCTYPE html>\n'
        '<html lang="fa" dir="rtl" data-theme="vanta">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        '<meta name="color-scheme" content="dark">\n'
        '<meta name="theme-color" content="#060a14">\n'
        '<meta name="referrer" content="no-referrer">\n'
        '<title>{{ if .subTitle }}{{ .subTitle }}{{ else }}VANTA · پنل اشتراک{{ end }}</title>\n'
        '<style>\n' + style + '\n</style>\n'
        '</head>\n'
    )

    body = markup.rstrip() + "\n"
    tail = (
        "<script>\n" + qr.rstrip() + "\n</script>\n"
        "<script>\n" + js.rstrip() + "\n</script>\n"
        "</body>\n</html>\n"
    )

    out = head + body + tail

    # the panel parses this through html/template; a stray "{{" outside our
    # own actions would break the render. The only "</script" allowed are the
    # two closing tags of the blocks we emit ourselves.
    stripped = re.sub(r"\{\{[^}]*\}\}", "", out)
    if "{{" in stripped:
        raise SystemExit("stray '{{' found in output")
    if stripped.count("</script") != 2:
        raise SystemExit(
            f"expected exactly 2 '</script' (our own), found {stripped.count('</script')}")

    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes, "
          f"{(len(out.splitlines())):,} lines, {out.count('{{')} actions)")


if __name__ == "__main__":
    main()
