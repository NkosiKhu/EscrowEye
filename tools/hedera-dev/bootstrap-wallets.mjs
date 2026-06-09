import {
  AccountBalanceQuery,
  AccountCreateTransaction,
  Client,
  Hbar,
  PrivateKey,
} from "@hashgraph/sdk";
import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "../..");
const credsPath = path.join(repoRoot, "creds");

function readCreds() {
  if (!fs.existsSync(credsPath)) {
    throw new Error(`Missing creds file at ${credsPath}`);
  }
  const entries = {};
  for (const rawLine of fs.readFileSync(credsPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...valueParts] = line.split("=");
    entries[key.trim()] = valueParts.join("=").trim();
  }
  return entries;
}

function upsertCreds(updates) {
  const existing = fs.existsSync(credsPath) ? fs.readFileSync(credsPath, "utf8").split(/\r?\n/) : [];
  const pending = new Map(Object.entries(updates));
  const next = [];

  for (const rawLine of existing) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      next.push(rawLine);
      continue;
    }
    const [key] = line.split("=");
    if (pending.has(key.trim())) {
      next.push(`${key.trim()}=${pending.get(key.trim())}`);
      pending.delete(key.trim());
    } else {
      next.push(rawLine);
    }
  }

  if (next.length && next[next.length - 1].trim()) next.push("");
  for (const [key, value] of pending) {
    next.push(`${key}=${value}`);
  }

  fs.writeFileSync(credsPath, `${next.join("\n").replace(/\n+$/, "")}\n`);
}

function clientFromCreds(creds) {
  const network = creds.HEDERA_NETWORK || "testnet";
  const client =
    network === "mainnet"
      ? Client.forMainnet()
      : network === "previewnet"
        ? Client.forPreviewnet()
        : Client.forTestnet();

  if (!creds.HEDERA_OPERATOR_ID || !creds.HEDERA_OPERATOR_PRIVATE_KEY) {
    throw new Error("Set HEDERA_OPERATOR_ID and HEDERA_OPERATOR_PRIVATE_KEY in creds first.");
  }

  const operatorKey = PrivateKey.fromStringECDSA(creds.HEDERA_OPERATOR_PRIVATE_KEY);
  client.setOperator(creds.HEDERA_OPERATOR_ID, operatorKey);
  return client;
}

async function createDevAccount(client, label, initialHbar) {
  const privateKey = PrivateKey.generateECDSA();
  const publicKey = privateKey.publicKey;
  const tx = await new AccountCreateTransaction()
    .setECDSAKeyWithAlias(publicKey)
    .setInitialBalance(new Hbar(initialHbar))
    .execute(client);
  const receipt = await tx.getReceipt(client);
  if (!receipt.accountId) {
    throw new Error(`No accountId returned for ${label}`);
  }
  return {
    id: receipt.accountId.toString(),
    privateKey: privateKey.toStringRaw(),
    publicKey: publicKey.toString(),
    evmAddress: `0x${publicKey.toEvmAddress()}`,
  };
}

async function main() {
  const args = new Set(process.argv.slice(2));
  const force = args.has("--force");
  const initialHbar = Number(process.env.DEV_WALLET_INITIAL_HBAR || "20");
  const creds = readCreds();

  if (!force && creds.DEV_OWNER_ID && creds.DEV_SUPPLIER_ID) {
    console.log("Dev wallets already exist in creds. Use --force to replace them.");
    console.log(`Owner: ${creds.DEV_OWNER_ID}`);
    console.log(`Supplier: ${creds.DEV_SUPPLIER_ID}`);
    return;
  }

  const client = clientFromCreds(creds);
  try {
    const balance = await new AccountBalanceQuery()
      .setAccountId(creds.HEDERA_OPERATOR_ID)
      .execute(client);
    console.log(`Operator balance: ${balance.hbars.toString()}`);
    console.log(`Creating owner and supplier accounts with ${initialHbar} HBAR each...`);

    const owner = await createDevAccount(client, "owner", initialHbar);
    const supplier = await createDevAccount(client, "supplier", initialHbar);

    upsertCreds({
      DEV_OWNER_ID: owner.id,
      DEV_OWNER_PRIVATE_KEY: owner.privateKey,
      DEV_OWNER_PUBLIC_KEY: owner.publicKey,
      DEV_OWNER_EVM_ADDRESS: owner.evmAddress,
      DEV_SUPPLIER_ID: supplier.id,
      DEV_SUPPLIER_PRIVATE_KEY: supplier.privateKey,
      DEV_SUPPLIER_PUBLIC_KEY: supplier.publicKey,
      DEV_SUPPLIER_EVM_ADDRESS: supplier.evmAddress,
    });

    console.log("Created dev wallets and wrote them to gitignored creds.");
    console.log(`Owner: ${owner.id} (${owner.evmAddress})`);
    console.log(`Supplier: ${supplier.id} (${supplier.evmAddress})`);
  } finally {
    client.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
