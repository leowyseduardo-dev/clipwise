param(
    [string]$Version = "1.3.0",
    [switch]$SkipFrontend,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = $env:Clipwise_BUILD_PYTHON
if (-not $Python) {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Temp\Clipwise-venv\Scripts\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe")
    )
    $Python = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Python -or -not (Test-Path $Python)) {
    throw "No encontre el Python de build. Define Clipwise_BUILD_PYTHON con la ruta a python.exe."
}
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "$Python no tiene PyInstaller instalado."
}
Write-Host "Python de build: $Python"

$WebView2 = Join-Path $PSScriptRoot "vendor\MicrosoftEdgeWebView2Setup.exe"
if (-not (Test-Path $WebView2)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $WebView2) | Out-Null
    Write-Host "Descargando bootstrapper de WebView2..."
    Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $WebView2 -UseBasicParsing
}
if (-not (Test-Path $WebView2) -or (Get-Item $WebView2).Length -lt 100000) {
    throw "No se pudo descargar el bootstrapper de WebView2."
}

$ModelDest = Join-Path $PSScriptRoot "build\models\tiny"
if (-not (Test-Path (Join-Path $ModelDest "model.bin"))) {
    $ModelSource = Get-ChildItem (Join-Path $env:USERPROFILE ".cache\huggingface\hub\models--Systran--faster-whisper-tiny\snapshots") -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ModelSource) {
        Write-Host "Descargando modelo faster-whisper tiny..."
        $ModelPath = & $Python -c "from huggingface_hub import snapshot_download; print(snapshot_download('Systran/faster-whisper-tiny'))" | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0 -or -not $ModelPath) {
            throw "No se pudo descargar el modelo tiny de Hugging Face."
        }
        $ModelSource = Get-Item $ModelPath
    }
    New-Item -ItemType Directory -Force -Path $ModelDest | Out-Null
    Get-ChildItem $ModelSource.FullName -File | Copy-Item -Destination $ModelDest -Force
}

if (-not $SkipFrontend) {
    Write-Host "Compilando frontend..."
    & npm.cmd --prefix web run build
    if ($LASTEXITCODE -ne 0) { throw "Fallo el build del frontend." }
}

# Fail before packaging if Vite left a half-written dist (missing JS/CSS assets).
$WebIndex = Join-Path $Root "web\dist\index.html"
if (-not (Test-Path $WebIndex)) { throw "No existe web\dist\index.html. Compila el frontend." }
$WebRefs = [regex]::Matches((Get-Content $WebIndex -Raw), "assets/[A-Za-z0-9._-]+\.(?:js|css)") |
    ForEach-Object { $_.Value } | Sort-Object -Unique
if (-not $WebRefs) { throw "web\dist\index.html no referencia assets compilados." }
foreach ($Ref in $WebRefs) {
    $AssetPath = Join-Path $Root ("web\dist\" + ($Ref -replace "/", "\"))
    if (-not (Test-Path $AssetPath)) { throw "Falta el asset $Ref en web\dist. Vuelve a compilar el frontend." }
}

Write-Host "Generando icono..."
& $Python (Join-Path $PSScriptRoot "make_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Fallo la generacion del icono." }

if (-not (Test-Path (Join-Path $Root "engine\models\titanet-small.onnx"))) {
    & $Python (Join-Path $Root "tools\instalar_voces.py")
    if ($LASTEXITCODE -ne 0) { throw "Fallo la descarga del modelo de voces." }
}

$ReleaseDir = Join-Path $PSScriptRoot "dist\Clipwise-$Version"
Write-Host "Empaquetando con PyInstaller..."
$env:PYTHONUTF8 = "1"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    (Join-Path $PSScriptRoot "Clipwise.spec") `
    --distpath $ReleaseDir `
    --workpath (Join-Path $PSScriptRoot "build\pyinstaller")
if ($LASTEXITCODE -ne 0) { throw "Fallo PyInstaller." }

$Exe = Join-Path $ReleaseDir "Clipwise\Clipwise.exe"
if (-not (Test-Path $Exe)) { throw "No se genero $Exe" }

if (-not $SkipInstaller) {
    $IsccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) {
        throw "No encontre ISCC.exe. Instala Inno Setup 6: winget install --id JRSoftware.InnoSetup -e --scope user"
    }

    Write-Host "Compilando instalador..."
    & $Iscc "/DAppVersion=$Version" "/DBundleDir=$(Join-Path $ReleaseDir 'Clipwise')" (Join-Path $PSScriptRoot "installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Fallo Inno Setup." }
}

Write-Host ""
Write-Host "Build listo:"
Write-Host "  App:       $Exe"
if (-not $SkipInstaller) {
    Write-Host "  Installer: $(Join-Path $PSScriptRoot "dist\installer\Clipwise-Setup-$Version.exe")"
}
