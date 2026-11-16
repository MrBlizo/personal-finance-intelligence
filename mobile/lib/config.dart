// Build-time settings. The OAuth client ids are public (PKCE, no secret);
// a --dart-define overrides them (see mobile/README.md).
// Entra app "PFI Sync" (Default Directory of the PFI publisher account):
// any Microsoft account, public client, redirect io.github.mrblizo.pfi://auth,
// delegated Files.ReadWrite.
const oneDriveClientId = String.fromEnvironment('ONEDRIVE_CLIENT_ID',
    defaultValue: 'a3f85272-b05d-4279-b167-39e953dd715b');
const dropboxAppKey = String.fromEnvironment('DROPBOX_APP_KEY');
// Google Cloud OAuth client of type Android (package io.github.mrblizo.pfi,
// SHA-1 of the release key, custom URI scheme enabled), scope drive.appdata.
const googleClientId = String.fromEnvironment('GOOGLE_CLIENT_ID');
const googleRedirect = '$oauthScheme:/oauth2redirect';

const oauthScheme = 'io.github.mrblizo.pfi';
const oauthRedirect = '$oauthScheme://auth';
const appVersion = '0.7.1';
