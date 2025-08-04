from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import os
from web3 import Web3

# --- Initialization ---
app = Flask(__name__)
CORS(app)

# --- Faucet Configuration (You can change these values) ---
PAYOUT_AMOUNT = 1
COOLDOWN_SECONDS = 3600  # 1 hour (60 seconds * 60 minutes)
WITHDRAWAL_MIN = 100

# --- Web3 Configuration ---
w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))
HOT_WALLET_PRIVATE_KEY = os.environ.get('FAUCET_PRIVATE_KEY')
WGEMA_TOKEN_ADDRESS = "0x83731a25ff14bA7DBeCf179Cb84e60400e82343d" # Your wGEMA token address

# Check for private key and derive the hot wallet address
if not HOT_WALLET_PRIVATE_KEY:
    raise ValueError("FAUCET_PRIVATE_KEY environment variable not set!")
HOT_WALLET_ADDRESS = w3.eth.account.from_key(HOT_WALLET_PRIVATE_KEY).address

# Minimal ABI for the wGEMA token (only need the 'transfer' function)
WGEMA_TOKEN_ABI = '[{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"}]'
wgema_contract = w3.eth.contract(address=Web3.to_checksum_address(WGEMA_TOKEN_ADDRESS), abi=WGEMA_TOKEN_ABI)

# --- In-Memory Database ---
user_data = {}

# --- API Routes ---

@app.route('/balance/<address>', methods=['GET'])
def get_balance(address):
    user_address = address.lower()
    if user_address not in user_data:
        return jsonify({"balance": 0, "nextClaim": 0})
    
    user = user_data[user_address]
    next_claim_time = user["last_claim"] + COOLDOWN_SECONDS
    return jsonify({"balance": user["balance"], "nextClaim": next_claim_time})

@app.route('/claim', methods=['POST'])
def claim_tokens():
    data = request.get_json()
    if not data or 'address' not in data:
        return jsonify({"error": "User address is missing."}), 400
    
    user_address = data['address'].lower()
    current_time = int(time.time())

    if user_address not in user_data:
        user_data[user_address] = {"balance": 0, "last_claim": 0}

    if current_time < user_data[user_address]["last_claim"] + COOLDOWN_SECONDS:
        return jsonify({"error": "Cooldown period is still active."}), 400

    user_data[user_address]["balance"] += PAYOUT_AMOUNT
    user_data[user_address]["last_claim"] = current_time

    print(f"Successful claim for {user_address}. New balance: {user_data[user_address]['balance']}")
    
    return jsonify({
        "message": "Reward successfully accumulated!",
        "newBalance": user_data[user_address]["balance"]
    })

@app.route('/withdraw', methods=['POST'])
def withdraw_tokens():
    data = request.get_json()
    if not data or 'address' not in data:
        return jsonify({"error": "User address is missing."}), 400
        
    user_address = data['address'].lower()

    if user_address not in user_data or user_data[user_address]["balance"] < WITHDRAWAL_MIN:
        return jsonify({"error": "Minimum balance not met for withdrawal."}), 400

    amount_to_send = user_data[user_address]["balance"]
    amount_in_wei = amount_to_send * (10**18)

    try:
        nonce = w3.eth.get_transaction_count(HOT_WALLET_ADDRESS)
        tx = wgema_contract.functions.transfer(
            Web3.to_checksum_address(user_address),
            amount_in_wei
        ).build_transaction({
            'chainId': 56,  # BNB Smart Chain ID
            'gas': 70000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key=HOT_WALLET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        user_data[user_address]["balance"] = 0

        print(f"Successful withdrawal for {user_address} of {amount_to_send} wGEMA. Hash: {w3.to_hex(tx_hash)}")
        
        return jsonify({"message": "Withdrawal in process.", "txHash": w3.to_hex(tx_hash)})

    except Exception as e:
        print(f"Error during withdrawal: {e}")
        return jsonify({"error": "An error occurred while processing the withdrawal."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
