import { loadFixture } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { expect } from "chai";
import { ethers } from "hardhat";

const KEY = ethers.id("proptwin:property:one");
const OTHER_KEY = ethers.id("proptwin:property:two");
const HASH_1 = ethers.id("record-v1");
const HASH_2 = ethers.id("record-v2");
const ZERO_HASH = ethers.ZeroHash;

async function deployFixture() {
  const [admin, registrar, owner, buyer, stranger] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("PropertyRegistry");
  const registry = await factory.deploy(admin.address, registrar.address);
  return { registry, admin, registrar, owner, buyer, stranger };
}

async function registeredFixture() {
  const context = await deployFixture();
  await context.registry.connect(context.registrar).register(KEY, HASH_1, context.owner.address);
  return context;
}

describe("PropertyRegistry", () => {
  describe("deployment", () => {
    it("assigns roles and rejects zero addresses", async () => {
      const { registry, admin, registrar } = await loadFixture(deployFixture);
      expect(await registry.hasRole(await registry.REGISTRAR_ROLE(), registrar.address)).to.equal(true);
      expect(await registry.hasRole(await registry.REGISTRAR_ROLE(), admin.address)).to.equal(false);
      expect(await registry.hasRole(await registry.PAUSER_ROLE(), admin.address)).to.equal(true);
      const factory = await ethers.getContractFactory("PropertyRegistry");
      await expect(factory.deploy(ethers.ZeroAddress, registrar.address)).to.be.revertedWithCustomError(registry, "ZeroAddress");
      await expect(factory.deploy(admin.address, ethers.ZeroAddress)).to.be.revertedWithCustomError(registry, "ZeroAddress");
    });
  });

  describe("registration", () => {
    it("stores the record and emits an event", async () => {
      const { registry, registrar, owner } = await loadFixture(deployFixture);
      await expect(registry.connect(registrar).register(KEY, HASH_1, owner.address))
        .to.emit(registry, "PropertyRegistered")
        .withArgs(KEY, HASH_1, owner.address, registrar.address);
      const record = await registry.getRecord(KEY);
      expect(record.recordHash).to.equal(HASH_1);
      expect(record.controller).to.equal(owner.address);
      expect(record.version).to.equal(1n);
      expect(await registry.isRegistered(KEY)).to.equal(true);
    });

    it("rejects a duplicate registration, even from the registrar", async () => {
      const { registry, registrar, buyer } = await loadFixture(registeredFixture);
      await expect(registry.connect(registrar).register(KEY, HASH_2, buyer.address))
        .to.be.revertedWithCustomError(registry, "AlreadyRegistered")
        .withArgs(KEY);
      expect((await registry.getRecord(KEY)).recordHash).to.equal(HASH_1);
    });

    it("rejects anyone but the registrar", async () => {
      const { registry, admin, stranger, owner } = await loadFixture(deployFixture);
      for (const caller of [admin, stranger, owner]) {
        await expect(registry.connect(caller).register(KEY, HASH_1, owner.address)).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
      }
    });

    it("rejects an empty hash or controller", async () => {
      const { registry, registrar, owner } = await loadFixture(deployFixture);
      await expect(registry.connect(registrar).register(KEY, ZERO_HASH, owner.address)).to.be.revertedWithCustomError(registry, "EmptyHash");
      await expect(registry.connect(registrar).register(KEY, HASH_1, ethers.ZeroAddress)).to.be.revertedWithCustomError(registry, "ZeroAddress");
    });

    it("reports an unregistered property as empty", async () => {
      const { registry } = await loadFixture(deployFixture);
      expect(await registry.isRegistered(OTHER_KEY)).to.equal(false);
      expect((await registry.getRecord(OTHER_KEY)).version).to.equal(0n);
    });
  });

  describe("updates", () => {
    it("lets the controller and the registrar update, bumping the version", async () => {
      const { registry, registrar, owner } = await loadFixture(registeredFixture);
      await expect(registry.connect(owner).updateRecord(KEY, HASH_2, 1)).to.emit(registry, "RecordUpdated").withArgs(KEY, HASH_2, 2n, owner.address);
      await expect(registry.connect(registrar).updateRecord(KEY, HASH_1, 2)).to.emit(registry, "RecordUpdated").withArgs(KEY, HASH_1, 3n, registrar.address);
      expect((await registry.getRecord(KEY)).version).to.equal(3n);
    });

    it("rejects unauthorized updates and leaves the record unchanged", async () => {
      const { registry, stranger, admin } = await loadFixture(registeredFixture);
      for (const caller of [stranger, admin]) {
        await expect(registry.connect(caller).updateRecord(KEY, HASH_2, 1)).to.be.revertedWithCustomError(registry, "NotAuthorized").withArgs(caller.address);
      }
      expect((await registry.getRecord(KEY)).recordHash).to.equal(HASH_1);
    });

    it("rejects a stale version", async () => {
      const { registry, owner } = await loadFixture(registeredFixture);
      await registry.connect(owner).updateRecord(KEY, HASH_2, 1);
      await expect(registry.connect(owner).updateRecord(KEY, HASH_1, 1)).to.be.revertedWithCustomError(registry, "VersionMismatch").withArgs(1n, 2n);
    });

    it("rejects an empty hash and an unregistered property", async () => {
      const { registry, registrar, owner } = await loadFixture(registeredFixture);
      await expect(registry.connect(owner).updateRecord(KEY, ZERO_HASH, 1)).to.be.revertedWithCustomError(registry, "EmptyHash");
      await expect(registry.connect(registrar).updateRecord(OTHER_KEY, HASH_2, 1)).to.be.revertedWithCustomError(registry, "NotRegistered");
    });
  });

  describe("valuation commitments", () => {
    it("emits an event for authorized callers only", async () => {
      const { registry, owner, stranger } = await loadFixture(registeredFixture);
      await expect(registry.connect(owner).commitValuation(KEY, HASH_2)).to.emit(registry, "ValuationCommitted").withArgs(KEY, HASH_2, owner.address);
      await expect(registry.connect(stranger).commitValuation(KEY, HASH_2)).to.be.revertedWithCustomError(registry, "NotAuthorized");
    });
  });

  describe("controller assignment", () => {
    it("lets the registrar hand over a record it holds", async () => {
      const { registry, registrar, owner } = await loadFixture(deployFixture);
      await registry.connect(registrar).register(KEY, HASH_1, registrar.address);
      await expect(registry.connect(registrar).assignController(KEY, owner.address)).to.emit(registry, "ControllerAssigned").withArgs(KEY, registrar.address, owner.address);
      expect((await registry.getRecord(KEY)).controller).to.equal(owner.address);
    });

    it("never lets the registrar take a record back from a user", async () => {
      const { registry, registrar, stranger } = await loadFixture(registeredFixture);
      await expect(registry.connect(registrar).assignController(KEY, stranger.address)).to.be.revertedWithCustomError(registry, "ControllerNotCustodial");
    });

    it("rejects other callers", async () => {
      const { registry, registrar, stranger } = await loadFixture(deployFixture);
      await registry.connect(registrar).register(KEY, HASH_1, registrar.address);
      await expect(registry.connect(stranger).assignController(KEY, stranger.address)).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
    });
  });

  describe("ownership transfer", () => {
    it("completes in two steps, and proposing alone moves nothing", async () => {
      const { registry, owner, buyer } = await loadFixture(registeredFixture);
      await expect(registry.connect(owner).proposeTransfer(KEY, buyer.address)).to.emit(registry, "TransferProposed").withArgs(KEY, owner.address, buyer.address);
      expect((await registry.getRecord(KEY)).controller).to.equal(owner.address);
      expect(await registry.pendingController(KEY)).to.equal(buyer.address);

      await expect(registry.connect(buyer).acceptTransfer(KEY)).to.emit(registry, "TransferAccepted").withArgs(KEY, owner.address, buyer.address);
      expect((await registry.getRecord(KEY)).controller).to.equal(buyer.address);
      expect(await registry.pendingController(KEY)).to.equal(ethers.ZeroAddress);
    });

    it("rejects a proposal from anyone but the controller, including the registrar", async () => {
      const { registry, registrar, stranger, buyer } = await loadFixture(registeredFixture);
      for (const caller of [registrar, stranger]) {
        await expect(registry.connect(caller).proposeTransfer(KEY, buyer.address)).to.be.revertedWithCustomError(registry, "NotAuthorized");
      }
    });

    it("rejects invalid targets", async () => {
      const { registry, owner } = await loadFixture(registeredFixture);
      await expect(registry.connect(owner).proposeTransfer(KEY, ethers.ZeroAddress)).to.be.revertedWithCustomError(registry, "InvalidTransferTarget");
      await expect(registry.connect(owner).proposeTransfer(KEY, owner.address)).to.be.revertedWithCustomError(registry, "InvalidTransferTarget");
    });

    it("rejects acceptance by anyone but the proposed recipient", async () => {
      const { registry, registrar, owner, buyer, stranger } = await loadFixture(registeredFixture);
      await registry.connect(owner).proposeTransfer(KEY, buyer.address);
      for (const caller of [stranger, registrar, owner]) {
        await expect(registry.connect(caller).acceptTransfer(KEY)).to.be.revertedWithCustomError(registry, "NotAuthorized").withArgs(caller.address);
      }
      expect((await registry.getRecord(KEY)).controller).to.equal(owner.address);
    });

    it("rejects acceptance with nothing pending, and a repeat acceptance", async () => {
      const { registry, owner, buyer } = await loadFixture(registeredFixture);
      await expect(registry.connect(buyer).acceptTransfer(KEY)).to.be.revertedWithCustomError(registry, "NoPendingTransfer");
      await registry.connect(owner).proposeTransfer(KEY, buyer.address);
      await registry.connect(buyer).acceptTransfer(KEY);
      await expect(registry.connect(buyer).acceptTransfer(KEY)).to.be.revertedWithCustomError(registry, "NoPendingTransfer");
    });

    it("lets the controller cancel, after which acceptance fails", async () => {
      const { registry, owner, buyer, stranger } = await loadFixture(registeredFixture);
      await registry.connect(owner).proposeTransfer(KEY, buyer.address);
      await expect(registry.connect(stranger).cancelTransfer(KEY)).to.be.revertedWithCustomError(registry, "NotAuthorized");
      await expect(registry.connect(owner).cancelTransfer(KEY)).to.emit(registry, "TransferCancelled").withArgs(KEY, owner.address, buyer.address);
      await expect(registry.connect(buyer).acceptTransfer(KEY)).to.be.revertedWithCustomError(registry, "NoPendingTransfer");
    });

    it("gives the new controller full rights and removes them from the old one", async () => {
      const { registry, owner, buyer } = await loadFixture(registeredFixture);
      await registry.connect(owner).proposeTransfer(KEY, buyer.address);
      await registry.connect(buyer).acceptTransfer(KEY);
      await expect(registry.connect(owner).updateRecord(KEY, HASH_2, 1)).to.be.revertedWithCustomError(registry, "NotAuthorized");
      await expect(registry.connect(buyer).updateRecord(KEY, HASH_2, 1)).to.emit(registry, "RecordUpdated");
    });
  });

  describe("pause", () => {
    it("blocks every state change while paused, then resumes", async () => {
      const { registry, admin, registrar, owner, buyer } = await loadFixture(registeredFixture);
      await registry.connect(owner).proposeTransfer(KEY, buyer.address);
      await registry.connect(admin).pause();
      const paused = [
        registry.connect(registrar).register(OTHER_KEY, HASH_1, owner.address),
        registry.connect(owner).updateRecord(KEY, HASH_2, 1),
        registry.connect(owner).commitValuation(KEY, HASH_2),
        registry.connect(owner).proposeTransfer(KEY, admin.address),
        registry.connect(owner).cancelTransfer(KEY),
        registry.connect(buyer).acceptTransfer(KEY),
      ];
      for (const attempt of paused) {
        await expect(attempt).to.be.revertedWithCustomError(registry, "EnforcedPause");
      }
      expect((await registry.getRecord(KEY)).recordHash).to.equal(HASH_1);
      await registry.connect(admin).unpause();
      await expect(registry.connect(owner).updateRecord(KEY, HASH_2, 1)).to.emit(registry, "RecordUpdated");
    });

    it("can only be toggled by the pauser", async () => {
      const { registry, registrar, stranger } = await loadFixture(deployFixture);
      for (const caller of [registrar, stranger]) {
        await expect(registry.connect(caller).pause()).to.be.revertedWithCustomError(registry, "AccessControlUnauthorizedAccount");
      }
    });
  });
});
