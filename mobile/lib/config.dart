// Build-time settings. The OAuth client ids are public (PKCE, no secret);
// pass them with --dart-define or fill them in once the apps are
// registered (see mobile/README.md).
const oneDriveClientId = String.fromEnvironment('ONEDRIVE_CLIENT_ID');
const dropboxAppKey = String.fromEnvironment('DROPBOX_APP_KEY');

const oauthScheme = 'io.github.mrblizo.pfi';
const oauthRedirect = '$oauthScheme://auth';
const appVersion = '0.7.0';
