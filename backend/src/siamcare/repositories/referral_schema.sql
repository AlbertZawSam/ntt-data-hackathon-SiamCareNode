CREATE TABLE IF NOT EXISTS referrals (
    referral_id TEXT PRIMARY KEY,
    patient_reference TEXT NOT NULL,
    specialty TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('routine', 'time-critical')),
    referring_clinician_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'open', 'awaiting_hospital', 'hospital_accepted',
        'awaiting_review', 'approved', 'rejected'
    )),
    selected_request_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    CHECK ((status = 'open') = (selected_request_id IS NULL)),
    FOREIGN KEY (selected_request_id, referral_id)
        REFERENCES hospital_requests(request_id, referral_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS hospital_requests (
    request_id TEXT PRIMARY KEY,
    referral_id TEXT NOT NULL REFERENCES referrals(referral_id),
    hospital_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled')),
    response_reason TEXT,
    created_at TEXT NOT NULL,
    responded_at TEXT,
    UNIQUE (request_id, referral_id),
    CHECK ((status = 'pending') = (responded_at IS NULL)),
    CHECK (status != 'declined' OR length(trim(response_reason)) > 0
        AND response_reason IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_request
    ON hospital_requests(referral_id) WHERE status IN ('pending', 'accepted');
CREATE INDEX IF NOT EXISTS requests_by_hospital ON hospital_requests(hospital_id);
CREATE TABLE IF NOT EXISTS referral_events (
    event_id TEXT PRIMARY KEY,
    referral_id TEXT NOT NULL REFERENCES referrals(referral_id),
    action TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    version INTEGER NOT NULL,
    details TEXT NOT NULL,
    UNIQUE (referral_id, version)
);
