<p align="center">
  <img src="assets/wordmark.svg" width="620" alt="VANTA — Private Network">
</p>

<p align="center">
  <b>A subscription page that doesn't look like every other subscription page.</b><br>
  <sub>Dark. Fast. Zero build step. One JSON file.</sub>
</p>

<p align="center">
  <img src="docs/home.png" width="330" alt="VANTA — account view">
</p>

---

## What this is

Most subscription pages are the same three templates recolored: a panel dumps a
base64 blob, a page parses it, and everyone gets the same rounded card with the
same ring in the same corner.

VANTA is a **static, dependency-free front end** for any subscription URL —
Marzban, Marzneshin, PasarGuard, 3x-ui, Hiddify, or a hand-rolled panel. It reads
usage, expiry and configs, and renders them in a layout built around one idea:
**the number you actually care about should be the biggest thing on screen.**

No framework. No bundler. No node_modules. One HTML file, one JSON file, one
Python script that fills the JSON in.

## Features

**Account view**
- Radial gauge showing **remaining** volume (not used — you open this page to
  know how much you have left, not how much you burned)
- Remaining / used / total in one row, colour-coded by meaning
- Live countdown to expiry in days · hours · minutes, turning red inside 3 days
- Subscription link with one-tap copy and a QR modal
- Full account table: username, ID, status, created, last connection, expiry,
  daily average — every value tappable to copy

**Configs view**
- Country chip per server, derived from the panel's own naming (`DE`, `FI`,
  `IR`, …) — text chips, not emoji flags, so they render identically on every
  device instead of showing tofu boxes
- Protocol badge (VLESS / VMess / Trojan / Shadowsocks / Hysteria2)
- Instant search across name, host and protocol
- Per-config copy and QR

**Apps view**
- Curated client list per platform, edited in `apps.json`

**Under the hood**
- Persian-first: RTL layout, Persian digits, Jalali dates via `Intl`
- Works on any static host — GitHub Pages, Cloudflare Pages, Netlify, a VPS, or
  `python3 -m http.server` for local preview
- `data.json` is fetched at runtime, so you can regenerate it on a cron and the
  page picks up new numbers on refresh — no redeploy
- Respects `prefers-reduced-motion`, uses `dvh` for mobile viewport, safe-area
  insets for notched phones

## Quick start

```bash
git clone https://github.com/frank0live/vanta-sub
cd vanta-sub
python3 build.py --demo          # writes data.json with sample data
python3 -m http.server 8080      # open http://localhost:8080
```

Then point it at a real subscription:

```bash
python3 build.py "https://your-panel.com/sub/TOKEN" \
  --plan "PREMIUM" \
  --plan-code "80GB / 30D" \
  --tagline "عبور امن از سانسور"
```

`build.py` fetches the URL, decodes the payload (base64 or plain), parses
`vless://`, `vmess://`, `trojan://`, `ss://`, `hysteria2://` links, reads the
`subscription-userinfo` header, and writes `data.json`.

### Options

| flag | meaning |
|---|---|
| `--out PATH` | where to write (default `data.json`) |
| `--name` | brand name in the header |
| `--subtitle` | small caps line under the name |
| `--plan` | plan label on the hero card |
| `--plan-code` | short code under it, e.g. `80GB / 30D` |
| `--tagline` | one-line description |
| `--logo` | optional **square** brand icon; omit for the built-in SVG monogram |
| `--timeout` | HTTP timeout in seconds |

## Deploy

Any static host works — there is no server-side code.

**GitHub Pages**

```bash
git add data.json && git commit -m "update usage" && git push
```

Then Settings → Pages → deploy from `main` / root.

**Refresh the numbers automatically**

```cron
*/30 * * * * cd /srv/vanta-sub && python3 build.py "https://panel/sub/TOKEN" && git commit -am "usage" && git push
```

The page refetches `data.json` with `cache: 'no-store'` on every load, so a push
is enough — no cache busting needed.

**Never commit a real token.** If you host this publicly, generate `data.json`
server-side and keep the subscription URL out of git. The demo token in
`demo.json` is fake.

## Customising

Everything visual is in `index.html` — a single `<style>` block and one
`<script>` block, both commented by section.

```css
:root{
  --brand:#ff7d03;      /* accent */
  --bg:#060a14;         /* page background */
  --card:rgba(17,25,44,.72);
}
```

To change the wordmark, edit `.brand-name` and the `<title>`. To use your own
logo, pass `--logo assets/your-icon.png` — it expects a **square** image, since
the header slot is a 44×44 tile.

To add or remove clients, edit `apps.json`:

```json
{ "name": "v2rayNG", "desc": "اندروید · محبوب‌ترین کلاینت", "icon": "🤖",
  "url": "https://github.com/2dust/v2rayNG/releases/latest" }
```

## `data.json` shape

```jsonc
{
  "brand": { "name": "VANTA", "plan": "PREMIUM", "planCode": "80GB / 30D",
             "tagline": "…", "subtitle": "PRIVATE NETWORK", "logo": null },
  "user":  { "username": "…", "id": "…", "status": "active",
             "used": 19327352832, "total": 85899345920, "lifetime": 19327352832,
             "expire": 1795123200, "created": 1792531200, "online": 1795046400,
             "sub_url": "https://panel/sub/TOKEN", "daily_avg": 644245094 },
  "configs": [ { "protocol": "vless", "name": "DE · Frankfurt",
                 "host": "de1.example.net", "port": 443,
                 "net": "ws", "tls": "tls", "sni": "de1.example.net",
                 "link": "vless://…" } ],
  "apps":  [ { "name": "…", "desc": "…", "icon": "🤖", "url": "…" } ],
  "build": "built 2026-10-21 22:00 UTC"
}
```

Bytes are plain integers. `expire` / `created` / `online` are Unix seconds.
Any field you leave out is skipped in the UI rather than rendering as `undefined`.

## Browser support

Anything from 2021 onward. Uses `dvh`, `:has`-free CSS, optional chaining, and
`Intl.DateTimeFormat` with `calendar: 'persian'`. Falls back gracefully if the
Persian calendar is unavailable.

## License

MIT — see [LICENSE](LICENSE).

The Vazirmatn webfont is loaded from jsDelivr under the SIL Open Font License.
`assets/qrcode.js` is [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
by Kazuhiko Arase, MIT.
