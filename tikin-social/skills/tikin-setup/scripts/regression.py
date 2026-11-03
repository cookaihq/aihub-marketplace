"""One operator-approved ledger shared by every regression request and process.

This module never creates an approval or a ledger and never sends HTTP requests.
An existing service-side guard must enforce the approved binding before upstream IO.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit
import uuid

from request_reporting import atomic_write, record_lock

CAPS = {'paid_attempts': 40, 'zero_attempts': 40, 'local_attempts': 8}
GUARD_HEADER = 'X-Tikin-Regression-Binding'


class GateError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def money(value: Any) -> Decimal:
    if not isinstance(value, str) or len(value) > 64:
        raise GateError('unverified_price')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise GateError('unverified_price') from None
    if not number.is_finite() or number < 0 or number > Decimal('0.50'):
        raise GateError('unverified_price')
    return number


def require(condition: Any, reason: str) -> None:
    if not condition:
        raise GateError(reason)


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise GateError('invalid_regression_file')
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def absolute(value: Any) -> Path:
    require(isinstance(value, str), 'invalid_reference')
    path = Path(value)
    require(path.is_absolute() and str(path.resolve()) == value, 'invalid_reference')
    return path


def future(value: Any) -> bool:
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                return False
            value = stamp.timestamp()
        except ValueError:
            return False
    return type(value) in (int, float) and time.time() < value < time.time() + 86400


class Regression:
    def __init__(self, approval_path: str, base: str, key: str, fingerprint: str, side_effects: bool):
        self.approval_path = absolute(str(Path(approval_path).resolve()))
        self.approval_hash = sha(self.approval_path)
        self.approval = read(self.approval_path)
        a = self.approval
        require(a.get('schema_version') == 1, 'invalid_approval')
        self.path = absolute(a['ledger_path'])
        self.binding_path = absolute(a['binding_path'])
        self.proof_path = absolute(a['proof_path'])
        self.binding = a['binding_sha256']
        require(isinstance(self.binding, str) and len(self.binding) == 64 and
                all(c in '0123456789abcdef' for c in self.binding), 'invalid_binding')
        self.binding_data = targets = read(self.binding_path)
        require(targets.get('schema') == 'tikin.regression-binding.v1' and targets.get('environment') == 'test', 'invalid_binding')
        require(targets['client_base_url'] == base, 'wrong_target')
        require(targets['test_token_sha256'] == hashlib.sha256(key.encode()).hexdigest(), 'wrong_identity')
        # A configured production default can never be used as this regression's target.
        for field in ('client_base_url', 'new_api_base', 'return_route'):
            parsed = urlsplit(targets[field])
            require(parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and
                    not parsed.password and not parsed.fragment and not parsed.query and not parsed.path, 'invalid_target')
            require(parsed.hostname not in ('console.tikin.net', 'tikin.net', 'api.tikin.net'), 'production_target')
        self.limits = a['limits']
        for name, cap in CAPS.items():
            require(type(self.limits.get(name)) is int and 0 <= self.limits[name] <= cap, 'invalid_limits')
        require(money(self.limits['paid_usd']) <= Decimal('0.50'), 'invalid_limits')
        self.fingerprint = fingerprint
        self.operation = a.get('requests', {}).get(fingerprint)
        require(isinstance(self.operation, dict), 'unapproved_request')
        op = self.operation
        self.category = op['category']
        require(self.category in ('paid', 'zero', 'local'), 'invalid_category')
        require(type(op.get('side_effects')) is bool and op['side_effects'] == side_effects, 'unverified_side_effects')
        for name in ('max_units', 'upstream_attempts'):
            require(type(op.get(name)) is int and 1 <= op[name] <= 40, 'unverified_multiplicity')
        self.attempts = op['upstream_attempts']
        self.cost = money(op['price_usd']) * op['max_units'] * self.attempts
        require((self.category == 'paid' and self.cost > 0) or
                (self.category != 'paid' and self.cost == 0), 'unverified_price')
        if self.category == 'local':
            require(op.get('upstream_forbidden') is True and self.attempts == 1, 'unverified_local_rejection')
        self.verify()
        with record_lock(self.path):
            self.load()

    @property
    def reference(self) -> dict[str, str]:
        return {'campaign_id': self.approval['campaign_id'], 'ledger_path': str(self.path),
                'binding_sha256': self.binding}

    def verify(self) -> None:
        a = self.approval
        require(sha(self.approval_path) == self.approval_hash, 'approval_changed')
        require(future(a.get('expires_at')), 'approval_expired')
        require(sha(self.binding_path) == self.binding and future(self.binding_data.get('expires_at')), 'binding_changed_or_expired')
        require(sha(self.proof_path) == a['proof_sha256'], 'proof_changed')
        proof = read(self.proof_path)
        require(proof.get('environment') == 'test' and future(proof.get('expires_at')),
                'proof_expired_or_unverified')
        require(proof.get('schema') == 'tikin.regression-route-proof.v1' and proof.get('binding_sha256') == self.binding and
                proof.get('route_verified') is True, 'unproven_target')
        require(isinstance(self.operation.get('price_evidence_sha256'), str) and
                len(self.operation['price_evidence_sha256']) == 64 and
                self.operation['price_evidence_sha256'] == proof.get('price_evidence_sha256'), 'unverified_price')

    def verify_server(self, response: Any) -> None:
        require(isinstance(response, dict), 'server_binding_unproven')
        require(response == {**self.binding_data, 'binding_sha256': self.binding}, 'server_binding_unproven')

    def load(self) -> dict[str, Any]:
        # No lazy initialization: a missing ledger is not a new allowance.
        ledger = read(self.path)
        require(ledger.get('schema_version') == 1 and ledger.get('campaign_id') == self.approval['campaign_id'] and
                ledger.get('ledger_path') == str(self.path) and ledger.get('binding_sha256') == self.binding and
                ledger.get('limits') == self.limits and self.approval_hash in ledger.get('approval_sha256s', []),
                'ledger_binding_mismatch')
        require(isinstance(ledger.get('reservations'), list), 'invalid_ledger')
        return ledger

    def write(self, ledger: dict[str, Any]) -> None:
        atomic_write(self.path, json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')

    def reserve(self, record: Path) -> str:
        self.verify()
        with record_lock(self.path):
            ledger = self.load()
            require(ledger.get('not_before', 0) <= time.time(), 'cooldown')
            require(not any(entry['request_sha256'] == self.fingerprint and entry['outcome'] in ('reserved', 'unknown')
                            for entry in ledger['reservations']), 'unresolved_attempt')
            used = {name: 0 for name in CAPS}
            dollars = Decimal(0)
            for entry in ledger['reservations']:
                counter = entry['category'] + '_attempts'
                require(counter in used and type(entry['attempts']) is int and entry['attempts'] > 0, 'invalid_ledger')
                used[counter] += entry['attempts']
                dollars += money(entry['reserved_usd'])
            counter = self.category + '_attempts'
            require(used[counter] + self.attempts <= self.limits[counter] and
                    dollars + self.cost <= money(self.limits['paid_usd']), 'budget_exhausted')
            reservation = str(uuid.uuid4())
            ledger['reservations'].append({'id': reservation, 'request_sha256': self.fingerprint,
                'approval_sha256': self.approval_hash, 'category': self.category, 'attempts': self.attempts,
                'reserved_usd': str(self.cost), 'record': str(record), 'at': time.time(), 'outcome': 'reserved'})
            self.write(ledger)  # Durable reservation must finish before the caller can transmit.
            return reservation

    def finish(self, reservation: str, outcome: str, http_status: int | None, not_before: float) -> None:
        with record_lock(self.path):
            ledger = self.load()
            entry = next(item for item in ledger['reservations'] if item['id'] == reservation)
            entry.update(outcome=outcome, http_status=http_status, finished_at=time.time())
            ledger['not_before'] = max(ledger.get('not_before', 0), not_before)
            self.write(ledger)  # No refunds: timeout/failure can still have consumed the reservation.
