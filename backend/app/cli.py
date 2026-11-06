"""Operator commands. Run from backend/: python -m app.cli create-admin --email you@example.com"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.models import User, ValuationModelVersion
from app.services import audit, auth_service, valuation_service


def create_admin(email: str, display_name: str) -> int:
    password = getpass.getpass("Password (at least 12 characters): ")
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email.lower())):
            print("That email is already registered.", file=sys.stderr)
            return 1
        user = auth_service.register_user(db, email, password, display_name, "owner")
        user.roles.append(auth_service.get_role(db, "admin"))
        audit.record(db, "admin.created_by_cli", "user", user.id)
        db.commit()
    print(f"Administrator created: {email.lower()}")
    return 0


def list_models() -> int:
    with SessionLocal() as db:
        valuation_service.sync_artifacts(db)
        for record in db.scalars(select(ValuationModelVersion).order_by(ValuationModelVersion.trained_at.desc())):
            mlp = record.metrics["held_out_test"]["pytorch_mlp"]
            data = "synthetic" if record.trained_on_synthetic_data else "real"
            print(f"{record.version}  status={record.status}  beats_baseline={record.beats_baseline}  data={data}  mae={mlp['mae']:.0f}  r2={mlp['r2']:.3f}")
    return 0


def activate_model(version: str, admin_email: str) -> int:
    """Runs the same gated promotion as the admin page: approved, then active."""
    with SessionLocal() as db:
        valuation_service.sync_artifacts(db)
        admin = db.scalar(select(User).where(User.email == admin_email.lower()))
        if admin is None or not admin.has_role("admin"):
            print("That account is not an administrator.", file=sys.stderr)
            return 1
        try:
            if valuation_service.get_model_record(db, version).status == "candidate":
                valuation_service.promote(db, version, "approved", admin)
            valuation_service.promote(db, version, "active", admin)
        except AppError as exc:
            print(f"Refused: {exc.message}", file=sys.stderr)
            return 1
    print(f"Model {version} is now active.")
    return 0


def ensure_model(admin_email: str) -> int:
    """Used by the start script. Activates the newest model that beat its baseline, unless one is already active."""
    with SessionLocal() as db:
        valuation_service.sync_artifacts(db)
        if db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.status == "active")):
            print("A model is already active.")
            return 0
        candidate = db.scalar(
            select(ValuationModelVersion)
            .where(ValuationModelVersion.beats_baseline.is_(True), ValuationModelVersion.status.in_(("candidate", "approved")))
            .order_by(ValuationModelVersion.trained_at.desc())
        )
        version = None if candidate is None else candidate.version
    if version is None:
        print("No trained model that beats its baseline was found. Run the training script first.", file=sys.stderr)
        return 1
    return activate_model(version, admin_email)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Administrator")
    sub.add_parser("list-models")
    activate = sub.add_parser("activate-model")
    activate.add_argument("version")
    activate.add_argument("--admin-email", required=True)
    ensure = sub.add_parser("ensure-model")
    ensure.add_argument("--admin-email", required=True)
    args = parser.parse_args()
    if args.command == "ensure-model":
        return ensure_model(args.admin_email)
    if args.command == "list-models":
        return list_models()
    if args.command == "activate-model":
        return activate_model(args.version, args.admin_email)
    return create_admin(args.email, args.name)


if __name__ == "__main__":
    raise SystemExit(main())
