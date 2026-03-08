#!/usr/bin/env bash
# NeighbourTalk – Tailscale setup
# Run once after deploying the app:  bash setup_tailscale.sh
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${BLUE}[•]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
die()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}NeighbourTalk — Tailscale HTTPS Setup${NC}"
echo "────────────────────────────────────────"
echo ""

# ── 1. Install Tailscale if not present ───────────────────────────────────────
if command -v tailscale &>/dev/null; then
    ok "Tailscale already installed ($(tailscale version | head -1))"
else
    info "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    ok "Tailscale installed"
fi

# ── 2. Ensure tailscaled is running ───────────────────────────────────────────
sudo systemctl enable --now tailscaled 2>/dev/null || true
sleep 1
ok "tailscaled service enabled"

# ── 3. Authenticate (skipped if already connected) ────────────────────────────
TS_STATE=$(sudo tailscale status --json 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('BackendState',''))" \
    2>/dev/null || echo "")

if [[ "$TS_STATE" == "Running" ]]; then
    ok "Already authenticated with Tailscale"
else
    info "Starting Tailscale authentication..."
    echo ""
    warn "A URL will be printed below — open it in any browser to log in."
    echo ""
    sudo tailscale up
    echo ""
fi

# ── 4. Resolve Tailscale hostname ─────────────────────────────────────────────
TS_HOSTNAME=$(sudo tailscale status --json 2>/dev/null \
    | python3 -c \
      "import sys,json; d=json.load(sys.stdin); \
       print(d.get('Self',{}).get('DNSName','').rstrip('.'))" \
    2>/dev/null || echo "")

[[ -n "$TS_HOSTNAME" ]] || die "Could not get Tailscale hostname. Run 'tailscale status' to debug."
ok "Tailscale hostname: ${TS_HOSTNAME}"

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")

# ── 5. Configure Tailscale Serve (HTTPS → localhost:5000) ────────────────────
info "Configuring Tailscale Serve (https → localhost:5000)..."
# Tailscale CLI v1.56+ syntax
sudo tailscale serve --bg http://localhost:5000
ok "Tailscale Serve configured (config persists across reboots)"

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}────────────────────────────────────────────────────────────${NC}"
echo -e "${GREEN}${BOLD}  Done!${NC}"
echo -e "${GREEN}${BOLD}────────────────────────────────────────────────────────────${NC}"
echo ""
echo -e "  ${BOLD}HTTPS (Isaac's iPhone — via Tailscale):${NC}"
echo -e "  ${BLUE}https://${TS_HOSTNAME}/${NC}"
echo ""
echo -e "  ${BOLD}HTTP (any device on the same WiFi):${NC}"
echo -e "  ${BLUE}http://${LAN_IP}:5000/${NC}"
echo ""
echo -e "${YELLOW}${BOLD}Before the HTTPS URL works — do this in the Tailscale admin console:${NC}"
echo "  1. Open: https://login.tailscale.com/admin/dns"
echo "  2. Enable MagicDNS"
echo "  3. Under 'HTTPS Certificates', click Enable"
echo ""

# ── 7. Funnel option for neighbour's iOS device ───────────────────────────────
echo -e "${BOLD}Neighbour's iOS device?${NC}"
echo "  The Tailscale HTTPS URL above requires Tailscale to be installed"
echo "  on the accessing device. For the neighbour (no Tailscale install):"
echo ""
echo "  Option A — Android: the LAN HTTP URL works fine without Tailscale."
echo ""
echo "  Option B — iPhone: enable Tailscale Funnel to create a public"
echo "  HTTPS URL that any browser can open (no Tailscale needed on client):"
echo ""
echo "      sudo tailscale funnel --bg http://localhost:5000"
echo ""
echo "  Funnel URL (same as above): https://${TS_HOSTNAME}/"
echo "  Note: Funnel is publicly reachable, but the subdomain is not"
echo "  guessable and the app has no sensitive persistent data."
echo ""
echo "  To check current serve/funnel config at any time:"
echo "      sudo tailscale serve status"
echo ""
