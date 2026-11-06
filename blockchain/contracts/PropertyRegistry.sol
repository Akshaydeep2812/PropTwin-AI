// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title PropertyRegistry
/// @notice Tamper-evident commitments to off-chain property records.
/// @dev A "controller" is the address allowed to manage a record here. Controlling an address does not
/// establish legal ownership of a physical property, and a stored hash does not prove that the underlying
/// documents are authentic. No personal data, addresses, or documents are stored on-chain.
contract PropertyRegistry is AccessControl, Pausable {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    struct Record {
        bytes32 recordHash;
        address controller;
        uint64 version;
        uint64 updatedAt;
    }

    mapping(bytes32 propertyKey => Record) private _records;
    mapping(bytes32 propertyKey => address) public pendingController;

    event PropertyRegistered(bytes32 indexed propertyKey, bytes32 recordHash, address indexed controller, address indexed registrar);
    event RecordUpdated(bytes32 indexed propertyKey, bytes32 recordHash, uint64 version, address indexed updatedBy);
    event ValuationCommitted(bytes32 indexed propertyKey, bytes32 valuationHash, address indexed committedBy);
    event ControllerAssigned(bytes32 indexed propertyKey, address indexed previousController, address indexed newController);
    event TransferProposed(bytes32 indexed propertyKey, address indexed from, address indexed to);
    event TransferCancelled(bytes32 indexed propertyKey, address indexed from, address indexed to);
    event TransferAccepted(bytes32 indexed propertyKey, address indexed from, address indexed to);

    error AlreadyRegistered(bytes32 propertyKey);
    error NotRegistered(bytes32 propertyKey);
    error EmptyHash();
    error ZeroAddress();
    error NotAuthorized(address caller);
    error VersionMismatch(uint64 expected, uint64 actual);
    error NoPendingTransfer(bytes32 propertyKey);
    error InvalidTransferTarget(address target);
    error ControllerNotCustodial(address controller);

    constructor(address admin, address registrar) {
        if (admin == address(0) || registrar == address(0)) revert ZeroAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(PAUSER_ROLE, admin);
        _grantRole(REGISTRAR_ROLE, registrar);
    }

    modifier onlyRegistered(bytes32 propertyKey) {
        if (_records[propertyKey].version == 0) revert NotRegistered(propertyKey);
        _;
    }

    modifier onlyRegistrarOrController(bytes32 propertyKey) {
        if (!hasRole(REGISTRAR_ROLE, msg.sender) && _records[propertyKey].controller != msg.sender) {
            revert NotAuthorized(msg.sender);
        }
        _;
    }

    /// @notice Registers a property once. Only the application's registrar can do this.
    function register(bytes32 propertyKey, bytes32 recordHash, address controller) external onlyRole(REGISTRAR_ROLE) whenNotPaused {
        if (_records[propertyKey].version != 0) revert AlreadyRegistered(propertyKey);
        if (recordHash == bytes32(0)) revert EmptyHash();
        if (controller == address(0)) revert ZeroAddress();
        _records[propertyKey] = Record(recordHash, controller, 1, uint64(block.timestamp));
        emit PropertyRegistered(propertyKey, recordHash, controller, msg.sender);
    }

    /// @notice Commits a new record hash. The expected version rejects updates based on a stale read.
    function updateRecord(bytes32 propertyKey, bytes32 recordHash, uint64 expectedVersion)
        external
        onlyRegistered(propertyKey)
        onlyRegistrarOrController(propertyKey)
        whenNotPaused
    {
        if (recordHash == bytes32(0)) revert EmptyHash();
        Record storage record = _records[propertyKey];
        if (record.version != expectedVersion) revert VersionMismatch(expectedVersion, record.version);
        record.recordHash = recordHash;
        record.version = expectedVersion + 1;
        record.updatedAt = uint64(block.timestamp);
        emit RecordUpdated(propertyKey, recordHash, record.version, msg.sender);
    }

    /// @notice Records a commitment to a valuation. The valuation itself stays off-chain.
    function commitValuation(bytes32 propertyKey, bytes32 valuationHash)
        external
        onlyRegistered(propertyKey)
        onlyRegistrarOrController(propertyKey)
        whenNotPaused
    {
        if (valuationHash == bytes32(0)) revert EmptyHash();
        emit ValuationCommitted(propertyKey, valuationHash, msg.sender);
    }

    /// @notice Hands a record held by the registrar over to a user's own wallet.
    /// @dev Only possible while the registrar holds it, so a registrar can never take a record back from a user.
    function assignController(bytes32 propertyKey, address newController) external onlyRegistered(propertyKey) onlyRole(REGISTRAR_ROLE) whenNotPaused {
        if (newController == address(0)) revert ZeroAddress();
        address current = _records[propertyKey].controller;
        if (!hasRole(REGISTRAR_ROLE, current)) revert ControllerNotCustodial(current);
        _records[propertyKey].controller = newController;
        delete pendingController[propertyKey];
        emit ControllerAssigned(propertyKey, current, newController);
    }

    /// @notice First step of a transfer. Control does not move until the recipient accepts.
    function proposeTransfer(bytes32 propertyKey, address to) external onlyRegistered(propertyKey) whenNotPaused {
        Record storage record = _records[propertyKey];
        if (record.controller != msg.sender) revert NotAuthorized(msg.sender);
        if (to == address(0) || to == msg.sender) revert InvalidTransferTarget(to);
        pendingController[propertyKey] = to;
        emit TransferProposed(propertyKey, msg.sender, to);
    }

    function cancelTransfer(bytes32 propertyKey) external onlyRegistered(propertyKey) whenNotPaused {
        Record storage record = _records[propertyKey];
        if (record.controller != msg.sender) revert NotAuthorized(msg.sender);
        address to = pendingController[propertyKey];
        if (to == address(0)) revert NoPendingTransfer(propertyKey);
        delete pendingController[propertyKey];
        emit TransferCancelled(propertyKey, msg.sender, to);
    }

    /// @notice Second step of a transfer. Only the proposed recipient can complete it.
    function acceptTransfer(bytes32 propertyKey) external onlyRegistered(propertyKey) whenNotPaused {
        address to = pendingController[propertyKey];
        if (to == address(0)) revert NoPendingTransfer(propertyKey);
        if (to != msg.sender) revert NotAuthorized(msg.sender);
        Record storage record = _records[propertyKey];
        address from = record.controller;
        record.controller = to;
        delete pendingController[propertyKey];
        emit TransferAccepted(propertyKey, from, to);
    }

    function getRecord(bytes32 propertyKey) external view returns (Record memory) {
        return _records[propertyKey];
    }

    function isRegistered(bytes32 propertyKey) external view returns (bool) {
        return _records[propertyKey].version != 0;
    }

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }
}
