-- ─── Migration 003: User Management + Notification System ───────────────────
-- Adds user profiles (role + approval status), in-app notifications,
-- and a setup checklist table.

-- ─── PROFILES ─────────────────────────────────────────────────────────────────
-- One row per auth.user. Created automatically via trigger on signup.
CREATE TABLE IF NOT EXISTS profiles (
  id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  email         TEXT NOT NULL,
  full_name     TEXT,
  -- role: admin | user
  role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
  -- status: pending (awaiting admin approval) | approved | denied | suspended
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'denied', 'suspended')),
  avatar_url    TEXT,
  approved_at   TIMESTAMPTZ,
  approved_by   UUID REFERENCES auth.users(id),
  denied_at     TIMESTAMPTZ,
  denied_by     UUID REFERENCES auth.users(id),
  denied_reason TEXT,
  last_seen_at  TIMESTAMPTZ
);

CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_role   ON profiles(role);

-- ── Auto-create profile on signup ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  admin_email TEXT := current_setting('app.admin_email', true);
  first_user  BOOLEAN;
BEGIN
  -- Check if this is the very first user (admin bootstrap)
  SELECT NOT EXISTS(SELECT 1 FROM profiles LIMIT 1) INTO first_user;

  INSERT INTO profiles (id, email, full_name, role, status, approved_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    -- First user or admin_email match gets admin + auto-approved
    CASE WHEN first_user OR NEW.email = admin_email THEN 'admin' ELSE 'user' END,
    CASE WHEN first_user OR NEW.email = admin_email THEN 'approved' ELSE 'pending' END,
    CASE WHEN first_user OR NEW.email = admin_email THEN NOW() ELSE NULL END
  );

  -- Notify admins of new pending user (skip for first admin)
  IF NOT first_user AND NEW.email != admin_email THEN
    INSERT INTO app_notifications (
      recipient_role, type, title, body,
      action_url, metadata
    ) VALUES (
      'admin', 'new_user_pending',
      'New User Awaiting Approval',
      COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email) || ' has requested access to WholesaleOS.',
      '/admin/users',
      jsonb_build_object('user_id', NEW.id, 'email', NEW.email)
    );
  END IF;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ─── APP NOTIFICATIONS ────────────────────────────────────────────────────────
-- Stores in-app notifications. Supports:
--   recipient_id  → specific user
--   recipient_role → broadcast to all users of that role (admin | user | all)
CREATE TABLE IF NOT EXISTS app_notifications (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  -- Target: either a specific user or broadcast to a role
  recipient_id   UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  recipient_role TEXT,  -- admin | user | all (used when recipient_id is null)
  -- Notification content
  type           TEXT NOT NULL,  -- new_user_pending | hot_lead | appointment_set |
                                 --   skip_trace_complete | pipeline_step | system
  title          TEXT NOT NULL,
  body           TEXT NOT NULL,
  -- Optional deep-link
  action_url     TEXT,
  action_label   TEXT,
  -- Lead / deal context
  lead_id        UUID REFERENCES leads(id) ON DELETE SET NULL,
  deal_id        UUID REFERENCES deals(id) ON DELETE SET NULL,
  -- State
  read           BOOLEAN DEFAULT FALSE,
  read_at        TIMESTAMPTZ,
  -- Extra data
  metadata       JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient   ON app_notifications(recipient_id) WHERE recipient_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_role        ON app_notifications(recipient_role) WHERE recipient_role IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_unread      ON app_notifications(read) WHERE read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_type        ON app_notifications(type);

-- ─── SETUP CHECKLIST ──────────────────────────────────────────────────────────
-- Tracks which setup steps each admin has completed.
CREATE TABLE IF NOT EXISTS setup_checklist (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  step         TEXT NOT NULL,   -- anthropic | supabase | agency | batchdata |
                                --  batchdialer | launch_control | email | test_complete
  completed    BOOLEAN DEFAULT FALSE,
  completed_at TIMESTAMPTZ,
  skipped      BOOLEAN DEFAULT FALSE,
  notes        TEXT,
  UNIQUE (user_id, step)
);

CREATE INDEX IF NOT EXISTS idx_setup_checklist_user ON setup_checklist(user_id);

-- ─── RLS ──────────────────────────────────────────────────────────────────────

ALTER TABLE profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_checklist  ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read their own; admins can read all; admins can update all
CREATE POLICY "profiles_read_own"    ON profiles FOR SELECT USING (id = auth.uid());
CREATE POLICY "profiles_admin_read"  ON profiles FOR SELECT USING (
  EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);
CREATE POLICY "profiles_admin_write" ON profiles FOR UPDATE USING (
  EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);

-- Notifications: users see their own + broadcasts to their role
CREATE POLICY "notifications_read" ON app_notifications FOR SELECT USING (
  recipient_id = auth.uid()
  OR recipient_role = 'all'
  OR (
    recipient_role = 'admin'
    AND EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
  )
  OR (
    recipient_role = 'user'
    AND EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.status = 'approved')
  )
);
CREATE POLICY "notifications_update_own" ON app_notifications FOR UPDATE USING (
  recipient_id = auth.uid()
  OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);

-- Setup checklist: only own rows
CREATE POLICY "setup_own" ON setup_checklist FOR ALL USING (user_id = auth.uid());

-- ─── PROTECT ALL DATA TABLES FROM PENDING/DENIED USERS ────────────────────────
-- Add an approved-user check to all existing table policies.
-- These supplement the existing "authenticated_full_access" policies.

CREATE OR REPLACE FUNCTION is_approved()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
  SELECT EXISTS (
    SELECT 1 FROM profiles
    WHERE id = auth.uid() AND status = 'approved'
  );
$$;

-- Helper view so frontend can check own profile without a full table scan
CREATE OR REPLACE VIEW my_profile AS
  SELECT id, email, full_name, role, status, avatar_url, created_at, approved_at
  FROM profiles
  WHERE id = auth.uid();

GRANT SELECT ON my_profile TO authenticated;

-- ─── FUNCTION: Admin approve / deny ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION admin_set_user_status(
  target_user_id UUID,
  new_status TEXT,
  reason TEXT DEFAULT NULL
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  -- Only admins may call this
  IF NOT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') THEN
    RAISE EXCEPTION 'Unauthorized: admin role required';
  END IF;

  UPDATE profiles SET
    status      = new_status,
    approved_at = CASE WHEN new_status = 'approved' THEN NOW() ELSE approved_at END,
    approved_by = CASE WHEN new_status = 'approved' THEN auth.uid() ELSE approved_by END,
    denied_at   = CASE WHEN new_status = 'denied'   THEN NOW() ELSE denied_at   END,
    denied_by   = CASE WHEN new_status = 'denied'   THEN auth.uid() ELSE denied_by  END,
    denied_reason = COALESCE(reason, denied_reason)
  WHERE id = target_user_id;

  -- Notify the user of the decision
  INSERT INTO app_notifications (recipient_id, type, title, body, action_url)
  VALUES (
    target_user_id,
    CASE new_status WHEN 'approved' THEN 'access_approved' ELSE 'access_denied' END,
    CASE new_status WHEN 'approved' THEN 'Access Approved' ELSE 'Access Denied' END,
    CASE new_status
      WHEN 'approved' THEN 'Your account has been approved. You can now access WholesaleOS.'
      ELSE COALESCE('Your access request was denied. ' || reason, 'Your access request was not approved.')
    END,
    '/login'
  );
END;
$$;

-- ─── FUNCTION: Admin set role ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION admin_set_user_role(
  target_user_id UUID,
  new_role TEXT
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') THEN
    RAISE EXCEPTION 'Unauthorized: admin role required';
  END IF;
  UPDATE profiles SET role = new_role WHERE id = target_user_id;
END;
$$;
