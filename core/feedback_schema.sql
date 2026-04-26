    CREATE TABLE IF NOT EXISTS feedback (
        id          SERIAL PRIMARY KEY,
        takim_id    BIGINT REFERENCES takimlar(id),
        gorev_id    TEXT NOT NULL,
        yildiz      INTEGER CHECK (yildiz BETWEEN 1 AND 5),
        yorum       TEXT DEFAULT '',
        zaman       TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(takim_id, gorev_id)
    );
