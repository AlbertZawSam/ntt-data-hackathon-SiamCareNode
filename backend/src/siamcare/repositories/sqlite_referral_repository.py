"""SQLite adapter: one short transaction per write, with optimistic concurrency."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from siamcare.errors import ConflictError, PersistenceError
from siamcare.models.referral import (
    HospitalRequest,
    Referral,
    ReferralEvent,
    RequestStatus,
)


class SqliteReferralRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PersistenceError(f"Cannot create database directory: {exc}") from exc
        schema = Path(__file__).with_name("referral_schema.sql").read_text()
        with self._connection() as connection:
            # executescript controls its own transaction. All DDL is repeatable.
            connection.executescript(f"BEGIN IMMEDIATE;\n{schema}\nCOMMIT;")

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Database operation failed at {self.path}: {exc}"
            ) from exc
        finally:
            if connection is not None:
                # Also rolls back domain conflicts and unexpected exceptions.
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def get_referral(self, referral_id: str) -> Referral | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM referrals WHERE referral_id = ?", (referral_id,)
            ).fetchone()
        return Referral.model_validate(dict(row)) if row else None

    def list_referrals(self) -> tuple[Referral, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM referrals ORDER BY created_at, referral_id"
            ).fetchall()
        return tuple(Referral.model_validate(dict(row)) for row in rows)

    def get_request(self, request_id: str) -> HospitalRequest | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM hospital_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        return HospitalRequest.model_validate(dict(row)) if row else None

    def list_requests(
        self, *, referral_id: str | None = None, hospital_id: str | None = None
    ) -> tuple[HospitalRequest, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM hospital_requests
                WHERE (? IS NULL OR referral_id = ?)
                  AND (? IS NULL OR hospital_id = ?)
                ORDER BY created_at, request_id""",
                (referral_id, referral_id, hospital_id, hospital_id),
            ).fetchall()
        return tuple(HospitalRequest.model_validate(dict(row)) for row in rows)

    def history(self, referral_id: str) -> tuple[ReferralEvent, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM referral_events WHERE referral_id = ? ORDER BY version",
                (referral_id,),
            ).fetchall()
        return tuple(
            ReferralEvent.model_validate(
                {**dict(row), "details": json.loads(row["details"])}
            )
            for row in rows
        )

    @staticmethod
    def _append_event(connection: sqlite3.Connection, event: ReferralEvent) -> None:
        connection.execute(
            """INSERT INTO referral_events
            (event_id, referral_id, action, actor_id, actor_role,
             timestamp, version, details)
            VALUES (:event_id, :referral_id, :action, :actor_id, :actor_role,
                    :timestamp, :version, :details)""",
            {**event.model_dump(mode="json"), "details": json.dumps(event.details)},
        )

    @staticmethod
    def _check_event(referral: Referral, event: ReferralEvent) -> None:
        if (
            event.referral_id != referral.referral_id
            or event.version != referral.version
        ):
            raise PersistenceError("Event must identify the same referral and version")

    def create(self, referral: Referral, event: ReferralEvent) -> None:
        self._check_event(referral, event)
        with self._connection(write=True) as connection:
            connection.execute(
                """INSERT INTO referrals
                (referral_id, patient_reference, specialty, urgency,
                 referring_clinician_id, status, selected_request_id,
                 created_at, updated_at, version)
                VALUES (:referral_id, :patient_reference, :specialty, :urgency,
                        :referring_clinician_id, :status, :selected_request_id,
                        :created_at, :updated_at, :version)""",
                referral.model_dump(mode="json"),
            )
            self._append_event(connection, event)

    def save_transition(
        self,
        referral: Referral,
        event: ReferralEvent,
        request: HospitalRequest | None = None,
    ) -> None:
        self._check_event(referral, event)
        if request is not None and request.referral_id != referral.referral_id:
            raise PersistenceError("Request must belong to the same referral")
        with self._connection(write=True) as connection:
            changed = connection.execute(
                """UPDATE referrals SET status = :status,
                    selected_request_id = :selected_request_id,
                    updated_at = :updated_at, version = :version
                WHERE referral_id = :referral_id AND version = :previous_version""",
                {
                    **referral.model_dump(mode="json"),
                    "previous_version": referral.version - 1,
                },
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "Referral changed concurrently; reload before retrying"
                )
            if request is not None:
                self._save_request(connection, request)
            self._append_event(connection, event)

    @staticmethod
    def _save_request(connection: sqlite3.Connection, request: HospitalRequest) -> None:
        values = request.model_dump(mode="json")
        if request.status == RequestStatus.PENDING:
            connection.execute(
                """INSERT INTO hospital_requests
                (request_id, referral_id, hospital_id, status,
                 response_reason, created_at, responded_at)
                VALUES (:request_id, :referral_id, :hospital_id, :status,
                        :response_reason, :created_at, :responded_at)""",
                values,
            )
        else:
            previous = (
                RequestStatus.ACCEPTED
                if request.status == RequestStatus.CANCELLED
                else RequestStatus.PENDING
            )
            changed = connection.execute(
                """UPDATE hospital_requests SET status = :status,
                    response_reason = :response_reason, responded_at = :responded_at
                WHERE request_id = :request_id AND referral_id = :referral_id
                    AND status = :previous""",
                {**values, "previous": previous},
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "Request changed concurrently; reload before retrying"
                )
