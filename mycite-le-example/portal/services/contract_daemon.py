from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from portal.services.contract_store import (
    ContractAlreadyExistsError,
    ContractValidationError,
    create_contract,
    update_contract,
)
from portal.services.outbound_requests import post_signed_inbox
from portal.services.request_log_store import append_event


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _private_dir() -> Path:
    return _base_dir() / "private"


def _data_dir() -> Path:
    return _base_dir() / "data"


def _config_path(msn_id: str) -> Path:
    return _private_dir() / f"mycite-config-{msn_id}.json"


def _request_log_path(msn_id: str) -> Path:
    return _private_dir() / "request_log" / f"{msn_id}.ndjson"


def _state_path() -> Path:
    return _private_dir() / "daemon_state" / "contract_daemon.json"


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return payload


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"last_processed_line": 0}
    try:
        state = _read_json(path)
    except Exception:
        return {"last_processed_line": 0}

    last_line = state.get("last_processed_line")
    if not isinstance(last_line, int) or last_line < 0:
        last_line = 0
    return {"last_processed_line": last_line}


def _write_state(last_processed_line: int) -> None:
    _write_json(_state_path(), {"last_processed_line": int(max(last_processed_line, 0))})


def _iter_unprocessed_events(log_path: Path, start_line: int) -> Tuple[Iterable[Tuple[int, Dict[str, Any]]], int]:
    if not log_path.exists():
        return [], start_line

    events: list[Tuple[int, Dict[str, Any]]] = []
    last_line = start_line
    with log_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            last_line = line_no
            if line_no <= start_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                events.append((line_no, payload))
    return events, last_line


def _load_contract_policy(msn_id: str) -> Dict[str, Any]:
    cfg_path = _config_path(msn_id)
    default_policy = {
        "allow_counterparties": [],
        "auto_accept_types": [],
        "require_manual_accept": False,
        "default_response": "decline",
        "counterparty_base_urls": {},
    }
    if not cfg_path.exists():
        return default_policy
    try:
        cfg = _read_json(cfg_path)
    except Exception:
        return default_policy

    raw = cfg.get("contract_policy")
    if not isinstance(raw, dict):
        return default_policy

    policy = dict(default_policy)
    policy.update(raw)
    if not isinstance(policy.get("allow_counterparties"), list):
        policy["allow_counterparties"] = []
    if not isinstance(policy.get("auto_accept_types"), list):
        policy["auto_accept_types"] = []
    if not isinstance(policy.get("counterparty_base_urls"), dict):
        policy["counterparty_base_urls"] = {}
    policy["require_manual_accept"] = bool(policy.get("require_manual_accept"))
    policy["default_response"] = str(policy.get("default_response") or "decline").strip().lower()
    return policy


def _resolve_payload_ref(payload_ref: str) -> Path:
    raw = (payload_ref or "").strip()
    if not raw:
        raise FileNotFoundError("Missing payload_ref")

    ref_path = Path(raw)
    if ref_path.is_absolute():
        return ref_path
    return _base_dir() / ref_path


def _decide_offer(policy: Dict[str, Any], from_msn_id: str, contract_type: str) -> bool:
    default_accept = str(policy.get("default_response") or "decline").lower() == "accept"
    if bool(policy.get("require_manual_accept")):
        return default_accept

    allow_counterparties = {str(v).strip() for v in policy.get("allow_counterparties", []) if str(v).strip()}
    auto_accept_types = {str(v).strip() for v in policy.get("auto_accept_types", []) if str(v).strip()}

    if allow_counterparties and from_msn_id not in allow_counterparties:
        return default_accept
    if auto_accept_types and contract_type not in auto_accept_types:
        return default_accept
    if allow_counterparties or auto_accept_types:
        return True
    return default_accept


def _extract_contract(event: Dict[str, Any], offer_payload: Dict[str, Any], local_msn_id: str) -> Dict[str, Any]:
    contract = offer_payload.get("contract")
    contract_dict = contract if isinstance(contract, dict) else {}
    from_msn_id = str(event.get("from_msn_id") or contract_dict.get("initiator_msn_id") or "").strip()
    contract_id = str(contract_dict.get("contract_id") or event.get("event_id") or uuid.uuid4().hex).strip()
    contract_type = str(contract_dict.get("contract_type") or "symmetric_key").strip()
    return {
        "contract_id": contract_id,
        "contract_type": contract_type,
        "counterparty_msn_id": from_msn_id,
        "initiator_msn_id": str(contract_dict.get("initiator_msn_id") or from_msn_id).strip(),
        "counterparty_local_msn_id": local_msn_id,
        "capabilities": contract_dict.get("capabilities", []),
        "source_payload_ref": str(event.get("payload_ref") or "").strip(),
    }


def _upsert_contract(contract_metadata: Dict[str, Any], status: str) -> None:
    metadata = dict(contract_metadata)
    contract_id = str(metadata.pop("contract_id"))
    metadata["status"] = status
    metadata["updated_by"] = "contract_daemon"
    try:
        create_contract(_private_dir(), {"contract_id": contract_id, **metadata})
    except ContractAlreadyExistsError:
        patch = dict(metadata)
        patch["status"] = status
        update_contract(_private_dir(), contract_id, patch)
    except ContractValidationError:
        # Keep daemon resilient to malformed inbound data.
        return


def _maybe_send_response(
    *,
    msn_id: str,
    counterparty_msn_id: str,
    contract_id: str,
    contract_type: str,
    accepted: bool,
    policy: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    base_urls = policy.get("counterparty_base_urls", {})
    target_base_url = ""
    if isinstance(base_urls, dict):
        target_base_url = str(base_urls.get(counterparty_msn_id) or "").strip()
    if not target_base_url:
        target_base_url = str(os.environ.get("MYCITE_COUNTERPARTY_BASE_URL", "")).strip()
    if not target_base_url:
        return 0, {"ok": False, "reason": "no_target_base_url"}

    msg_type = "contract.accept" if accepted else "contract.decline"
    response_body = {
        "schema": "mycite.message.v0",
        "type": msg_type,
        "msg_id": f"{contract_id}-{msg_type}-{int(time.time())}",
        "contract": {
            "contract_id": contract_id,
            "contract_type": contract_type,
            "initiator_msn_id": counterparty_msn_id,
            "counterparty_msn_id": msn_id,
            "status": "active" if accepted else "revoked",
        },
    }
    return post_signed_inbox(
        target_base_url=target_base_url,
        target_msn_id=counterparty_msn_id,
        sender_msn_id=msn_id,
        body=response_body,
    )


def run_once(msn_id: str) -> Dict[str, Any]:
    state = _read_state()
    start_line = int(state.get("last_processed_line", 0))
    events, last_line = _iter_unprocessed_events(_request_log_path(msn_id), start_line)
    policy = _load_contract_policy(msn_id)

    processed = 0
    accepted_count = 0
    declined_count = 0

    for _, event in events:
        if event.get("type") != "contract.offer.received":
            continue
        payload_ref = str(event.get("payload_ref") or "").strip()
        if not payload_ref:
            continue

        try:
            offer_payload = _read_json(_resolve_payload_ref(payload_ref))
        except Exception:
            continue

        contract = _extract_contract(event, offer_payload, msn_id)
        decision_accept = _decide_offer(
            policy,
            contract["counterparty_msn_id"],
            contract["contract_type"],
        )
        status = "active" if decision_accept else "revoked"
        _upsert_contract(contract, status)

        send_status, send_payload = _maybe_send_response(
            msn_id=msn_id,
            counterparty_msn_id=contract["counterparty_msn_id"],
            contract_id=contract["contract_id"],
            contract_type=contract["contract_type"],
            accepted=decision_accept,
            policy=policy,
        )

        out_type = "contract.accept.sent" if decision_accept else "contract.decline.sent"
        append_event(
            _private_dir(),
            msn_id,
            {
                "type": out_type,
                "from_msn_id": msn_id,
                "to_msn_id": contract["counterparty_msn_id"],
                "contract_id": contract["contract_id"],
                "status": "sent" if send_status else "stubbed",
                "details": {
                    "source_payload_ref": payload_ref,
                    "outbound_status_code": send_status,
                    "outbound_response": send_payload,
                },
            },
        )

        processed += 1
        if decision_accept:
            accepted_count += 1
        else:
            declined_count += 1

    _write_state(last_line)
    return {
        "ok": True,
        "msn_id": msn_id,
        "processed_offers": processed,
        "accepted": accepted_count,
        "declined": declined_count,
        "last_processed_line": last_line,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Process contract.offer request-log events.")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
    parser.add_argument("--msn-id", required=True, help="Local portal MSN ID")
    args = parser.parse_args()

    summary = run_once(args.msn_id)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
