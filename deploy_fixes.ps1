# PowerShell Deployment script for bcrypt and Google OAuth fixes
# Campus OS UNIGOM - Backend

Write-Host "🚀 Deploying bcrypt fixes and Google OAuth..." -ForegroundColor Green

# Step 1: Install updated dependencies
Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan
pip install --upgrade -r requirements.txt

# Step 2: Run database migration (if using direct DB access)
Write-Host "🗄️ Running database migration..." -ForegroundColor Cyan
if ($env:DATABASE_URL) {
    psql $env:DATABASE_URL -f migrations/add_google_oauth.sql
    Write-Host "✅ Migration completed" -ForegroundColor Green
} else {
    Write-Host "⚠️  DATABASE_URL not set. Please run migration manually in Supabase:" -ForegroundColor Yellow
    Write-Host "   Copy contents of migrations/add_google_oauth.sql to Supabase SQL Editor" -ForegroundColor Yellow
}

# Step 3: Verify environment variables
Write-Host "🔍 Checking environment variables..." -ForegroundColor Cyan
if (-not $env:GOOGLE_CLIENT_ID) {
    Write-Host "⚠️  GOOGLE_CLIENT_ID not set. Add to .env file" -ForegroundColor Yellow
}
if (-not $env:GOOGLE_CLIENT_SECRET) {
    Write-Host "⚠️  GOOGLE_CLIENT_SECRET not set. Add to .env file" -ForegroundColor Yellow
}
if (-not $env:GOOGLE_REDIRECT_URI) {
    Write-Host "ℹ️  GOOGLE_REDIRECT_URI not set (optional, will auto-detect)" -ForegroundColor Gray
}

# Step 4: Run tests (if available)
Write-Host "🧪 Running tests..." -ForegroundColor Cyan
if ((Test-Path "pytest.ini") -or (Test-Path "tests")) {
    pytest -v
} else {
    Write-Host "ℹ️  No tests found, skipping" -ForegroundColor Gray
}

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Configure Google OAuth in Google Cloud Console"
Write-Host "   2. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env"
Write-Host "   3. Run migration in Supabase (if not done automatically)"
Write-Host "   4. Restart your server"
Write-Host ""
Write-Host "📖 See OAUTH_SETUP.md for detailed instructions" -ForegroundColor Cyan
