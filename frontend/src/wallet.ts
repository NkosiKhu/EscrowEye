type WalletSignatureResult = string | ArrayBuffer | Uint8Array | { signature?: unknown; accountId?: string; publicKey?: string };

type WalletSigner = {
  connect?: () => Promise<unknown> | unknown;
  signMessage?: (message: string) => Promise<WalletSignatureResult> | WalletSignatureResult;
  sign?: (message: string) => Promise<WalletSignatureResult> | WalletSignatureResult;
  accountId?: string;
  publicKey?: string;
};

declare global {
  interface Window {
    escrowEyeWalletSigner?: WalletSigner;
    hashpack?: WalletSigner;
    HashPack?: WalletSigner;
    hederaWallet?: WalletSigner;
  }
}

export type SignedWalletChallenge = {
  signature: string;
  accountId?: string;
  publicKey?: string;
  source: "wallet" | "dev";
};

export async function signWalletChallenge(message: string, devSignature: string): Promise<SignedWalletChallenge> {
  const signer = findWalletSigner();
  if (!signer) return { signature: devSignature, source: "dev" };

  await signer.connect?.();
  const rawSignature = signer.signMessage ? await signer.signMessage(message) : await signer.sign?.(message);
  const parsed = parseSignature(rawSignature);
  if (!parsed.signature) return { signature: devSignature, source: "dev" };

  return {
    signature: parsed.signature,
    accountId: parsed.accountId ?? signer.accountId,
    publicKey: parsed.publicKey ?? signer.publicKey,
    source: "wallet",
  };
}

function findWalletSigner(): WalletSigner | null {
  if (typeof window === "undefined") return null;
  return window.escrowEyeWalletSigner ?? window.hashpack ?? window.HashPack ?? window.hederaWallet ?? null;
}

function parseSignature(value: WalletSignatureResult | undefined): SignedWalletChallenge | { signature?: string; accountId?: string; publicKey?: string } {
  if (!value) return {};
  if (typeof value === "string") return { signature: value };
  if (value instanceof ArrayBuffer) return { signature: bytesToHex(new Uint8Array(value)) };
  if (value instanceof Uint8Array) return { signature: bytesToHex(value) };
  if (typeof value === "object") {
    const signature = value.signature;
    if (typeof signature === "string") return { signature, accountId: value.accountId, publicKey: value.publicKey };
    if (signature instanceof ArrayBuffer) return { signature: bytesToHex(new Uint8Array(signature)), accountId: value.accountId, publicKey: value.publicKey };
    if (signature instanceof Uint8Array) return { signature: bytesToHex(signature), accountId: value.accountId, publicKey: value.publicKey };
  }
  return {};
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
