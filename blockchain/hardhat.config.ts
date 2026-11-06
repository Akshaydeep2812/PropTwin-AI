import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

// Testnet settings come only from the environment. Nothing here holds a private key.
const testnetUrl = process.env.TESTNET_RPC_URL;
const deployerKey = process.env.TESTNET_DEPLOYER_PRIVATE_KEY;

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "cancun" },
  },
  networks: {
    // A standalone node acts like a real network: a reverting transaction is mined with a failed receipt
    // instead of erroring on send. In-process contract tests keep the default, which their matchers rely on.
    hardhat: { throwOnTransactionFailures: !process.argv.includes("node") },
    localhost: { url: process.env.LOCAL_RPC_URL ?? "http://127.0.0.1:8545" },
    ...(testnetUrl && deployerKey ? { testnet: { url: testnetUrl, accounts: [deployerKey] } } : {}),
  },
};

export default config;
