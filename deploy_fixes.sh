#!/bin/bash
# Deployment script for bcrypt and Google OAuth fixes
# Campus OS UNIGOM - Backend

echo "🚀 Deploying bcrypt fixes and Google OAuth..."

# Step 1: Install updated dependencies
echo "📦 Installing dependencies..."
pip install --upgrade -r requirements.txt

# Step 2: Run database migration (if using direct DB access)
echo "🗄️ Running database migration..."
if [ -n "$DATABASE_URL" ]; then
    psql $DATABASE_URL -f migrations/add_google_oauth.sql
    echo "✅ Migration completed"
else
    echo "⚠️  DATABASE_URL not set. Please run migration manually in Supabase:"
    echo "   Copy contents of migrations/add_google_oauth.sql to Supabase SQL Editor"
fi

# Step 3: Verify environment variables
echo "🔍 Checking environment variables..."
if [ -z "$GOOGLE_CLIENT_ID" ]; then
    echo "⚠️  GOOGLE_CLIENT_ID not set. Add to .env file"
fi
if [ -z "$GOOGLE_CLIENT_SECRET" ]; then
    echo "⚠️  GOOGLE_CLIENT_SECRET not set. Add to .env file"
fi
if [ -z "$GOOGLE_REDIRECT_URI" ]; then
    echo "ℹ️  GOOGLE_REDIRECT_URI not set (optional, will auto-detect)"
fi

# Step 4: Run tests (if available)
echo "🧪 Running tests..."
if [ -f "pytest.ini" ] || [ -d "tests" ]; then
    pytest -v
else
    echo "ℹ️  No tests found, skipping"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Configure Google OAuth in Google Cloud Console"
echo "   2. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env"
echo "   3. Run migration in Supabase (if not done automatically)"
echo "   4. Restart your server"
echo ""
echo "📖 See OAUTH_SETUP.md for detailed instructions"
