const { Connection, PublicKey, Keypair, Transaction, SystemProgram, sendAndConfirmTransaction } = require('@solana/web3.js');
const bs58 = require('bs58');
const dotenv = require('dotenv');

// Load environment variables
dotenv.config();

// Solana configuration
const config = {
  rpc_url: process.env.SOLANA_RPC_URL,
  receiver_address: process.env.SOLANA_RECEIVER_ADDRESS,
  name: 'Solana Devnet',
  minimum_lamports: 1_000_000, // Minimum balance to trigger transfer (0.001 SOL)
};

// Load sender wallets dynamically
const wallets = {};
const sender_users = new Set();
for (const key of Object.keys(process.env)) {
  if (key.startsWith('SOLANA_SENDER_')) {
    const user = key.replace('SOLANA_SENDER_', '');
    sender_users.add(user);
  }
}

for (const user of sender_users) {
  const address = process.env[`SOLANA_SENDER_${user}`];
  const private_key = process.env[`SOLANA_PRIVATE_KEY_${user}`];
  if (address && private_key) {
    try {
      wallets[address] = bs58.decode(private_key); // Decode Base58 private key
    } catch (e) {
      console.log(`Warning: Invalid private key for ${user} (${address}), skipping...`);
    }
  } else {
    console.log(`Warning: SOLANA_SENDER_${user} or SOLANA_PRIVATE_KEY_${user} not found in .env, skipping...`);
  }
}

// Check if any valid wallets are configured
if (Object.keys(wallets).length === 0) {
  console.log('Error: No valid sender wallets found in .env file');
  process.exit(1);
}

// Initialize Solana connection
const connection = new Connection(config.rpc_url, 'confirmed');
connection.getVersion().then(version => {
  console.log(`Connected to ${config.name}, version: ${version['solana-core']}`);
}).catch(e => {
  console.log(`Failed to connect to ${config.name} node: ${e}`);
  process.exit(1);
});

// Convert receiver address to PublicKey
let receiverPubkey;
try {
  receiverPubkey = new PublicKey(config.receiver_address);
} catch (e) {
  console.log(`Invalid receiver address: ${e}`);
  process.exit(1);
}

// Track last known balances
const last_balances = {};
for (const address of Object.keys(wallets)) {
  last_balances[address] = 0; // Initialize balances
}

// Transfer function for Solana
async function transfer_funds(sender_address, private_key, receiver_address) {
  try {
    const senderKeypair = Keypair.fromSecretKey(private_key);
    const current_balance = await connection.getBalance(new PublicKey(sender_address));

    // Calculate amount to transfer (leave some lamports for fees)
    const lamports_to_transfer = current_balance - 5000; // 5000 lamports for transaction fee
    if (lamports_to_transfer <= 0) {
      console.log(`Insufficient balance for ${sender_address} to cover fees`);
      return false;
    }

    const transaction = new Transaction().add(
      SystemProgram.transfer({
        fromPubkey: senderKeypair.publicKey,
        toPubkey: receiver_address,
        lamports: lamports_to_transfer,
      })
    );

    const signature = await sendAndConfirmTransaction(connection, transaction, [senderKeypair]);
    console.log(`Transfer sent from ${sender_address}: ${signature}`);
    return true;
  } catch (e) {
    console.log(`Error transferring from ${sender_address}: ${e}`);
    return false;
  }
}

// Check and transfer funds
async function check_and_transfer() {
  for (const [sender_address, private_key] of Object.entries(wallets)) {
    try {
      const current_balance = await connection.getBalance(new PublicKey(sender_address));
      if (current_balance > last_balances[sender_address] && current_balance >= config.minimum_lamports) {
        console.log(`New deposit detected for ${sender_address}! Current balance: ${current_balance / 1_000_000_000} SOL`);
        const success = await transfer_funds(sender_address, private_key, receiverPubkey);
        if (success) {
          last_balances[sender_address] = current_balance;
        }
      } else {
        console.log(`No new deposits for ${sender_address}`);
      }
      last_balances[sender_address] = current_balance;
    } catch (e) {
      console.log(`Error checking ${sender_address}: ${e}`);
    }
  }
}

// Main loop
async function main() {
  console.log(`Starting wallet monitoring for ${config.name}...`);
  console.log(`Monitoring ${Object.keys(wallets).length} wallets`);
  while (true) {
    await check_and_transfer();
    await new Promise(resolve => setTimeout(resolve, 7000)); // Check every 7 seconds
  }
}

main().catch(e => {
  console.error(`Main loop error: ${e}`);
  process.exit(1);
});
