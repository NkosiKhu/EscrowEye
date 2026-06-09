import { HashConnect } from "hashconnect";
import { LedgerId } from "@hashgraph/sdk";

const APP_METADATA = {
  name: "EscrowEye",
  description: "Hedera escrow for home services",
  icons: ["https://escroweye.app/logo.png"],
  url: typeof window !== "undefined" ? window.location.origin : "https://escroweye.app",
};

let hc: HashConnect | null = null;

export function getHashConnect(): HashConnect {
  if (!hc) {
    hc = new HashConnect(
      LedgerId.TESTNET,
      import.meta.env.VITE_WALLETCONNECT_PROJECT_ID,
      APP_METADATA,
      true, // debug
    );
  }
  return hc;
}

export async function connectHashPack(): Promise<{ accountId: string; publicKey: string }> {
  const hashconnect = getHashConnect();
  await hashconnect.init();
  // openPairingModal triggers the pairing UI; connected accounts are available on the instance after pairing
  await hashconnect.openPairingModal();
  const accountId = String(hashconnect.connectedAccountIds[0]);
  // publicKey can be derived from accountId via mirror node if needed
  const publicKey = "";
  return { accountId, publicKey };
}

export async function signChallengeWithHashPack(message: string): Promise<string> {
  const hashconnect = getHashConnect();
  const signer = hashconnect.getSigner(hashconnect.connectedAccountIds[0]);
  const signed = await signer.sign([Buffer.from(message)]);
  return Buffer.from(signed[0].signature).toString("hex");
}

export async function transferHbarWithHashPack(
  toAccountId: string,
  amountTinybar: number,
): Promise<{ transactionId: string }> {
  const { TransferTransaction, AccountId, Hbar } = await import("@hashgraph/sdk");
  const hashconnect = getHashConnect();
  const signer = hashconnect.getSigner(hashconnect.connectedAccountIds[0]);
  const fromAccountId = hashconnect.connectedAccountIds[0];

  const tx = await new TransferTransaction()
    .addHbarTransfer(AccountId.fromString(String(fromAccountId)), Hbar.fromTinybars(-amountTinybar))
    .addHbarTransfer(AccountId.fromString(toAccountId), Hbar.fromTinybars(amountTinybar))
    .freezeWithSigner(signer);

  const result = await tx.executeWithSigner(signer);
  return { transactionId: result.transactionId.toString() };
}
