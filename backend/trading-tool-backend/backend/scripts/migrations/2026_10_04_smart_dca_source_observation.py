"""Record provider observation time separately from ingestion time.

Existing timestamps may have been stamped when data was received. Leave all
existing source_observed_at values NULL so legacy rows cannot size Smart DCA.
"""

SQL = """
ALTER TABLE market_data ADD COLUMN IF NOT EXISTS source_observed_at TIMESTAMP NULL;
ALTER TABLE macro_data ADD COLUMN IF NOT EXISTS source_observed_at TIMESTAMP NULL;
ALTER TABLE market_data_indicators ADD COLUMN IF NOT EXISTS source_observed_at TIMESTAMP NULL;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS source_observed_at TIMESTAMP NULL;
"""
