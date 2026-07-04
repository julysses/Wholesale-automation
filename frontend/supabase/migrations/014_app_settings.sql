-- ── Migration 014: App Settings ───────────────────────────────────────────────
-- Key/value store for runtime configuration entered via the Setup Wizard.
-- Secrets stored here supplement Vercel env vars without requiring a redeploy.

CREATE TABLE IF NOT EXISTS app_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_app_settings_ts()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER app_settings_updated_at
  BEFORE UPDATE ON app_settings
  FOR EACH ROW EXECUTE FUNCTION update_app_settings_ts();

ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;

-- Only approved admins can read or write settings
CREATE POLICY "admin_read_settings"
  ON app_settings FOR SELECT TO authenticated
  USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin' AND status = 'approved')
  );

CREATE POLICY "admin_write_settings"
  ON app_settings FOR ALL TO authenticated
  USING (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin' AND status = 'approved')
  )
  WITH CHECK (
    EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin' AND status = 'approved')
  );

-- Service role can read (backend startup fetch)
CREATE POLICY "service_read_settings"
  ON app_settings FOR SELECT TO service_role USING (true);
