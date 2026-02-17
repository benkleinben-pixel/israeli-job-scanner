#!/bin/bash
#
# Israeli Job Scanner — Install background fetch + WhatsApp notifications
#
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.israeli-job-scanner.fetch"
PLIST_SRC="$PROJECT_DIR/$PLIST_NAME.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
ENV_FILE="$PROJECT_DIR/fetch/.env"

echo "=== Israeli Job Scanner — Setup ==="
echo ""

# 1. Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r "$PROJECT_DIR/fetch/requirements.txt"
echo ""

# 2. Configure Twilio WhatsApp (optional)
echo "--- WhatsApp Notifications (via Twilio) ---"
echo "To receive WhatsApp alerts when new jobs are found, you need a Twilio account."
echo "  1. Sign up at https://www.twilio.com (free trial available)"
echo "  2. Go to Messaging > Try it out > Send a WhatsApp message"
echo "  3. Join the sandbox by sending a WhatsApp message to the Twilio number"
echo ""

read -p "Would you like to configure WhatsApp notifications now? [y/N] " setup_twilio

if [[ "$setup_twilio" =~ ^[Yy]$ ]]; then
    read -p "Twilio Account SID: " twilio_sid
    read -p "Twilio Auth Token: " twilio_token
    read -p "Twilio WhatsApp From number (e.g. +14155238886): " twilio_from
    read -p "Your WhatsApp number (e.g. +972501234567): " whatsapp_to

    cat > "$ENV_FILE" <<EOF
# Twilio WhatsApp Notification Credentials
TWILIO_ACCOUNT_SID=$twilio_sid
TWILIO_AUTH_TOKEN=$twilio_token
TWILIO_WHATSAPP_FROM=$twilio_from
WHATSAPP_TO=$whatsapp_to
EOF
    echo "Credentials saved to $ENV_FILE"
else
    echo "Skipped. You can configure later by editing $ENV_FILE"
fi
echo ""

# 3. Install launchd job for background fetching
echo "--- Background Scheduling (every 3 hours) ---"

# Unload existing job if present
if launchctl list | grep -q "$PLIST_NAME" 2>/dev/null; then
    echo "Unloading existing launchd job..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Generate plist with actual paths substituted
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__HOME__|$HOME|g" \
    "$PLIST_SRC" > "$PLIST_DEST"

# Load the job
launchctl load "$PLIST_DEST"

echo "Background fetch job installed and loaded."
echo "  Plist: $PLIST_DEST"
echo "  Logs:  ~/Library/Logs/israeli-job-scanner.log"
echo ""
echo "Useful commands:"
echo "  launchctl list | grep israeli-job-scanner  # Check if running"
echo "  launchctl unload $PLIST_DEST               # Stop background fetching"
echo "  python3 $PROJECT_DIR/fetch/fetcher.py --once  # Manual test run"
echo ""
echo "=== Setup complete! ==="
