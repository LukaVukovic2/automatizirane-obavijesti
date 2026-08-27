# Njuškalo Telegram Notifier

A lightweight Python service that watches a Njuškalo real-estate search URL and sends Telegram notifications whenever new listings appear.

---

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/listing-notifying-app.git
   cd listing-notifying-app
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**

   ```bash
   playwright install
   ```

5. **Copy the example environment file and fill in your values**

   ```bash
   cp .env.example .env
   ```

---

## Configuration

All settings are loaded from environment variables or a `.env` file in the project root. Copy `.env.example` to `.env` and set each value before starting the service.

### Required

| Variable | Description |
|---|---|
| `NJUSKALO_SEARCH_URL` | Full Njuškalo search URL to monitor. Copy it directly from your browser after configuring your filters. |
| `TELEGRAM_BOT_TOKEN` | Bot token obtained from @BotFather (see [Telegram Setup](#telegram-setup)). |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID where notifications will be sent. |
| `CHECK_INTERVAL_MINUTES` | How often to poll for new listings, in minutes. Must be an integer between 1 and 1440. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log verbosity. Accepted values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

> The service exits with a non-zero status code if any required variable is missing or invalid.

---

## Telegram Setup

### 1. Create a bot and get the token

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and username for your bot).
3. BotFather will reply with a token that looks like `123456789:AABBccDDee...`. Copy it into `TELEGRAM_BOT_TOKEN`.

### 2. Find your Chat ID

**Personal chat:**

1. Search for **@userinfobot** on Telegram and start a conversation.
2. It will reply with your numeric Chat ID (e.g., `123456789`). Copy it into `TELEGRAM_CHAT_ID`.

**Group chat:**

1. Add your bot to the group.
2. Send any message in the group, then open a browser and visit:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
3. Find the `"chat"` object in the response — its `"id"` field is the group Chat ID (negative number for groups, e.g., `-987654321`).

> Make sure you send your bot at least one message (or add it to the group) before calling `getUpdates`, otherwise the response will be empty.

---

## Running the Service

Start the monitor with:

```bash
python monitor.py
```

The service will:

1. On the **first run**, silently scrape the search URL and save the current listing IDs as a baseline — no notifications are sent.
2. On **subsequent runs**, detect any listings that weren't present in the previous check and send a Telegram message for each new batch.
3. Repeat indefinitely at the interval configured by `CHECK_INTERVAL_MINUTES`.

To stop the service, press `Ctrl+C` (or send `SIGTERM`). The service will log a shutdown message and exit cleanly, leaving `previous_ids.json` in its last valid state.

### Example `.env`

```dotenv
NJUSKALO_SEARCH_URL=https://www.njuskalo.hr/prodaja-stanova?geo_location_id=3&price_from=100000&price_to=200000
TELEGRAM_BOT_TOKEN=123456789:AABBccDDeeFfGgHhIiJj
TELEGRAM_CHAT_ID=123456789
CHECK_INTERVAL_MINUTES=5
LOG_LEVEL=INFO
```

---

## Adding a New Searcher

The multi-searcher pipeline (`listing_monitor/`) lets you monitor any number of independent Njuškalo searches, each posting to its own Discord channel. Follow these four steps to add a new one:

1. **Create a Discord webhook**

   In the target Discord server, go to **Server Settings → Integrations → Webhooks** and click **New Webhook**. Give it a name (e.g., "Njuškalo Garages"), select the channel where notifications should appear, and copy the webhook URL.

2. **Add the webhook URL to `.env`**

   Open your `.env` file (copy from `.env.example` if you haven't already) and add a new entry with a descriptive name:

   ```dotenv
   DISCORD_WEBHOOK_GARAGES=https://discord.com/api/webhooks/<id>/<token>
   ```

3. **Add a new Searcher object to `config.json`**

   Open `config.json` and append a new object to the `searchers` array. The `discord_webhook_env` value must match the variable name you chose in step 2:

   ```json
   {
     "id": "garages",
     "name": "Garages Zagreb",
     "search_url": "https://www.njuskalo.hr/najam-garaze?geo[locationIds]=1250",
     "discord_webhook_env": "DISCORD_WEBHOOK_GARAGES"
   }
   ```

   Each `id` must be unique across all Searchers — it is used as the key in `previous_ids.json`.

4. **Restart the monitor**

   ```bash
   python -m listing_monitor.monitor
   ```

   On the first run the new Searcher will silently baseline the current listings (no notifications sent). From the second run onward, new listings will be posted to the Discord channel you configured.
