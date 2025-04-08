import base64
import json
import logging
import os
import random  # Add it here, alphabetically ordered
import re
import requests
import time
import uuid
from decimal import Decimal
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Keys and URLs
API_KEY_BENDER_SEARCH = os.environ.get('API_KEY_BENDER_SEARCH', '74ffb423f5b400fe6ab7f80f2536041fe3b9e0a64c243682a4e5a789c94f8a9d')
API_KEY_BLOCKONOMICS = os.environ.get('API_KEY_BLOCKONOMICS', 'RM3FJKXzhG9QGjznb4JEcEWIP6JRlqnBsoPagNS3NpU')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '7823866996:AAH1rOfsbFqnHT1E_Sn-3Pizh3uyc5zEetQ')

# Webhook settings
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://incognitolookupbotrender.onrender.com/webhook')
WEBHOOK_PORT = int(os.environ.get('PORT', 8443))

# Service URLs
BENDER_SEARCH_URL = "https://bender-search.ru/apiv1/search_data"
BLOCKONOMICS_NEW_ADDRESS_URL = "https://www.blockonomics.co/api/new_address"
BLOCKONOMICS_TRANSACTIONS_URL = "https://www.blockonomics.co/api/transactions"
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"

# Define search pricing
SEARCH_PRICING = {
    'ssndob': {'price': 10, 'description': 'Social Security Number / Date of Birth Lookup'},
    'dl': {'price': 10, 'description': 'Driver License Lookup'},
    'cs': {'price': 5, 'description': 'Court Records Search'},
    'bg': {'price': 1, 'description': 'Background Check'}
}

# Search types and their expected parameters
SEARCH_TYPES = {
    'ssndob': ['first_name', 'last_name', 'state'],
    'dl': ['first_name', 'last_name', 'state'],
    'cs': ['first_name', 'last_name', 'state'],
    'bg': ['first_name', 'last_name', 'state', 'city']
}

# User database (in-memory for demonstration, use a real database in production)
users = {}

# Flask app for webhook
app = Flask(__name__)


def generate_user_id():
    """Generate a unique ID for new users."""
    return str(uuid.uuid4())


def get_btc_price():
    """Get the current BTC price in USD."""
    try:
        response = requests.get(
            COINGECKO_PRICE_URL,
            params={'ids': 'bitcoin', 'vs_currencies': 'usd'},
            timeout=10
        )
        data = response.json()
        return Decimal(str(data['bitcoin']['usd']))
    except Exception as e:
        logger.error(f"Error fetching BTC price: {e}")
        return None


def create_btc_wallet(user_id):
    """Create a new BTC wallet for a user."""
    try:
        headers = {'Authorization': f'Bearer {API_KEY_BLOCKONOMICS}'}
        response = requests.post(
            BLOCKONOMICS_NEW_ADDRESS_URL,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            address = response.json().get('address')
            if address:
                # Store wallet information
                if user_id not in users:
                    users[user_id] = {}

                users[user_id]['wallet_address'] = address
                users[user_id]['balance'] = Decimal('0')
                users[user_id]['transactions'] = []

                return address

        logger.error(f"Failed to create wallet: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error creating BTC wallet: {e}")
        return None


def get_wallet_balance(user_id):
    """Get wallet balance and update transaction history."""
    if user_id not in users or 'wallet_address' not in users[user_id]:
        return None

    wallet_address = users[user_id]['wallet_address']

    try:
        headers = {'Authorization': f'Bearer {API_KEY_BLOCKONOMICS}'}
        response = requests.get(
            f"{BLOCKONOMICS_TRANSACTIONS_URL}/{wallet_address}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            # Process transactions and calculate balance
            balance = Decimal('0')
            transactions = []

            for tx in data.get('txs', []):
                # Check if confirmed (6+ confirmations)
                if tx.get('confirmations', 0) >= 6:
                    amount = Decimal(str(tx.get('value', 0))) / Decimal('100000000')  # Convert satoshis to BTC
                    balance += amount

                    # Save transaction details
                    transactions.append({
                        'txid': tx.get('txid'),
                        'amount': amount,
                        'confirmations': tx.get('confirmations'),
                        'time': tx.get('time')
                    })

            # Update user's balance and transactions
            users[user_id]['balance'] = balance
            users[user_id]['transactions'] = transactions

            return balance

        logger.error(f"Failed to get wallet balance: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error getting wallet balance: {e}")
        return None


def get_user_profile(user_id):
    """Get a formatted user profile string."""
    if user_id not in users:
        return "Profile not found. Please register with /register"

    user = users[user_id]

    # Update wallet balance
    balance = get_wallet_balance(user_id)
    if balance is None:
        balance = users[user_id].get('balance', Decimal('0'))

    # Format balance with 8 decimal places
    balance_formatted = f"{balance:.8f}"

    # Get current BTC price
    btc_price = get_btc_price()
    usd_value = "Unknown"
    if btc_price:
        usd_value = f"${balance * btc_price:.2f}"

    profile = f"👤 *User Profile*\n\n"
    profile += f"🆔 User ID: `{user_id}`\n"
    profile += f"💰 BTC Balance: `{balance_formatted} BTC` (≈ {usd_value} USD)\n"

    if 'wallet_address' in user:
        profile += f"📬 Deposit Address: `{user['wallet_address']}`\n"

    profile += f"\n💳 Credits Used: {user.get('searches', 0)}"

    return profile


def send_telegram_message(chat_id, text, parse_mode=None, reply_markup=None):
    """Send a message to Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text
    }

    if parse_mode:
        payload['parse_mode'] = parse_mode

    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None


def handle_start_command(chat_id, user_id):
    """Handle /start command."""
    welcome_message = (
        "👋 *Welcome to Incognito Lookup Bot!*\n\n"
        "I can help you search for information across various databases.\n\n"
        "💰 Please register and add funds to your account to use search services.\n\n"
        "*Available Commands:*\n"
        "/register - Create your account\n"
        "/myprofile - View your account details\n"
        "/ssndob - Social Security Number / Date of Birth Lookup\n"
        "/dl - Driver License Lookup\n"
        "/cs - Court Records Search\n"
        "/bg - Background Check\n\n"
        "*Pricing:*\n"
    )

    for search_type, info in SEARCH_PRICING.items():
        welcome_message += f"• {info['description']} (/${info['price']}) - /{search_type}\n"

    send_telegram_message(chat_id, welcome_message, parse_mode='Markdown')


def handle_register_command(chat_id, user_id):
    """Handle /register command."""
    # Check if user already exists
    if user_id in users and 'wallet_address' in users[user_id]:
        message = (
            "✅ You're already registered!\n\n"
            "Use /myprofile to view your account details and deposit address."
        )
        send_telegram_message(chat_id, message)
        return

    # Create new user if needed
    if user_id not in users:
        users[user_id] = {
            'searches': 0,
            'balance': Decimal('0')
        }

    # Create BTC wallet
    wallet_address = create_btc_wallet(user_id)

    if wallet_address:
        # Registration successful
        message = (
            "✅ *Registration successful!*\n\n"
            "Your account has been created. You can now deposit funds to start using our services.\n\n"
            f"🔑 Your Deposit Address:\n`{wallet_address}`\n\n"
            "ℹ️ Send BTC to this address to fund your account. Your balance will update automatically after 6 confirmations.\n\n"
            "Use /myprofile to check your balance and account information."
        )
        send_telegram_message(chat_id, message, parse_mode='Markdown')
    else:
        # Registration failed
        message = (
            "❌ *Registration failed*\n\n"
            "Sorry, we couldn't create a wallet for you at this time. Please try again later."
        )
        send_telegram_message(chat_id, message, parse_mode='Markdown')


def handle_myprofile_command(chat_id, user_id):
    """Handle /myprofile command."""
    profile = get_user_profile(user_id)
    send_telegram_message(chat_id, profile, parse_mode='Markdown')


def handle_search_command(chat_id, user_id, search_type, text):
    """Generic handler for all search type commands."""
    # Check if user is registered
    if user_id not in users or 'wallet_address' not in users[user_id]:
        message = (
            "❌ *Account Required*\n\n"
            "You need to register before you can use this service.\n"
            "Please use /register to create your account."
        )
        send_telegram_message(chat_id, message, parse_mode='Markdown')
        return

    # Get pricing for the search type
    if search_type not in SEARCH_PRICING:
        message = "❌ Invalid search type."
        send_telegram_message(chat_id, message)
        return

    search_info = SEARCH_PRICING[search_type]
    price_usd = search_info['price']
    description = search_info['description']

    # Parse command arguments
    command_parts = text.split(' ', 1)
    if len(command_parts) == 1:
        # Show search info if no parameters provided
        required_params = ', '.join(SEARCH_TYPES[search_type])
        message = (
            f"🔎 *{description}*\n\n"
            f"Price: ${price_usd}\n\n"
            f"Required Parameters: {required_params}\n\n"
            f"Example: /{search_type} first_name=John last_name=Doe state=CA"
        )
        if search_type == 'bg':
            message += " city=LosAngeles"

        send_telegram_message(chat_id, message, parse_mode='Markdown')
        return

    # Process parameters and perform search
    handle_parameters(chat_id, user_id, search_type, command_parts[1])


def handle_ssndob_command(chat_id, user_id, text):
    """Handle /ssndob command."""
    handle_search_command(chat_id, user_id, 'ssndob', text)


def handle_dl_command(chat_id, user_id, text):
    """Handle /dl command."""
    handle_search_command(chat_id, user_id, 'dl', text)


def handle_cs_command(chat_id, user_id, text):
    """Handle /cs command."""
    handle_search_command(chat_id, user_id, 'cs', text)


def handle_bg_command(chat_id, user_id, text):
    """Handle /bg command."""
    handle_search_command(chat_id, user_id, 'bg', text)


def handle_parameters(chat_id, user_id, search_type, params_text):
    """Process parameters and initiate search."""
    # Check required parameters for the search type
    required_params = SEARCH_TYPES[search_type]

    # Extract parameters from the text
    # Supports both "param=value" format and "param:value" format
    params = {}
    param_matches = re.finditer(r'(\w+)[=:]([\w\s]+)', params_text)

    for match in param_matches:
        key = match.group(1).lower()
        value = match.group(2).strip()
        params[key] = value

    # Validate parameters
    missing_params = []
    for param in required_params:
        if param not in params:
            missing_params.append(param)

    if missing_params:
        message = (
                "❌ *Missing Required Parameters*\n\n"
                f"Please provide the following parameters:\n"
                f"• {', '.join(missing_params)}\n\n"
                f"Example: /{search_type} " + ' '.join([f"{p}=value" for p in required_params])
        )
        send_telegram_message(chat_id, message, parse_mode='Markdown')
        return

    # Get current wallet balance
    balance = get_wallet_balance(user_id)
    if balance is None:
        balance = users[user_id].get('balance', Decimal('0'))

    # Get BTC price and calculate required BTC amount
    btc_price = get_btc_price()
    if not btc_price:
        message = "❌ Unable to get current BTC price. Please try again later."
        send_telegram_message(chat_id, message)
        return

    price_usd = SEARCH_PRICING[search_type]['price']
    price_btc = Decimal(price_usd) / btc_price

    # Check if user has enough balance
    if balance < price_btc:
        # Calculate how much more BTC the user needs
        needed_btc = price_btc - balance
        needed_usd = needed_btc * btc_price

        message = (
            "❌ *Insufficient Balance*\n\n"
            f"This search costs: ${price_usd} (≈ {price_btc:.8f} BTC)\n"
            f"Your balance: {balance:.8f} BTC\n\n"
            f"You need {needed_btc:.8f} BTC more (≈ ${needed_usd:.2f})\n\n"
            "Please deposit funds to your account and try again.\n"
            "Use /myprofile to see your deposit address."
        )
        send_telegram_message(chat_id, message, parse_mode='Markdown')
        return

    # User has enough balance, proceed with search
    send_telegram_message(
        chat_id,
        "🔍 *Processing your search request...*\n\nThis may take a moment.",
        parse_mode='Markdown'
    )

    # Deduct balance
    users[user_id]['balance'] -= price_btc

    # Increment search counter
    users[user_id]['searches'] = users[user_id].get('searches', 0) + 1

    # Perform search
    perform_search(chat_id, user_id, search_type, params)


def perform_search(chat_id, user_id, search_type, params):
    """Perform the actual search operation."""
    try:
        # Prepare search request
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {API_KEY_BENDER_SEARCH}'
        }

        # Build search payload based on search type
        payload = {
            'search_type': search_type,
            'parameters': params
        }

        # Send search request to API
        send_telegram_message(chat_id, "🔄 Querying database...", parse_mode='Markdown')

        # Simulate API request (in production, use actual API)
        time.sleep(2)  # Simulating API request time

        # Simulate search response based on search type
        if search_type == 'ssndob':
            # Generate fake SSN and DOB for demonstration
            ssn = f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}"
            dob = f"{random.randint(1, 12)}/{random.randint(1, 28)}/{random.randint(1950, 2000)}"

            result = {
                'success': True,
                'data': {
                    'first_name': params.get('first_name', ''),
                    'last_name': params.get('last_name', ''),
                    'state': params.get('state', ''),
                    'ssn': ssn,
                    'dob': dob,
                    'address': f"{random.randint(100, 9999)} Main St, {params.get('state', 'CA')} {random.randint(10000, 99999)}"
                }
            }

        elif search_type == 'dl':
            # Generate fake driver's license number
            dl_number = f"{params.get('state', 'CA')}{random.randint(10000000, 99999999)}"

            result = {
                'success': True,
                'data': {
                    'first_name': params.get('first_name', ''),
                    'last_name': params.get('last_name', ''),
                    'state': params.get('state', ''),
                    'dl_number': dl_number,
                    'issue_date': f"{random.randint(1, 12)}/{random.randint(1, 28)}/{random.randint(2010, 2020)}",
                    'expiry_date': f"{random.randint(1, 12)}/{random.randint(1, 28)}/{random.randint(2023, 2030)}"
                }
            }

        elif search_type == 'cs':
            # Generate fake court records
            case_types = ['Traffic Violation', 'Civil Case', 'Criminal Case', 'No Records Found']
            case_type = random.choice(case_types)

            if case_type == 'No Records Found':
                result = {
                    'success': True,
                    'data': {
                        'first_name': params.get('first_name', ''),
                        'last_name': params.get('last_name', ''),
                        'state': params.get('state', ''),
                        'records': []
                    }
                }
            else:
                result = {
                    'success': True,
                    'data': {
                        'first_name': params.get('first_name', ''),
                        'last_name': params.get('last_name', ''),
                        'state': params.get('state', ''),
                        'records': [
                            {
                                'case_number': f"{random.randint(2010, 2023)}-{random.randint(1000, 9999)}",
                                'case_type': case_type,
                                'filing_date': f"{random.randint(1, 12)}/{random.randint(1, 28)}/{random.randint(2010, 2023)}",
                                'status': random.choice(['Closed', 'Open', 'Pending'])
                            }
                        ]
                    }
                }

        elif search_type == 'bg':
            # Generate fake background check
            result = {
                'success': True,
                'data': {
                    'first_name': params.get('first_name', ''),
                    'last_name': params.get('last_name', ''),
                    'state': params.get('state', ''),
                    'city': params.get('city', ''),
                    'criminal_records': random.choice([True, False]),
                    'employment_history': [
                        {
                            'employer': f"Company {chr(65 + random.randint(0, 25))}",
                            'period': f"{random.randint(2010, 2020)} - {random.randint(2021, 2023)}"
                        }
                    ],
                    'education': [
                        {
                            'institution': f"{params.get('state', 'CA')} University",
                            'degree': random.choice(['Bachelor', 'Master', 'Associate'])
                        }
                    ]
                }
            }

        # Format and send the result
        if result.get('success'):
            data = result.get('data', {})

            # Format response based on search type
            if search_type == 'ssndob':
                message = (
                    "✅ *SSNDOB Search Results*\n\n"
                    f"👤 *Subject:* {data.get('first_name', '')} {data.get('last_name', '')}\n"
                    f"📍 *State:* {data.get('state', '')}\n\n"
                    f"🔒 *SSN:* `{data.get('ssn', 'Not found')}`\n"
                    f"🎂 *DOB:* `{data.get('dob', 'Not found')}`\n"
                    f"🏠 *Address:* `{data.get('address', 'Not found')}`\n\n"
                    f"*Search ID:* `{uuid.uuid4()}`"
                )

            elif search_type == 'dl':
                message = (
                    "✅ *Driver License Search Results*\n\n"
                    f"👤 *Subject:* {data.get('first_name', '')} {data.get('last_name', '')}\n"
                    f"📍 *State:* {data.get('state', '')}\n\n"
                    f"🔑 *DL Number:* `{data.get('dl_number', 'Not found')}`\n"
                    f"📅 *Issue Date:* `{data.get('issue_date', 'Not found')}`\n"
                    f"⏰ *Expiry Date:* `{data.get('expiry_date', 'Not found')}`\n\n"
                    f"*Search ID:* `{uuid.uuid4()}`"
                )

            elif search_type == 'cs':
                records = data.get('records', [])

                message = (
                    "✅ *Court Records Search Results*\n\n"
                    f"👤 *Subject:* {data.get('first_name', '')} {data.get('last_name', '')}\n"
                    f"📍 *State:* {data.get('state', '')}\n\n"
                )

                if not records:
                    message += "📋 *Records:* No court records found.\n\n"
                else:
                    message += "📋 *Records Found:*\n\n"
                    for record in records:
                        message += (
                            f"🔹 *Case #:* `{record.get('case_number', '')}`\n"
                            f"🔹 *Type:* {record.get('case_type', '')}\n"
                            f"🔹 *Filed:* {record.get('filing_date', '')}\n"
                            f"🔹 *Status:* {record.get('status', '')}\n\n"
                        )

                message += f"*Search ID:* `{uuid.uuid4()}`"

            elif search_type == 'bg':
                message = (
                    "✅ *Background Check Results*\n\n"
                    f"👤 *Subject:* {data.get('first_name', '')} {data.get('last_name', '')}\n"
                    f"📍 *Location:* {data.get('city', '')}, {data.get('state', '')}\n\n"
                    f"⚖️ *Criminal Records:* {'Found' if data.get('criminal_records') else 'None Found'}\n\n"
                )

                message += "💼 *Employment History:*\n"
                for job in data.get('employment_history', []):
                    message += f"🔹 {job.get('employer', '')}: {job.get('period', '')}\n"

                message += "\n📚 *Education:*\n"
                for edu in data.get('education', []):
                    message += f"🔹 {edu.get('institution', '')}: {edu.get('degree', '')} Degree\n\n"

                message += f"*Search ID:* `{uuid.uuid4()}`"

            send_telegram_message(chat_id, message, parse_mode='Markdown')

        else:
            # Search failed
            error_message = (
                "❌ *Search Failed*\n\n"
                "We couldn't find any results matching your search criteria.\n"
                "Please verify your search parameters and try again."
            )
            send_telegram_message(chat_id, error_message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error performing search: {e}")
        error_message = (
            "❌ *Search Error*\n\n"
            "An error occurred while processing your search.\n"
            "Please try again later."
        )
        send_telegram_message(chat_id, error_message, parse_mode='Markdown')


@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    update = request.json

    # Extract chat id and user id
    chat_id = update.get('message', {}).get('chat', {}).get('id')
    user_id = str(update.get('message', {}).get('from', {}).get('id'))
    text = update.get('message', {}).get('text', '')

    if not chat_id or not text:
        return jsonify({'status': 'error', 'message': 'Invalid update'})

    # Handle commands
    if text.startswith('/start'):
        handle_start_command(chat_id, user_id)
    elif text.startswith('/register'):
        handle_register_command(chat_id, user_id)
    elif text.startswith('/myprofile'):
        handle_myprofile_command(chat_id, user_id)
    elif text.startswith('/ssndob'):
        handle_ssndob_command(chat_id, user_id, text)
    elif text.startswith('/dl'):
        handle_dl_command(chat_id, user_id, text)
    elif text.startswith('/cs'):
        handle_cs_command(chat_id, user_id, text)
    elif text.startswith('/bg'):
        handle_bg_command(chat_id, user_id, text)
    else:
        # Unknown command
        send_telegram_message(
            chat_id,
            "I don't understand that command. Use /start to see available commands."
        )

    return jsonify({'status': 'ok'})


def setup_webhook():
    """Set up the webhook for Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
        payload = {'url': WEBHOOK_URL}
        response = requests.post(url, json=payload)
        result = response.json()

        if result.get('ok'):
            logger.info("Webhook set up successfully")
        else:
            logger.error(f"Failed to set up webhook: {result}")
    except Exception as e:
        logger.error(f"Error setting up webhook: {e}")


if __name__ == '__main__':
    # Set up the webhook first
    setup_webhook()

    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", WEBHOOK_PORT))

    # Run the Flask application, binding to all network interfaces
    app.run(host='0.0.0.0', port=port)

