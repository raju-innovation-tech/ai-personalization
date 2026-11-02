# One-time Flutter setup (run from the repo root).
# The zip ships only lib/ + pubspec.yaml; platform folders (android/, windows/, web/) must be generated.
$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\flutter_admin"

flutter create . --project-name ai_personalization_admin --org com.example --platforms=android,windows,web
# `flutter create` adds a template test that references a MyApp widget this project does not have.
if (Test-Path 'test\widget_test.dart') { Remove-Item 'test\widget_test.dart' -Force }

flutter pub get

# Android: the generated *main* manifest has no INTERNET permission (only debug/profile do) and
# Android 9+ blocks plain-http traffic. Dev-only patch; use HTTPS and remove the flag for production.
$manifest = Join-Path (Get-Location) 'android\app\src\main\AndroidManifest.xml'
if (Test-Path $manifest) {
    $xml = [System.IO.File]::ReadAllText($manifest)
    if ($xml -notmatch 'android.permission.INTERNET') {
        $xml = $xml -replace '(<manifest[^>]*>)', "`$1`r`n    <uses-permission android:name=`"android.permission.INTERNET`"/>"
    }
    if ($xml -notmatch 'usesCleartextTraffic') {
        $xml = $xml -replace '<application', '<application android:usesCleartextTraffic="true"'
    }
    [System.IO.File]::WriteAllText($manifest, $xml, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "Patched AndroidManifest.xml (INTERNET + cleartext for dev)."
}

flutter analyze
flutter test
Write-Host ""
Write-Host "Done. Run:  flutter run -d chrome   |   flutter run -d windows"
