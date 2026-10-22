"""Receipt races must recover only identical, persisted provider evidence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid5

import pytest
from tools.facebook_inquiry import save_submission


@pytest.mark.parametrize("code_attribute", ["code", "pgcode"])
@pytest.mark.parametrize("outcome", ["identical", "changed", "missing", "other_error"])
def test_unique_receipt_race(code_attribute, outcome):
    answers = {"_facebook_consent": {"leadgen_id": "race", "form_id": "form",
        "submitted_at": "2026-10-21T12:00:00Z", "phone": "+12145550100"}}
    row = {"id": str(uuid5(NAMESPACE_URL, "wholesaleos:facebook:submission:race")),
        "lead_id": "lead", "leadgen_id": "race", "form_id": "form",
        "submitted_at": "2026-10-21T12:00:00Z", "phone_number": "+12145550100",
        "raw_answers": deepcopy(answers)}
    error = RuntimeError("database failure")
    setattr(error, code_attribute, "42501" if outcome == "other_error" else "23505")
    db = MagicMock()
    table = db.table.return_value
    table.upsert.return_value.execute.side_effect = error
    if outcome == "changed":
        row["raw_answers"]["_facebook_consent"]["form_id"] = "different"
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
        data=[] if outcome == "missing" else [row])
    if outcome == "identical":
        assert save_submission(db, "lead", answers) == answers
    else:
        match = {"changed": "conflicts with saved evidence", "missing": "persistence was not confirmed",
                 "other_error": "database failure"}[outcome]
        with pytest.raises(RuntimeError, match=match):
            save_submission(db, "lead", answers)
    if outcome == "other_error":
        table.select.assert_not_called()
    else:
        table.select.return_value.eq.assert_called_once_with("id", row["id"])
