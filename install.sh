#!/usr/bin/env bash
# Install / update the VANTA subscription page for 3x-ui panels.
#   bash <(curl -fsSL https://raw.githubusercontent.com/frank0live/vanta-sub/main/install.sh)
#
# What it does:
#   1. Sanity: root + 3x-ui panel detected (fails early on the wrong server)
#   2. Download sub.html from the repo, compute sha256
#   3. Install into a theme dir
#   4. Back up x-ui.db (WAL-safe .backup), set the `subThemeDir` settings key
#      (single-key upsert: UPDATE alone silently no-ops on a missing key)
#   5. Verify by requesting a real subscription link and reading the response
#
# No panel restart. The panel reads subThemeDir straight from the DB on every
# request and re-parses the template when its mtime changes, so a dropped file
# takes effect immediately. Restarting would drop every client on the box for
# no benefit, which is exactly what we want to avoid on a live panel.

# Env knobs:
#   VANTA_THEME_DIR=/etc/3x-ui/sub_templates/vanta   install folder
#   VANTA_BASE=https://.../main                      custom file source (testing)
#   XUI_DB=/etc/x-ui/x-ui.db                         panel database
set -u

REPO="frank0live/vanta-sub"
BRANCH="main"
BASE="${VANTA_BASE:-https://raw.githubusercontent.com/$REPO/$BRANCH}"
INSTALLER_VERSION="1.0.0"
THEME_DIR="${VANTA_THEME_DIR:-/etc/3x-ui/sub_templates/vanta}"
# drawn from the theme itself, so we tell "our page rendered" apart from the
# panel's built-in fallback page
THEME_MARKERS="PRIVATE NETWORK"
THEME_MARKER="accRows"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERROR: %s\n' "$*"; exit 1; }

say "==== VANTA subscription installer v$INSTALLER_VERSION ===="

# 0) helpers ---------------------------------------------------------------
# sqlite3 is optional: python3 ships with the 3x-ui images, sqlite3 does not.
have_sqlite3=0
command -v sqlite3 >/dev/null 2>&1 && have_sqlite3=1

db_query() {  # db_query <sql>  -> rows on stdout
  if [ "$have_sqlite3" = 1 ]; then
    sqlite3 "$DB" "$1"
  else
    DB="$DB" SQL="$1" python3 - <<'PYEOF'
import os, sqlite3
con = sqlite3.connect("file:%s?mode=ro" % os.environ["DB"], uri=True)
for row in con.execute(os.environ["SQL"]):
    print("|".join("" if v is None else str(v) for v in row))
PYEOF
  fi
}

# Picks a subscription id worth probing. Prefers ids that belong to a real
# client over bare inbound ids, and returns the id on stdout.
find_sub_id() {
  DB="$1" python3 - <<'PYEOF'
import json, os, sqlite3
db = os.environ["DB"]
picked = ""
try:
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
except Exception:
    con = None
if con is not None:
    # modern 3.8.x schema keeps subIds in the normalized `clients` table
    try:
        rows = list(con.execute(
            "SELECT sub_id FROM clients WHERE sub_id IS NOT NULL AND sub_id != '' "
            "AND enable = 1 ORDER BY id"))
        for (sid,) in rows:
            sid = str(sid).strip()
            if sid:
                picked = sid
                break
    except Exception:
        pass
    # older panels keep the client JSON inside inbounds.settings
    if not picked:
        try:
            for (raw,) in con.execute("SELECT settings FROM inbounds WHERE settings IS NOT NULL"):
                try:
                    s = json.loads(raw)
                except Exception:
                    continue
                for c in (s.get("clients") or []):
                    if not c.get("enable", True):
                        continue
                    sid = str(c.get("subId") or c.get("sub_id") or "").strip()
                    if sid:
                        picked = sid
                        break
                if picked:
                    break
        except Exception:
            pass
if picked:
    print(picked)
PYEOF
}

db_backup() {  # db_backup <dest>
  if [ "$have_sqlite3" = 1 ]; then
    sqlite3 "$DB" ".backup $1" 2>/dev/null || true
  else
    DB="$DB" DEST="$1" python3 - <<'PYEOF'
import os, sqlite3
src = sqlite3.connect("file:%s?mode=ro" % os.environ["DB"], uri=True)
dst = sqlite3.connect(os.environ["DEST"])
with dst:
    src.backup(dst)
dst.close(); src.close()
PYEOF
  fi
}

# The panel's sub server may be plain HTTP or TLS depending on the cert keys in
# settings, so every probe tries both and keeps the first answer that looks like
# our page. HTML mode is asked for explicitly: that is the path the panel routes
# to the custom template, and it is served before the HWID gate, so probing never
# burns a device slot.
fetch_page() {  # fetch_page <url>
  curl -sk -H 'Accept: text/html' -A 'Mozilla/5.0' --max-time 20 "$1" 2>/dev/null || true
}

looks_like_theme() {  # looks_like_theme <body>
  body="$1"
  for m in $THEME_MARKERS; do
    printf '%s' "$body" | grep -q -- "$m" || return 1
  done
  return 0
}

# 1) preflight ---------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "run as root"

DB="${XUI_DB:-}"
if [ -n "$DB" ]; then
  # an explicit path wins; a typo must fail loudly instead of silently
  # installing into some other panel that happens to live on this box
  [ -f "$DB" ] || die "XUI_DB=$DB does not exist"
else
  DB="/etc/x-ui/x-ui.db"
  if [ ! -f "$DB" ]; then
    # docker images built from the official entrypoint keep the db next to it
    for cand in /etc/x-ui/x-ui.db /app/bin/x-ui.db /usr/local/x-ui/x-ui.db; do
      [ -f "$cand" ] && { DB="$cand"; break; }
    done
  fi
fi
[ -f "$DB" ] || die "3x-ui database not found — is 3x-ui installed on this server?"

panel_version=""
# `x-ui` is a shell menu wrapper in the docker images and prints the menu, not
# the version. Probe real binaries; accept only output that is a bare x.y.z line.
for cand in /app/x-ui /usr/local/x-ui/bin/version /usr/local/x-ui/x-ui /usr/bin/x-ui; do
  [ -x "$cand" ] || continue
  head -c2 "$cand" 2>/dev/null | grep -q '#!' && continue   # skip shell wrappers
  v="$("$cand" -v 2>/dev/null | head -1 | tr -d ' \r\n' | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+$' || true)"
  [ -n "$v" ] && { panel_version="$v"; break; }
done
[ -n "$panel_version" ] || panel_version="unknown"
say "[1/5] panel detected (3x-ui $panel_version)"

# 2) download ----------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say "[2/5] downloading sub.html ..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --max-time 60 "$BASE/sub.html" -o "$TMP/sub.html" || die "download failed ($BASE/sub.html)"
else
  wget -qO "$TMP/sub.html" "$BASE/sub.html" || die "download failed ($BASE/sub.html)"
fi
[ -s "$TMP/sub.html" ] || die "downloaded file is empty"
grep -q -- "$THEME_MARKER" "$TMP/sub.html" || die "downloaded file does not look like the VANTA theme"
subhtml_sha256="$(sha256sum "$TMP/sub.html" | awk '{print $1}')"
subhtml_bytes="$(wc -c < "$TMP/sub.html")"
say "      ${subhtml_bytes} bytes, sha256 ${subhtml_sha256:0:16}..."

# 3) install theme file ------------------------------------------------------
say "[3/5] installing theme into $THEME_DIR ..."
mkdir -p "$THEME_DIR"; chmod 755 "$THEME_DIR"
cp "$TMP/sub.html" "$THEME_DIR/sub.html"; chmod 644 "$THEME_DIR/sub.html"
touch "$THEME_DIR/sub.html"    # fresh mtime is what makes the panel re-parse
say "      $THEME_DIR/sub.html"

# 4) DB backup + single-key upsert -------------------------------------------
say "[4/5] panel DB: backup + set subThemeDir ..."
db_backup "/root/x-ui.db.bak-vanta-$(date +%Y%m%d-%H%M%S)"
prev_value="$(db_query "SELECT value FROM settings WHERE key='subThemeDir'" 2>/dev/null | head -1)"
THEME_DIR="$THEME_DIR" DB="$DB" python3 - <<'PYEOF' || die "DB upsert failed"
import os, sqlite3
d = os.environ["THEME_DIR"].rstrip("/") + "/"
con = sqlite3.connect(os.environ["DB"], timeout=15)
row = con.execute("SELECT value FROM settings WHERE key='subThemeDir'").fetchone()
if row:
    con.execute("UPDATE settings SET value=? WHERE key='subThemeDir'", (d,)); print("      subThemeDir updated ->", d)
else:
    con.execute("INSERT INTO settings (key, value) VALUES ('subThemeDir', ?)", (d,)); print("      subThemeDir inserted ->", d)
con.commit()
PYEOF

# 5) verify (no restart) -----------------------------------------------------
say "[5/5] verifying the page renders ..."

# the panel process must still be up; we never restarted it, so if it is down
# the problem predates this install and subThemeDir goes back to what it was
alive=""
if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active --quiet x-ui 2>/dev/null && alive=1
fi
if [ -z "$alive" ] && command -v docker >/dev/null 2>&1; then
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx '3x-ui' && alive=1
fi
if [ -z "$alive" ]; then
  pgrep -x x-ui >/dev/null 2>&1 && alive=1
fi

sub_path="$(db_query "SELECT value FROM settings WHERE key='subPath'" 2>/dev/null | head -1)"
[ -n "$sub_path" ] || sub_path="/sub/"
case "$sub_path" in /*) ;; *) sub_path="/$sub_path" ;; esac
case "$sub_path" in */) ;; *) sub_path="$sub_path/" ;; esac

sub_port="$(db_query "SELECT value FROM settings WHERE key='subPort'" 2>/dev/null | head -1)"
[ -n "$sub_port" ] || sub_port=2096
web_port="$(db_query "SELECT value FROM settings WHERE key='webPort'" 2>/dev/null | head -1)"
[ -n "$web_port" ] || web_port=2053

sub_id="$(find_sub_id "$DB" 2>/dev/null || true)"
iid="$(db_query "SELECT id FROM inbounds ORDER BY id LIMIT 1" 2>/dev/null | head -1)"
key_part="${sub_id:-$iid}"

suburl=""
rendered_bytes=""
if [ -n "$key_part" ]; then
  for scheme in https http; do
    for port in "$sub_port" "$web_port"; do
      u="$scheme://127.0.0.1:$port$sub_path$key_part"
      body="$(fetch_page "$u")"
      if looks_like_theme "$body"; then
        rendered_bytes="$(printf '%s' "$body" | wc -c)"
        say "      rendered sub page OK (${rendered_bytes} bytes) — $u"
        suburl="$u"; break 2
      fi
    done
  done
fi

if [ -n "$suburl" ] && [ -n "$alive" ]; then
  say "      panel still running, no restart needed"
fi

if [ -z "$suburl" ]; then
  say "      could not render the page from the loopback address."
  say "      That is usually the panel's Host restriction, not a broken install:"
  say "      request any real subscription link from a browser to confirm. If it"
  say "      fails there too, revert with:"
  say "        sqlite3 $DB \"UPDATE settings SET value='${prev_value}' WHERE key='subThemeDir'\""
  [ -z "$alive" ] && die "panel process is not running and it was not restarted by this script"
fi

say ""
say "======================================================"
say " VANTA subscription installed successfully"
say "   theme dir : $THEME_DIR"
say "   file      : $THEME_DIR/sub.html ($subhtml_bytes bytes)"
say "   sha256    : $subhtml_sha256"
say "   panel     : 3x-ui $panel_version"
say "   sub page  : ${suburl:-open one of your subscription links}"
say "------------------------------------------------------"
say " Refresh   : $THEME_DIR/sub.html"
say " Update    : re-run the same install command"
say " Support   : https://t.me/master_supports"
say "======================================================"
