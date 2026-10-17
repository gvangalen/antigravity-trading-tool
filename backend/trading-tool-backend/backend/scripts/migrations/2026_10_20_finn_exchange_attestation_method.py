"""Record the verifiable channel of user attestation, not an unverified UI control."""

SQL = """
ALTER TABLE finn_exchange_review_attestations
  DROP CONSTRAINT IF EXISTS finn_exchange_review_attestations_confirmation_method_check;
UPDATE finn_exchange_review_attestations
  SET confirmation_method='authenticated_api_attestation'
  WHERE confirmation_method='web_checkbox';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname='ck_finn_exchange_attestation_method') THEN
    ALTER TABLE finn_exchange_review_attestations
      ADD CONSTRAINT ck_finn_exchange_attestation_method
      CHECK (confirmation_method='authenticated_api_attestation');
  END IF;
END $$;
"""
