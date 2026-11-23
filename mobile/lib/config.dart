// Build-time settings. The OAuth client ids are public (PKCE, no secret);
// a --dart-define overrides them (see mobile/README.md).
// Entra app "PFI Sync" (Default Directory of the Personal Finance publisher account):
// any Microsoft account, public client, redirect io.github.mrblizo.pfi://auth,
// delegated Files.ReadWrite.
const oneDriveClientId = String.fromEnvironment('ONEDRIVE_CLIENT_ID',
    defaultValue: 'a3f85272-b05d-4279-b167-39e953dd715b');
const dropboxAppKey = String.fromEnvironment('DROPBOX_APP_KEY');
// Google Cloud project "pfi-sync": an Android OAuth client (package
// io.github.mrblizo.pfi + SHA-1 of the release key) authorises the app through
// Google Play services; this is the project's web client id, which Android
// sign-in needs as serverClientId. Scope: drive.appdata only.
const googleServerClientId = String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID',
    defaultValue:
        '462340548032-rnm3nsvng6mk4f6ip3isdbr10bet0eop.apps.googleusercontent.com');

const oauthScheme = 'io.github.mrblizo.pfi';
const oauthRedirect = '$oauthScheme://auth';
const appVersion = '1.0.0';
