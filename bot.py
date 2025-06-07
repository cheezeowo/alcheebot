import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime
from collections import defaultdict

TOKEN = "7289172434:AAEcGKU6hNANwnCoENkDQk_oUsC1Oicr-O0"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

GRAPH_API = "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v2"

def format_number(num):
    return f"${num:,.2f}"

def approx_power_of_2(value):
    import math
    power = math.floor(math.log2(value)) if value > 0 else 0
    return f">=2^{power}"

async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].startswith("0x"):
        await update.message.reply_text("Please enter a valid wallet address. Example: /wallet 0xabc...")
        return

    wallet = context.args[0].lower()
    now = int(datetime.utcnow().timestamp())
    fifteen_days_ago = now - 15 * 24 * 60 * 60

    query = f"""
    {{
      swaps(first: 1000, orderBy: timestamp, orderDirection: desc,
        where: {{
          sender: "{wallet}",
          timestamp_gte: {fifteen_days_ago}
        }}) {{
        amountUSD
        amount0In
        amount1In
        amount0Out
        amount1Out
        timestamp
        pair {{
          token0 {{ id symbol }}
          token1 {{ id symbol }}
        }}
      }}
    }}
    """

    response = requests.post(GRAPH_API, json={"query": query})
    if response.status_code != 200:
        await update.message.reply_text("Failed to fetch data.")
        return

    swaps = response.json().get("data", {}).get("swaps", [])
    daily_data = defaultdict(lambda: defaultdict(lambda: {"volume": 0.0, "slippage": 0.0, "symbol": ""}))
    total_volume = 0.0
    total_slippage = 0.0

    for swap in swaps:
        date = datetime.utcfromtimestamp(int(swap["timestamp"])).strftime("%m/%d")
        amount_usd = float(swap["amountUSD"])
        in_sum = float(swap["amount0In"]) + float(swap["amount1In"])
        out_sum = float(swap["amount0Out"]) + float(swap["amount1Out"])

        expected = in_sum
        actual = out_sum
        slippage = amount_usd * (1 - actual / expected) if expected > actual and expected > 0 else 0

        token = swap["pair"]["token0"] if in_sum >= out_sum else swap["pair"]["token1"]
        token_id = token["id"]
        token_symbol = token["symbol"]

        daily_data[date][token_id]["volume"] += amount_usd
        daily_data[date][token_id]["slippage"] += slippage
        daily_data[date][token_id]["symbol"] = token_symbol

        total_volume += amount_usd
        total_slippage += slippage

    message = "[Wallet Slippage Summary (Last 15 days)]\n\n"

    message += "[Daily Token Volume + Slippage]\n"
    for date in sorted(daily_data.keys(), reverse=True)[:5]:
        message += f"{date}\n"
        for token in daily_data[date].values():
            message += f"  - {token['symbol']}: {format_number(token['volume'])} / Slippage: {format_number(token['slippage'])}\n"

    message += "\n[x2 Volume Summary]\n"
    for date in sorted(daily_data.keys(), reverse=True)[:5]:
        day_total = sum(token["volume"] for token in daily_data[date].values())
        x2_volume = day_total * 2
        message += f"{date}  {format_number(x2_volume)} ({approx_power_of_2(x2_volume)})\n"

    message += f"\nTotal Volume: {format_number(total_volume)} (x2 BSC: {format_number(total_volume * 2)})"
    message += f"\nTotal Slippage: {format_number(total_slippage)}"

    keyboard = [[InlineKeyboardButton(f"/wallet {wallet}", callback_data=f"/wallet {wallet}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, reply_markup=reply_markup)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("wallet", handle_wallet))
    app.run_polling()
