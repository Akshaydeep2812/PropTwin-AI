// Talks to a browser wallet through the standard EIP-1193 provider. Keys stay in the wallet and never reach this app.

export function walletAvailable() {
  return typeof window !== "undefined" && Boolean(window.ethereum);
}

function provider() {
  if (!walletAvailable()) throw new Error("No browser wallet was found. Install one, such as MetaMask, to sign this transaction.");
  return window.ethereum;
}

export async function connectWallet() {
  const accounts = await provider().request({ method: "eth_requestAccounts" });
  return accounts[0];
}

export function signMessage(address, message) {
  return provider().request({ method: "personal_sign", params: [message, address] });
}

export async function sendPreparedCall(call) {
  const chainHex = `0x${call.chain_id.toString(16)}`;
  const current = await provider().request({ method: "eth_chainId" });
  if (current.toLowerCase() !== chainHex) {
    await provider().request({ method: "wallet_switchEthereumChain", params: [{ chainId: chainHex }] });
  }
  return provider().request({
    method: "eth_sendTransaction",
    params: [{ from: call.from_address, to: call.to, data: call.data }],
  });
}
