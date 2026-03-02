from __future__ import annotations

from flask import abort

from portal.services.workspace_store import materialize_people


def is_board_member(member_msn_id: str) -> bool:
    candidate = str(member_msn_id or "").strip()
    if not candidate:
        return False
    for person in materialize_people():
        if str(person.get("msn_id") or "").strip() == candidate:
            return True
    return False


def require_board_member(member_msn_id: str) -> None:
    if not is_board_member(member_msn_id):
        abort(403, description="member_msn_id is not an allowed board_member")

