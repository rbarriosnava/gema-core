from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import os
from web3 import Web3

app = Flask(__name__)
CORS(app)

# --- CONFIGURACIÓN ---
PAYOUT_AMOUNT = 1
COOLDOWN_SECONDS = 3600  # 1 hora
WITHDRAWAL_MIN = 100

# --- CONEXIÓN A LA BLOCKCHAIN (BNB SMART CHAIN) ---
# Usamos un nodo público de BNB Chain
w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/'))

# Carga la clave privada de forma segura desde los "Secrets" de Replit
HOT_WALLET_PRIVATE_KEY = os.environ.get('FAUCET_PRIVATE_KEY')
HOT_WALLET_ADDRESS = w3.eth.account.from_key(HOT_WALLET_PRIVATE_KEY).address

# ABI muy simple del token wGEMA (solo necesitamos la función "transfer")
WGEMA_TOKEN_ABI = '[{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"}]'
# Dirección de tu contrato de token wGEMA
WGEMA_TOKEN_ADDRESS = "0x83731a25ff14bA7DBeCf179Cb84e60400e82343d"

wgema_contract = w3.eth.contract(
    address=Web3.to_checksum_address(WGEMA_TOKEN_ADDRESS), abi=WGEMA_TOKEN_ABI)

# --- Base de Datos en Memoria ---
user_data = {}

# --- RUTAS DE LA API ---


@app.route('/balance/<address>', methods=['GET'])
def get_balance(address):
    # ... (código igual que antes)
    user_address = address.lower()
    if user_address not in user_data:
        return jsonify({"balance": 0, "nextClaim": 0})
    user = user_data[user_address]
    next_claim_time = user["last_claim"] + COOLDOWN_SECONDS
    return jsonify({"balance": user["balance"], "nextClaim": next_claim_time})


@app.route('/claim', methods=['POST'])
def claim_tokens():
    print("\n--- NUEVA PETICIÓN DE RECLAMO RECIBIDA ---")
    print("Cabeceras (Headers):", request.headers)
    print("¿Es JSON?:", request.is_json)

    # Imprime el cuerpo de la petición en bruto
    raw_data = request.get_data(as_text=True)
    print("Cuerpo de la Petición (Raw):", raw_data)

    data = request.get_json()
    print("Datos JSON Parseados:", data)

    if not data or 'address' not in data:
        print(
            "--> ERROR: Los datos JSON están vacíos o no contienen la 'address'."
        )
        return jsonify({"error": "Faltan datos en la petición."}), 400

    user_address = data['address'].lower()
    current_time = int(time.time())

    # Si el usuario es nuevo, lo añadimos a nuestra "base de datos"
# y asignamos los valores iniciales ANTES de continuar.
if user_address not in user_data:
    user_data[user_address] = {"balance": 0, "last_claim": 0}

    if current_time < user_data[user_address]["last_claim"] + COOLDOWN_SECONDS:
        print(f"--> ERROR: Cooldown activo para {user_address}.")
        return jsonify({
            "error":
            f"Debes esperar. Próximo reclamo disponible en {COOLDOWN_SECONDS // 60} minutos."
        }), 400

    user_data[user_address]["balance"] += PAYOUT_AMOUNT
    user_data[user_address]["last_claim"] = current_time

    print(
        f"--> ÉXITO: Reclamo exitoso para {user_address}. Nuevo saldo: {user_data[user_address]['balance']}"
    )

    return jsonify({
        "message": "¡Recompensa acumulada con éxito!",
        "newBalance": user_data[user_address]["balance"]
    })


# --- ¡NUEVA RUTA DE RETIRO! ---
@app.route('/withdraw', methods=['POST'])
def withdraw_tokens():
    data = request.get_json()
    if not data or 'address' not in data:
        return jsonify({"error": "Falta la direccion del usuario."}), 400
    user_address = data['address'].lower()

    if user_address not in user_data or user_data[user_address][
            "balance"] < WITHDRAWAL_MIN:
        return jsonify({"error":
                        "No tienes el saldo mínimo para retirar."}), 400

    amount_to_send = user_data[user_address]["balance"]
    # Convertimos el monto a la unidad más pequeña del token (con 18 decimales)
    amount_in_wei = amount_to_send * (10**18)

    try:
        # Construimos la transacción
        nonce = w3.eth.get_transaction_count(HOT_WALLET_ADDRESS)
        tx = wgema_contract.functions.transfer(
            Web3.to_checksum_address(user_address),
            amount_in_wei).build_transaction({
                'chainId': 56,  # 56 es el ID de la BNB Smart Chain
                'gas': 70000,
                'gasPrice': w3.eth.gas_price,
                'nonce': nonce,
            })

        # Firmamos la transacción con nuestra clave privada
        signed_tx = w3.eth.account.sign_transaction(
            tx, private_key=HOT_WALLET_PRIVATE_KEY)

        # Enviamos la transacción a la red
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        # Reseteamos el saldo del usuario en nuestra base de datos
        user_data[user_address]["balance"] = 0

        print(
            f"Retiro exitoso para {user_address} de {amount_to_send} wGEMA. Hash: {w3.to_hex(tx_hash)}"
        )

        return jsonify({
            "message": "Retiro en proceso.",
            "txHash": w3.to_hex(tx_hash)
        })

    except Exception as e:
        print(f"Error en el retiro: {e}")
        return jsonify({"error":
                        "Ocurrió un error al procesar el retiro."}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
