-- Migration: Add Google OAuth support to users table
-- Date: 2026-02-06
-- Description: Add google_id column and make password_hash nullable for OAuth users

-- Add google_id column for Google OAuth users
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;

-- Make password_hash nullable (for OAuth-only users)
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Add index for faster Google ID lookups
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);

-- Add comment
COMMENT ON COLUMN users.google_id IS 'Google OAuth user ID for users who sign in with Google';

-- Update existing users to ensure data consistency
UPDATE users SET google_id = NULL WHERE google_id = '';
