"""AURORA CLI — U2.

Usage:
    python -m app.cli tenant validate <path> [<path> ...]
    python -m app.cli tenant load     <path> [--force]
    python -m app.cli tenant list
    python -m app.cli tenant reset    <tenant_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _validate_cmd(args: list[str]) -> int:
    from app.services.tenancy.pack_loader import validate_pack

    if not args:
        print("Usage: python -m app.cli tenant validate <path> [<path> ...]", file=sys.stderr)
        return 2

    bad = 0
    for path_str in args:
        p = Path(path_str)
        if not p.exists():
            print(f"MISSING {p}", file=sys.stderr)
            bad += 1
            continue
        try:
            pack = json.loads(p.read_bytes())
        except Exception as exc:
            print(f"FAIL    {p}  (JSON parse error: {exc})")
            bad += 1
            continue
        errs = validate_pack(pack)
        if errs:
            print(f"FAIL    {p}")
            for e in errs:
                print(f"         - {e}")
            bad += 1
        else:
            print(f"OK      {p}")

    return 1 if bad else 0


def _load_cmd(args: list[str]) -> int:
    from app.services.tenancy.pack_loader import load_pack, validate_pack

    force = "--force" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("Usage: python -m app.cli tenant load <path> [--force]", file=sys.stderr)
        return 2

    bad = 0
    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            print(f"ERROR  {p}: file not found", file=sys.stderr)
            bad += 1
            continue
        try:
            pack = json.loads(p.read_bytes())
        except Exception as exc:
            print(f"ERROR  {p}: JSON parse error: {exc}", file=sys.stderr)
            bad += 1
            continue

        errs = validate_pack(pack)
        if errs:
            print(f"ABORT  {p}: validation failed")
            for e in errs:
                print(f"         - {e}")
            bad += 1
            continue

        try:
            rec = load_pack(p, force=force)
            print(f"OK     loaded tenant '{rec.id}' ({rec.name})  hash={rec.pack_hash}")
        except Exception as exc:
            print(f"ERROR  {p}: {exc}", file=sys.stderr)
            bad += 1

    return 1 if bad else 0


def _list_cmd(args: list[str]) -> int:
    from app.db.control import list_tenants

    tenants = list_tenants()
    if not tenants:
        print("(no active tenants)")
        return 0

    fmt = "{:<20} {:<30} {:<16} {:<10}"
    print(fmt.format("ID", "NAME", "HASH", "STATUS"))
    print("-" * 80)
    for t in tenants:
        print(fmt.format(
            t.id,
            t.name[:30],
            (t.pack_hash or "—")[:16],
            t.status,
        ))
    return 0


def _reset_cmd(args: list[str]) -> int:
    if not args:
        print("Usage: python -m app.cli tenant reset <tenant_id>", file=sys.stderr)
        return 2

    tenant_id = args[0]
    from app.db.control import get_control_session, TenantRecord, tenant_db_path, _BACKUPS_DIR
    from app.core.tenancy import _invalidate_engine
    import shutil, datetime as _dt

    ctrl_db = get_control_session()
    try:
        rec: TenantRecord | None = ctrl_db.get(TenantRecord, tenant_id)
        if rec is None:
            print(f"ERROR: tenant '{tenant_id}' not found", file=sys.stderr)
            return 1

        db_path = tenant_db_path(tenant_id)
        if db_path.exists():
            ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_dir = _BACKUPS_DIR / f"{tenant_id}_{ts}_reset"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, backup_dir / f"{tenant_id}.db")
            db_path.unlink()
            print(f"Backed up to {backup_dir}")

        rec.status = "disabled"
        rec.pack_hash = None
        ctrl_db.commit()
        _invalidate_engine(tenant_id)
        print(f"OK     tenant '{tenant_id}' disabled and DB removed")
        return 0
    finally:
        ctrl_db.close()


def _tenant_cmd(args: list[str]) -> int:
    if not args:
        print("Subcommands: validate, load, list, reset", file=sys.stderr)
        return 2
    sub = args[0]
    rest = args[1:]
    if sub == "validate":
        return _validate_cmd(rest)
    elif sub == "load":
        return _load_cmd(rest)
    elif sub == "list":
        return _list_cmd(rest)
    elif sub == "reset":
        return _reset_cmd(rest)
    else:
        print(f"Unknown subcommand: {sub}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv)[1:]
    if not args:
        print("Usage: python -m app.cli <command> [args...]")
        print("Commands: tenant")
        return 2
    cmd = args[0]
    rest = args[1:]
    if cmd == "tenant":
        return _tenant_cmd(rest)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
