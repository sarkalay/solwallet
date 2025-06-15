from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from dotenv import load_dotenv
import os
import time
import base58

# Load environment variables
load_dotenv()

# Solana configuration
config = {
    'rpc_url': os.getenv('SOLANA_RPC_URL'),
    'receiver_address': os.getenv('SOLANA_RECEIVER_ADDRESS'),
    'name': 'Solana Devnet',
    'minimum_lamports': 1_000_000,  # Minimum balance to trigger transfer (0.001 SOL)
}

# Load sender wallets dynamically
wallets = {}
sender_users = set()
for key in os.environ.keys():
    if key.startswith('SOLANA_SENDER_'):
        user = key.replace('SOLANA_SENDER_', '')
        sender_users.add(user)

for user in sender_users:
    address = os.getenv(f'SOLANA_SENDER_{user}')
    private_key = os.getenv(f'SOLANA_PRIVATE_KEY_{user}')
    if address and private_key:
        try:
            # Decode Base58 private key
            private_key_bytes = base58.b58decode(private_key)
            wallets[address] = private_key_bytes
        except Exception as e:
            print(f"Warning: Invalid private key for {user} ({address}), skipping: {e}")
    else:
        print(f"Warning: SOLANA_SENDER_{user} or SOLANA_PRIVATE_KEY_{user} not found in .env, skipping...")

# Check if any valid wallets are configured
if not wallets:
    print("Error: No valid sender wallets found in .env file")
    exit(1)

# Initialize Solana connection
client = Client(config['rpc_url'])
try:
    version = client.get_version()
    print(f"Connected to {config['name']}, version: {version.value['solana-core']}")
except Exception as e:
    print(f"Failed to connect to {config['name']} node: {e}")
    exit(1)

# Convert receiver address to Pubkey
try:
    receiver_pubkey = Pubkey.from_string(config['receiver_address'])
except ValueError as e:
    print(f"Invalid receiver address: {e}")
    exit(1)

# Track last known balances
last_balances = {addr: 0 for addr in wallets}

# Transfer function for Solana
def transfer_funds(client, private_key, sender_address, receiver_pubkey):
    try:
        sender_keypair = Keypair.from_bytes(private_key)
        sender_pubkey = Pubkey.from_string(sender_address)
        current_balance = client.get_balance(sender_pubkey).value

        # Calculate amount to transfer (leave 5000 lamports for fees)
        lamports_to_transfer = current_balance - 5000
        if lamports_to_transfer <= 0:
            print(f"Insufficient balance for {sender_address} to cover fees")
            return False

        # Create transaction
        tx = Transaction().add(
            transfer(
                TransferParams(
                    from_pubkey=sender_keypair.pubkey(),
                    to_pubkey=receiver_pubkey,
                    lamports=lamports_to_transfer
                )
            )
        )

        # Send and confirm transaction
        signature = client.send_transaction(tx, sender_keypair).value
        print(f"Transfer sent from {sender_address}: {signature}")
        client.confirm_transaction(signature)
        print(f"Transfer confirmed from {sender_address}: {signature}")
        return True
    except Exception as e:
        print(f"Error transferring from {sender_address}: {e}")
        return False

# Check and transfer funds
def check_and_transfer():
    for sender_address, private_key in wallets.items():
        try:
            sender_pubkey = Pubkey.from_string(sender_address)
            current_balance = client.get_balance(sender_pubkey).value
            if current_balance > last_balances[sender_address] and current_balance >= config['minimum_lamports']:
                print(f"New deposit detected for {sender_address}! Current balance: {current_balance / 1_000_000_000} SOL")
                success = transfer_funds(client, private_key, sender_address, receiver_pubkey)
                if success:
                    last_balances[sender_address] = current_balance
            else:
                print(f"No new deposits for {sender_address}")
            last_balances[sender_address] = current_balance
        except Exception as e:
            print(f"Error checking {sender_address}: {e}")

# Main loop
def main():
    print(f"Starting wallet monitoring for {config['name']}...")
    print(f"Monitoring {len(wallets)} wallets")
    while True:
        check_and_transfer()
        time.sleep(7)  # Check every 7 seconds

if __name__ == "__main__":
    main()
