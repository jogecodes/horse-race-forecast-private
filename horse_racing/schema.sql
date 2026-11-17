PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY CHECK(version=3));
INSERT OR IGNORE INTO schema_version VALUES(3);
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
 access_notes TEXT NOT NULL, rights_notes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), url TEXT NOT NULL,
 observed_at TEXT NOT NULL, published_at TEXT, media_type TEXT NOT NULL,
 body TEXT NOT NULL, sha256 TEXT NOT NULL, collection_method TEXT NOT NULL,
 UNIQUE(url, sha256, observed_at)
);
CREATE TABLE IF NOT EXISTS entities(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('horse','jockey','trainer','stable','breeder')),
 name TEXT NOT NULL, identity_scope TEXT NOT NULL,
 UNIQUE(kind,name,identity_scope)
);
CREATE TABLE IF NOT EXISTS meetings(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), external_id TEXT NOT NULL,
 race_date TEXT NOT NULL, venue TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'Europe/Madrid'
);
CREATE TABLE IF NOT EXISTS races(
 id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meetings(id), race_number INTEGER NOT NULL CHECK(race_number>0)
);
CREATE TABLE IF NOT EXISTS race_versions(
 id TEXT PRIMARY KEY, race_id TEXT NOT NULL REFERENCES races(id), snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
 phase TEXT NOT NULL CHECK(phase IN ('declaration','result')),
 external_number TEXT NOT NULL, title TEXT NOT NULL, distance_m INTEGER CHECK(distance_m>0),
 header_raw TEXT NOT NULL, conditions_raw TEXT,
 UNIQUE(race_id,snapshot_id,phase)
);
CREATE TABLE IF NOT EXISTS entries(
 id TEXT PRIMARY KEY, race_version_id TEXT NOT NULL REFERENCES race_versions(id),
 cloth INTEGER NOT NULL CHECK(cloth>0), horse_id TEXT NOT NULL REFERENCES entities(id),
 jockey_id TEXT REFERENCES entities(id), trainer_id TEXT REFERENCES entities(id),
 stable_id TEXT REFERENCES entities(id), weight_kg REAL, draw INTEGER,
 withdrawn INTEGER NOT NULL CHECK(withdrawn IN(0,1)), horse_raw TEXT NOT NULL,
 source_line INTEGER NOT NULL, row_raw TEXT NOT NULL,
 UNIQUE(race_version_id,cloth)
);
-- Outcome tables must never be copied into a forecaster's packet database.
CREATE TABLE IF NOT EXISTS results(
 id TEXT PRIMARY KEY, race_version_id TEXT NOT NULL REFERENCES race_versions(id),
 cloth INTEGER CHECK(cloth>0), horse_id TEXT NOT NULL REFERENCES entities(id),
 position INTEGER CHECK(position>0), status_raw TEXT NOT NULL, margin_raw TEXT,
 jockey_id TEXT REFERENCES entities(id), trainer_id TEXT REFERENCES entities(id),
 stable_id TEXT REFERENCES entities(id), breeder_id TEXT REFERENCES entities(id),
 weight_kg REAL, draw INTEGER, horse_raw TEXT NOT NULL, source_line INTEGER NOT NULL,
 row_raw TEXT NOT NULL, UNIQUE(race_version_id,cloth), UNIQUE(race_version_id,horse_id)
);
CREATE TABLE IF NOT EXISTS quality_issues(
 id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
 race_id TEXT REFERENCES races(id), code TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
 text TEXT NOT NULL, entity_id TEXT REFERENCES entities(id),
 related_race_id TEXT REFERENCES races(id), kind TEXT NOT NULL CHECK(kind IN ('context','declaration','result')),
 locator TEXT NOT NULL, UNIQUE(snapshot_id,text,locator)
);
CREATE TABLE IF NOT EXISTS forecast_runs(
 id TEXT PRIMARY KEY, target_race_id TEXT NOT NULL REFERENCES races(id), cutoff TEXT NOT NULL,
 created_at TEXT NOT NULL, required_judges_json TEXT NOT NULL, policy_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS judge_votes(
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES forecast_runs(id),
 evidence_id TEXT NOT NULL REFERENCES evidence(id), judge_id TEXT NOT NULL,
 verdict TEXT NOT NULL CHECK(verdict IN('allow','drop','error')),
 reason TEXT NOT NULL, model TEXT NOT NULL, prompt_text TEXT NOT NULL, prompt_sha256 TEXT NOT NULL, raw_response TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(run_id,evidence_id,judge_id)
);
CREATE TABLE IF NOT EXISTS gate_decisions(
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES forecast_runs(id),
 evidence_id TEXT NOT NULL REFERENCES evidence(id), decision TEXT NOT NULL CHECK(decision IN('allow','drop')),
 reasons_json TEXT NOT NULL, decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS packet_exports(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES forecast_runs(id),
 created_at TEXT NOT NULL, sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES forecast_runs(id),
 packet_id TEXT NOT NULL REFERENCES packet_exports(id), model TEXT NOT NULL,
 created_at TEXT NOT NULL, probabilities_json TEXT NOT NULL, raw_response TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_horse ON entries(horse_id);
CREATE INDEX IF NOT EXISTS idx_results_horse ON results(horse_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(observed_at);
CREATE INDEX IF NOT EXISTS idx_evidence_snapshot ON evidence(snapshot_id);

-- Source-provided stable IDs; do not silently merge identities across providers.
CREATE TABLE IF NOT EXISTS entity_identifiers(
 source_id TEXT NOT NULL REFERENCES sources(id), kind TEXT NOT NULL,
 external_id TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(id),
 PRIMARY KEY(source_id,kind,external_id)
);
CREATE TABLE IF NOT EXISTS race_details(
 race_version_id TEXT PRIMARY KEY REFERENCES race_versions(id),
 category_raw TEXT, surface_raw TEXT, going_raw TEXT, start_time_raw TEXT,
 prize_raw TEXT, dividends_raw TEXT
);
CREATE TABLE IF NOT EXISTS result_details(
 result_id TEXT PRIMARY KEY REFERENCES results(id),
 weight_raw TEXT NOT NULL, assigned_weight_kg REAL, carried_weight_kg REAL,
 dividend_raw TEXT, time_or_margin_raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS race_identifiers(
 source_id TEXT NOT NULL REFERENCES sources(id), external_id TEXT NOT NULL,
 race_id TEXT NOT NULL REFERENCES races(id),
 PRIMARY KEY(source_id,external_id)
);
-- Supervisor/scorer view only. Prefer official results, then latest observation per race.
-- This is a current-label selection policy, NOT an as-of historical feature view.
CREATE VIEW IF NOT EXISTS latest_results AS
WITH ranked AS (
 SELECT v.id,v.race_id,
 ROW_NUMBER() OVER (
  PARTITION BY v.race_id
  ORDER BY CASE s.source_id WHEN 'jce' THEN 0 ELSE 1 END,
           s.observed_at DESC,v.id
 ) AS priority
 FROM race_versions v JOIN snapshots s ON s.id=v.snapshot_id
 WHERE v.phase='result' AND EXISTS(SELECT 1 FROM results z WHERE z.race_version_id=v.id)
)
SELECT ranked.race_id,z.*
FROM ranked JOIN results z ON z.race_version_id=ranked.id
WHERE ranked.priority=1;
