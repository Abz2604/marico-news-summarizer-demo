-- Migration: Add user_id column to campaigns table
-- This migration adds user_id to AI_NW_SUMM_CAMPAIGNS table to support user-scoped campaigns

ALTER TABLE AI_NW_SUMM_CAMPAIGNS 
ADD COLUMN IF NOT EXISTS user_id VARCHAR;

-- Add foreign key constraint
ALTER TABLE AI_NW_SUMM_CAMPAIGNS
ADD CONSTRAINT IF NOT EXISTS fk_campaigns_user 
FOREIGN KEY (user_id) REFERENCES AI_NW_SUMM_USERS(id);

-- Note: Existing campaigns will have NULL user_id. 
-- You may want to assign them to a default user or delete them:
-- UPDATE AI_NW_SUMM_CAMPAIGNS SET user_id = '<default_user_id>' WHERE user_id IS NULL;
-- Or: DELETE FROM AI_NW_SUMM_CAMPAIGNS WHERE user_id IS NULL;

