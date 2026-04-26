-- ═══════════════════════════════════════════════════════
-- ALEV v2.0 — PostgreSQL Şeması
-- Hiyerarşi: Etkinlik → Senaryo → Görev → Takım → Üye → RPG
-- ═══════════════════════════════════════════════════════

-- Uzantılar
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── ETKİNLİKLER ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,           -- URL-friendly: "hackathon-2025"
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'draft',           -- draft | active | paused | ended
    start_at    TIMESTAMPTZ,
    end_at      TIMESTAMPTZ,
    max_teams   INT DEFAULT 20,
    max_members_per_team INT DEFAULT 6,
    join_mode   TEXT DEFAULT 'code',            -- code | open | approval
    settings    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── ETKİNLİK NİTELİK ŞEMASI ──────────────────────────────
-- Her etkinlik kendi RPG niteliklerini tanımlar
CREATE TABLE IF NOT EXISTS event_attributes (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,                  -- "guc", "zeka", "cevre_puani"
    name_tr     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    description_tr TEXT,
    description_en TEXT,
    emoji       TEXT DEFAULT '⭐',
    min_val     INT DEFAULT 0,
    max_val     INT DEFAULT 20,
    default_val INT DEFAULT 5,
    color       TEXT DEFAULT 'amber',
    sort_order  INT DEFAULT 0,
    UNIQUE(event_id, key)
);

-- ── ETKİNLİK ROLLERİ ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_roles (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    name_tr     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    description_tr TEXT,
    description_en TEXT,
    emoji       TEXT DEFAULT '⚔️',
    color       TEXT DEFAULT 'amber',
    bonus_task_types TEXT[] DEFAULT '{}',
    bonus_multiplier FLOAT DEFAULT 1.0,
    base_attributes JSONB DEFAULT '{}',        -- {"guc": 7, "zeka": 5}
    max_members INT DEFAULT 6,
    unlock_level INT DEFAULT 1,
    UNIQUE(event_id, key)
);

-- ── SENARYOLAR ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenarios (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'inactive',        -- inactive | active | completed
    current_stage_id INT,                       -- FK sonra eklenecek
    auto_advance BOOL DEFAULT FALSE,
    settings    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── SENARYO AŞAMALARI ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS scenario_stages (
    id          SERIAL PRIMARY KEY,
    scenario_id INT REFERENCES scenarios(id) ON DELETE CASCADE,
    stage_order INT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    duration_minutes INT DEFAULT 60,
    xp_multiplier FLOAT DEFAULT 1.0,
    task_filter JSONB DEFAULT '{}',            -- hangi görev setleri açık
    unlock_message_tr TEXT,
    unlock_message_en TEXT,
    is_final    BOOL DEFAULT FALSE
);

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_current_stage'
  ) THEN
    ALTER TABLE scenarios ADD CONSTRAINT fk_current_stage
      FOREIGN KEY (current_stage_id) REFERENCES scenario_stages(id)
      ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;

-- ── GÖREVLER ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    title_tr    TEXT NOT NULL,
    title_en    TEXT NOT NULL,
    description_tr TEXT,
    description_en TEXT,
    task_type   TEXT DEFAULT 'general',
    difficulty  TEXT DEFAULT 'orta',            -- kolay | orta | zor | efsane
    sp_reward   INT DEFAULT 300,
    attribute_rewards JSONB DEFAULT '{}',       -- {"guc": 2, "zeka": 1}
    proof_type  TEXT DEFAULT 'link',            -- link | file | code | photo
    stage_id    INT REFERENCES scenario_stages(id) ON DELETE SET NULL,
    active      BOOL DEFAULT TRUE,
    max_completions INT DEFAULT 1,              -- takım başına max tamamlama
    badge_id    TEXT,
    sort_order  INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── KARAR AĞACI ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS branch_nodes (
    id          SERIAL PRIMARY KEY,
    scenario_id INT REFERENCES scenarios(id) ON DELETE CASCADE,
    node_key    TEXT NOT NULL,
    node_type   TEXT DEFAULT 'choice',          -- choice | task_gate | end
    title_tr    TEXT,
    title_en    TEXT,
    description_tr TEXT,
    description_en TEXT,
    parent_id   INT REFERENCES branch_nodes(id) ON DELETE SET NULL,
    choices     JSONB DEFAULT '[]',             -- [{label_tr, label_en, next_key, xp_bonus}]
    required_xp INT DEFAULT 0,
    task_id     INT REFERENCES tasks(id) ON DELETE SET NULL,
    UNIQUE(scenario_id, node_key)
);

-- ── QUIZLer ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quizzes (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    title_tr    TEXT NOT NULL,
    title_en    TEXT NOT NULL,
    stage_id    INT REFERENCES scenario_stages(id) ON DELETE SET NULL,
    cooldown_minutes INT DEFAULT 60,
    sp_reward   INT DEFAULT 100,
    active      BOOL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id          SERIAL PRIMARY KEY,
    quiz_id     INT REFERENCES quizzes(id) ON DELETE CASCADE,
    question_tr TEXT NOT NULL,
    question_en TEXT NOT NULL,
    options_tr  TEXT[] NOT NULL,
    options_en  TEXT[] NOT NULL,
    correct_idx INT NOT NULL,
    explanation_tr TEXT,
    explanation_en TEXT,
    sp_reward   INT DEFAULT 50,
    sort_order  INT DEFAULT 0
);

-- ── TAKIMLAR ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    role_id     INT REFERENCES event_roles(id) ON DELETE SET NULL,
    telegram_group_id BIGINT,                   -- Telegram grup chat_id
    telegram_group_name TEXT,
    invite_code TEXT UNIQUE,                    -- 6 haneli davet kodu
    xp          INT DEFAULT 0,
    level       INT DEFAULT 1,
    attributes  JSONB DEFAULT '{}',             -- mevcut nitelik değerleri
    badges      TEXT[] DEFAULT '{}',
    status      TEXT DEFAULT 'active',          -- active | frozen | disqualified
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, name)
);

-- ── TAKIM ÜYELERİ ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_members (
    id          SERIAL PRIMARY KEY,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    username    TEXT,
    display_name TEXT,
    role        TEXT DEFAULT 'member',          -- leader | member
    attributes  JSONB DEFAULT '{}',             -- üye bazlı nitelikler
    xp          INT DEFAULT 0,
    joined_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, telegram_id)
);

-- ── GÖREV TAMAMLAMALARI ───────────────────────────────────
CREATE TABLE IF NOT EXISTS task_completions (
    id          SERIAL PRIMARY KEY,
    task_id     INT REFERENCES tasks(id) ON DELETE CASCADE,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    submitted_by BIGINT,                        -- telegram_id
    proof_url   TEXT,
    status      TEXT DEFAULT 'pending',         -- pending | approved | rejected
    sp_awarded  INT DEFAULT 0,
    reviewed_by TEXT,
    review_note TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);

-- ── JÜRİ PUANLARI ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jury_scores (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    criterion   TEXT NOT NULL,
    score       FLOAT NOT NULL,
    jury_user   BIGINT,
    note        TEXT,
    scored_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, team_id, criterion, jury_user)
);

-- ── JÜRİ KRİTERLERİ ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS jury_criteria (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    name_tr     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    emoji       TEXT DEFAULT '⭐',
    weight      FLOAT DEFAULT 1.0,
    min_score   INT DEFAULT 0,
    max_score   INT DEFAULT 100,
    UNIQUE(event_id, key)
);

-- ── JÜRİ ÜYELERİ ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jury_members (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    name        TEXT,
    UNIQUE(event_id, telegram_id)
);

-- ── DUYURULAR ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS announcements (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    title_tr    TEXT,
    title_en    TEXT,
    message_tr  TEXT NOT NULL,
    message_en  TEXT NOT NULL,
    ann_type    TEXT DEFAULT 'info',
    sent_to_telegram BOOL DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── BOT TOKENLARI ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_tokens (
    id          SERIAL PRIMARY KEY,
    group_id    TEXT UNIQUE NOT NULL,
    token_env_key TEXT NOT NULL,
    encrypted_token TEXT NOT NULL,
    bot_id      BIGINT,
    bot_username TEXT,
    event_id    INT REFERENCES events(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── DUYURU / BULMACA DURUMU (kullanıcı bazlı) ─────────────
CREATE TABLE IF NOT EXISTS user_quiz_attempts (
    id          SERIAL PRIMARY KEY,
    quiz_id     INT REFERENCES quizzes(id) ON DELETE CASCADE,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    telegram_id BIGINT,
    score       INT DEFAULT 0,
    completed   BOOL DEFAULT FALSE,
    attempted_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── BRANCH NODE DURUMU ────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_branch_state (
    id          SERIAL PRIMARY KEY,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    scenario_id INT REFERENCES scenarios(id) ON DELETE CASCADE,
    current_node_key TEXT,
    history     JSONB DEFAULT '[]',
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, scenario_id)
);

-- ── İNDEKSLER ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_teams_event    ON teams(event_id);
CREATE INDEX IF NOT EXISTS idx_teams_code     ON teams(invite_code);
CREATE INDEX IF NOT EXISTS idx_members_tgid   ON team_members(telegram_id);
CREATE INDEX IF NOT EXISTS idx_completions_status ON task_completions(status);
CREATE INDEX IF NOT EXISTS idx_tasks_event    ON tasks(event_id);
CREATE INDEX IF NOT EXISTS idx_completions_team ON task_completions(team_id);

-- ── YARDIMCI FONKSİYONLAR ────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_events_upd ON events;
CREATE TRIGGER trg_events_upd
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_teams_upd ON teams;
CREATE TRIGGER trg_teams_upd
    BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── v2.1 MİGRASYONLAR ────────────────────────────────────
-- Üye bireysel rolü
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name='team_members' AND column_name='role_id'
  ) THEN
    ALTER TABLE team_members ADD COLUMN role_id INT REFERENCES event_roles(id) ON DELETE SET NULL;
  END IF;
  -- character_name veya role_name yoksa role_name ekle
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='character_name')
  AND NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='role_name') THEN
    ALTER TABLE team_members ADD COLUMN role_name TEXT;
  END IF;
END $$;

-- Jüri: Telegram bildirimi için webhook flag
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name='jury_scores' AND column_name='notified_telegram'
  ) THEN
    ALTER TABLE jury_scores ADD COLUMN notified_telegram BOOL DEFAULT FALSE;
  END IF;
END $$;

-- Jüri: Oturum token (web paneli için)
CREATE TABLE IF NOT EXISTS jury_sessions (
    id          SERIAL PRIMARY KEY,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    token       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, telegram_id)
);

-- ── SENARYO BONUS SİSTEMİ (v2.2) ─────────────────────────
DO $$ BEGIN
  -- scenarios tablosuna bonus alanları ekle
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='scenarios' AND column_name='min_tasks_required') THEN
    ALTER TABLE scenarios ADD COLUMN min_tasks_required INT DEFAULT 1;
    ALTER TABLE scenarios ADD COLUMN bonus_sp INT DEFAULT 500;
    ALTER TABLE scenarios ADD COLUMN first_bonus_sp INT DEFAULT 1000;
    ALTER TABLE scenarios ADD COLUMN bonus_badge TEXT DEFAULT '';
    ALTER TABLE scenarios ADD COLUMN bonus_attrs JSONB DEFAULT '{}';
  END IF;
END $$;

-- Senaryo tamamlama kayıtları
CREATE TABLE IF NOT EXISTS scenario_completions (
    id          SERIAL PRIMARY KEY,
    scenario_id INT REFERENCES scenarios(id) ON DELETE CASCADE,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    rank        INT,            -- kaçıncı tamamlayan (1=ilk)
    bonus_sp    INT DEFAULT 0,
    badge       TEXT DEFAULT '',
    completed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scenario_id, team_id)
);

-- ── ALEV v2.3 MİGRASYONLARI ──────────────────────────────
DO $$ BEGIN
  -- tasks.scenario_id
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='tasks' AND column_name='scenario_id') THEN
    ALTER TABLE tasks ADD COLUMN scenario_id INT REFERENCES scenarios(id) ON DELETE SET NULL;
  END IF;
  -- team_members.role_id
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='role_id') THEN
    ALTER TABLE team_members ADD COLUMN role_id INT REFERENCES event_roles(id) ON DELETE SET NULL;
  END IF;
  -- team_members.role_name (character_name yerine)
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='role_name')
  AND NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='character_name') THEN
    ALTER TABLE team_members ADD COLUMN role_name TEXT;
  END IF;
  -- team_members.bp (başarı puanı - üye bazlı)
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='bp') THEN
    ALTER TABLE team_members ADD COLUMN bp INT DEFAULT 0;
  END IF;
  -- teams.updated_at
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='teams' AND column_name='updated_at') THEN
    ALTER TABLE teams ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
  END IF;
  -- events.language
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='events' AND column_name='language') THEN
    ALTER TABLE events ADD COLUMN language TEXT DEFAULT 'tr';
  END IF;
  -- scenarios bonus alanları
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='scenarios' AND column_name='min_tasks_required') THEN
    ALTER TABLE scenarios ADD COLUMN min_tasks_required INT DEFAULT 2;
    ALTER TABLE scenarios ADD COLUMN bonus_sp INT DEFAULT 150;
    ALTER TABLE scenarios ADD COLUMN first_bonus_sp INT DEFAULT 200;
    ALTER TABLE scenarios ADD COLUMN bonus_badge TEXT DEFAULT '';
    ALTER TABLE scenarios ADD COLUMN bonus_badge_color INT DEFAULT 0;
    ALTER TABLE scenarios ADD COLUMN bonus_badge_url TEXT DEFAULT '';
    ALTER TABLE scenarios ADD COLUMN bonus_attrs JSONB DEFAULT '{}';
  END IF;
END $$;

-- scenario_completions
CREATE TABLE IF NOT EXISTS scenario_completions (
    id          SERIAL PRIMARY KEY,
    scenario_id INT REFERENCES scenarios(id) ON DELETE CASCADE,
    team_id     INT REFERENCES teams(id) ON DELETE CASCADE,
    event_id    INT REFERENCES events(id) ON DELETE CASCADE,
    rank        INT,
    bonus_sp    INT DEFAULT 0,
    badge       TEXT DEFAULT '',
    completed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scenario_id, team_id)
);

-- updated_at trigger for teams
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_teams_upd ON teams;
CREATE TRIGGER trg_teams_upd BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── ALEV v2.4 — RPG Katkı ve Üye BP Sistemi ─────────────
-- Görev bazlı RPG nitelik switch (hangi nitelik bu görevden puan alır)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='tasks' AND column_name='rpg_attr_switches') THEN
    ALTER TABLE tasks ADD COLUMN rpg_attr_switches JSONB DEFAULT '{}';
    -- Örnek: {"guc": true, "zeka": false, "cevre": true}
    -- true olanlar görev onayında, kullanıcı rolünün katkı puanını alır
  END IF;
END $$;

-- Üye rol bazlı BP geçmişi
CREATE TABLE IF NOT EXISTS member_bp_log (
    id           SERIAL PRIMARY KEY,
    member_id    INT REFERENCES team_members(id) ON DELETE CASCADE,
    team_id      INT REFERENCES teams(id) ON DELETE CASCADE,
    task_id      INT REFERENCES tasks(id) ON DELETE SET NULL,
    completion_id INT REFERENCES task_completions(id) ON DELETE SET NULL,
    role_key     TEXT NOT NULL,
    attr_key     TEXT NOT NULL,   -- hangi RPG niteliğine katkıda bulundu
    bp_earned    INT DEFAULT 0,   -- bu katkıdan kazanılan BP
    note         TEXT,
    earned_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bp_log_member ON member_bp_log(member_id);
CREATE INDEX IF NOT EXISTS idx_bp_log_team   ON member_bp_log(team_id);

-- Takım toplam BP (xp sütununu kullanmaya devam, ama bp alias ekle)
-- team_members.bp zaten var (v2.3'te eklendi)

-- ── ALEV v2.5 MİGRASYONLARI ──────────────────────────────
-- Kullanılmayan kolonları kaldır, character_name → role_name

-- event_roles: kullanılmayan kolonları kaldır
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='event_roles' AND column_name='bonus_task_types') THEN
    ALTER TABLE event_roles DROP COLUMN bonus_task_types;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='event_roles' AND column_name='bonus_multiplier') THEN
    ALTER TABLE event_roles DROP COLUMN bonus_multiplier;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='event_roles' AND column_name='max_members') THEN
    ALTER TABLE event_roles DROP COLUMN max_members;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='event_roles' AND column_name='unlock_level') THEN
    ALTER TABLE event_roles DROP COLUMN unlock_level;
  END IF;
END $$;

-- team_members: character_name → role_name (idempotent)
DO $$ BEGIN
  -- character_name varsa role_name'e rename et
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='character_name') THEN
    ALTER TABLE team_members RENAME COLUMN character_name TO role_name;
  END IF;
  -- Her ikisi de yoksa ekle
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='role_name')
    AND NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='team_members' AND column_name='character_name') THEN
    ALTER TABLE team_members ADD COLUMN role_name TEXT;
  END IF;
  -- role_name zaten varsa hiçbir şey yapma (RENAME zaten olmuş)
END $$;

-- ── ALEV v2.6 — xp_reward → sp_reward, xp_awarded → sp_awarded ──────────
DO $$ BEGIN
  -- tasks.xp_reward → sp_reward
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='tasks' AND column_name='xp_reward') THEN
    ALTER TABLE tasks RENAME COLUMN xp_reward TO sp_reward;
  END IF;
  -- task_completions.xp_awarded → sp_awarded
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='task_completions' AND column_name='xp_awarded') THEN
    ALTER TABLE task_completions RENAME COLUMN xp_awarded TO sp_awarded;
  END IF;
  -- quizzes.xp_reward → sp_reward
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='quizzes' AND column_name='xp_reward') THEN
    ALTER TABLE quizzes RENAME COLUMN xp_reward TO sp_reward;
  END IF;
  -- quiz_questions.xp_reward → sp_reward
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='quiz_questions' AND column_name='xp_reward') THEN
    ALTER TABLE quiz_questions RENAME COLUMN xp_reward TO sp_reward;
  END IF;
  -- scenario_completions.bonus_xp → bonus_sp
  IF EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='scenario_completions' AND column_name='bonus_xp') THEN
    ALTER TABLE scenario_completions RENAME COLUMN bonus_xp TO bonus_sp;
  END IF;
END $$;

-- ── ALEV v2.7 — Nihai Puanlama Sistemi ───────────────────────────────────
-- events: kişi başı görev limiti
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name='events' AND column_name='max_tasks_per_member') THEN
    ALTER TABLE events ADD COLUMN max_tasks_per_member INT DEFAULT 0;
    -- 0 = sınırsız
  END IF;
END $$;

-- tasks: rpg_attr_switches artık kullanılmıyor, attribute_rewards yeterli
-- (kolonu silmiyoruz - veri kaybı riski, sadece kodda kullanmıyoruz)
