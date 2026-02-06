# Google OAuth Configuration Guide

## Overview
This guide explains how to set up Google OAuth authentication for Campus OS UNIGOM.

## Features Implemented
✅ Complete Google OAuth 2.0 flow
✅ Automatic user creation with Google account
✅ Profile picture sync from Google
✅ Email verification via Google
✅ Secure state management with JWT
✅ Additional info collection after OAuth (faculty, phone, etc.)

## Prerequisites
1. Google Cloud Console account
2. Backend deployed with HTTPS (required for OAuth)

## Setup Steps

### 1. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Google+ API** and **People API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure OAuth consent screen:
   - User Type: External (for public access)
   - App name: Campus OS UNIGOM
   - User support email: Your email
   - Developer contact: Your email
   - Add scopes: `openid`, `email`, `profile`
   - Add test users (for testing phase)

6. Create OAuth Client ID:
   - Application type: **Web application**
   - Name: Campus OS UNIGOM Backend
   - Authorized JavaScript origins:
     ```
     https://campusos-wpce.onrender.com
     http://localhost:8000
     ```
   - Authorized redirect URIs:
     ```
     https://campusos-wpce.onrender.com/api/v1/oauth/google/callback
     http://localhost:8000/api/v1/oauth/google/callback
     ```

7. Copy the **Client ID** and **Client Secret**

### 2. Update Environment Variables

Add to your `.env` file:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://campusos-wpce.onrender.com/api/v1/oauth/google/callback
```

For Render.com deployment, add these as environment variables in your service settings.

### 3. Update Supabase Database

Run the migration script to add Google OAuth support:

```sql
-- Run this in Supabase SQL Editor
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
COMMENT ON COLUMN users.google_id IS 'Google OAuth user ID';
```

Or use the provided migration file:
```bash
psql $DATABASE_URL -f migrations/add_google_oauth.sql
```

### 4. Install Required Dependencies

```bash
cd backend
pip install -r requirements.txt
```

New dependencies added:
- `authlib==1.3.0` - OAuth library
- `bcrypt==4.0.1` - Fixed bcrypt version for compatibility
- `itsdangerous==2.1.2` - For secure state management

## API Endpoints

### 1. Start Google OAuth Flow
```
GET /api/v1/oauth/google/login
```

Redirects user to Google login page.

**Query Parameters:**
- `redirect_uri` (optional): Where to redirect after successful login

**Example:**
```
https://campusos-wpce.onrender.com/api/v1/oauth/google/login
```

### 2. OAuth Callback (handled automatically)
```
GET /api/v1/oauth/google/callback
```

Google redirects here after authentication.

**Returns:**
- If user exists: Full `TokenResponse` with access_token, refresh_token, and user data
- If new user: Temporary token + user info to complete registration

### 3. Complete Registration
```
POST /api/v1/oauth/google/complete
```

For new users to provide additional info.

**Request Body:**
```json
{
  "google_token": "temporary-jwt-token",
  "phone": "+243999999999",
  "faculty": "Informatique",
  "academic_level": "L3",
  "student_id": "UG2024001"
}
```

**Response:**
```json
{
  "access_token": "jwt-token",
  "refresh_token": "jwt-refresh-token",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@gmail.com",
    "full_name": "John Doe",
    "avatar_url": "https://lh3.googleusercontent.com/...",
    "batera_coins": 10.0,
    ...
  }
}
```

## Mobile Integration (Flutter)

### Install Dependencies
```yaml
dependencies:
  url_launcher: ^6.2.0
  webview_flutter: ^4.4.0
```

### Implementation Example

```dart
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

class GoogleSignInButton extends StatelessWidget {
  Future<void> _signInWithGoogle() async {
    final url = Uri.parse('https://campusos-wpce.onrender.com/api/v1/oauth/google/login');
    
    if (await canLaunchUrl(url)) {
      await launchUrl(
        url,
        mode: LaunchMode.externalApplication,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: _signInWithGoogle,
      icon: Image.asset('assets/google_logo.png', height: 24),
      label: Text('Continuer avec Google'),
    );
  }
}
```

### Handle Deep Links

Update `android/app/src/main/AndroidManifest.xml`:
```xml
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data
        android:scheme="campusos"
        android:host="oauth" />
</intent-filter>
```

Update `ios/Runner/Info.plist`:
```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>campusos</string>
        </array>
    </dict>
</array>
```

## Security Features

1. **State Parameter**: Uses JWT-signed state to prevent CSRF attacks
2. **Nonce**: Random nonce included in state for additional security
3. **Short-lived Tokens**: Temporary tokens expire in 30 minutes
4. **Device Binding**: Tracks device for security monitoring
5. **Email Verification**: Google-verified emails only

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Ensure the redirect URI in your code matches exactly what's in Google Console
- Include protocol (https://) and full path

### Error: "Google OAuth n'est pas configuré"
- Check that `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in environment
- Restart the server after adding environment variables

### Error: "Access blocked: Campus OS UNIGOM has not completed the Google verification process"
- During development, add test users in Google Console → OAuth consent screen
- For production, submit app for verification

### bcrypt Errors Fixed
- Upgraded to `bcrypt==4.0.1` for compatibility
- Added password length validation (72 bytes max)
- Better error messages for password issues

## Benefits of Google Sign-In

✅ **No Password Management**: Users don't need to remember another password
✅ **Faster Registration**: Pre-filled name and email
✅ **Profile Pictures**: Automatic avatar from Google
✅ **Email Verification**: Google-verified emails
✅ **Better Security**: Google's 2FA and security features
✅ **Bonus Coins**: 10 Batera Coins for Google sign-up (vs 5 for regular)

## Testing

1. Start backend: `uvicorn main:app --reload`
2. Visit: `http://localhost:8000/api/v1/oauth/google/login`
3. Authenticate with Google test account
4. Complete registration with faculty and phone
5. Verify tokens and user data in response

## Production Deployment

Before going to production:
1. ✅ Submit OAuth app for Google verification
2. ✅ Use production redirect URIs only
3. ✅ Enable HTTPS (required for OAuth)
4. ✅ Set proper CORS origins
5. ✅ Monitor OAuth logs for suspicious activity

---

**Developed by Nathanael Batera Akilimali**
Campus OS UNIGOM v15.0.0
