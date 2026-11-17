"""Persist the explicit Smart DCA trigger mode without changing legacy plans."""

SQL = """
ALTER TABLE setups
    ADD COLUMN IF NOT EXISTS dca_trigger_mode VARCHAR NOT NULL DEFAULT 'calendar';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'setups_dca_trigger_mode_valid') THEN
        ALTER TABLE setups ADD CONSTRAINT setups_dca_trigger_mode_valid
            CHECK (dca_trigger_mode IN ('calendar', 'benchmark')) NOT VALID;
    END IF;
END $$;
"""
