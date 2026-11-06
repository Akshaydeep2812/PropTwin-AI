import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { artifacts, ethers, network } from "hardhat";

/**
 * Deploys PropertyRegistry and writes the ABI and address the backend reads.
 * The registrar defaults to the second signer locally. On a testnet set REGISTRAR_ADDRESS,
 * so that the admin key can stay offline and only the relayer key lives on the server.
 */
async function main() {
  const signers = await ethers.getSigners();
  const admin = signers[0];
  const registrar = process.env.REGISTRAR_ADDRESS ?? signers[1]?.address;
  if (!registrar) throw new Error("Set REGISTRAR_ADDRESS: this network has only one signer.");

  const factory = await ethers.getContractFactory("PropertyRegistry");
  const registry = await factory.deploy(admin.address, registrar);
  await registry.waitForDeployment();
  const address = await registry.getAddress();
  const receipt = await registry.deploymentTransaction()?.wait();

  const root = join(__dirname, "..");
  mkdirSync(join(root, "abi"), { recursive: true });
  mkdirSync(join(root, "deployments"), { recursive: true });
  const { abi } = await artifacts.readArtifact("PropertyRegistry");
  writeFileSync(join(root, "abi", "PropertyRegistry.json"), JSON.stringify(abi, null, 2));
  const { chainId } = await ethers.provider.getNetwork();
  writeFileSync(
    join(root, "deployments", `${network.name}.json`),
    JSON.stringify({ address, chainId: Number(chainId), admin: admin.address, registrar, blockNumber: receipt?.blockNumber }, null, 2),
  );

  console.log(`PropertyRegistry deployed to ${address} on ${network.name} (chain ${chainId})`);
  console.log(`Registrar: ${registrar}`);
  console.log(`Set BLOCKCHAIN_CONTRACT_ADDRESS=${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
