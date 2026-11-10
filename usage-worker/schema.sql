-- One row per install and ISO week ("2026-W46").
CREATE TABLE IF NOT EXISTS pings (
  week    TEXT NOT NULL,
  id      TEXT NOT NULL,
  version TEXT NOT NULL,
  lang    TEXT NOT NULL,
  PRIMARY KEY (week, id)
);
