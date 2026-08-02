<#
.SYNOPSIS
    Sauvegarde locale + commit + push GitHub pour Api_Emploi.
.DESCRIPTION
    Adapte du push.sh utilise sur d'autres projets, pour PowerShell/Windows.
    Aucun token n'est stocke dans ce script : l'authentification GitHub passe
    par Git Credential Manager (integre a Git for Windows), qui ouvre une
    fenetre de connexion navigateur au premier push.
.PARAMETER Message
    Message de commit (optionnel). Par defaut : "chore: sync api_emploi -- <date>".
#>
param(
    [string]$Message
)

$ProjectDir = "D:\Work\Python\Api_Emploi"
Set-Location $ProjectDir

function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host $msg -ForegroundColor Red }

Write-Info "[*] Push Api_Emploi -- $ProjectDir`n"

if (-not (Test-Path ".git")) {
    Write-Err "[!] Pas de depot git ici"
    exit 1
}

$branch = git branch --show-current
if (-not $branch) {
    Write-Err "[!] Branche Git introuvable"
    exit 1
}

# git remote (sans argument) ne renvoie jamais d'erreur, meme sans remote configure :
# on evite ainsi le piege de "git remote get-url origin" qui echoue si absent.
$remoteNames = git remote
if ($remoteNames -notcontains "origin") {
    Write-Err "[!] Aucun remote 'origin' configure."
    Write-Err "    Lancez d'abord : git remote add origin <url-du-depot-github>"
    exit 1
}
$remote = git remote get-url origin

Write-Info "[*] Branche : $branch"
Write-Info "[*] Remote  : $remote`n"
Write-Info "[*] Statut :"
git status --short
Write-Host ""

$hasChanges = git status --porcelain

if ($hasChanges) {
    # --- Backup local avant commit ---
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $backupDir = Join-Path $ProjectDir "backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    Write-Info "[*] Backup local avant push..."
    $exclude = @(".venv", "backups", "__pycache__", ".git")
    $backupZip = Join-Path $backupDir "api_emploi-prepush-$timestamp.zip"
    $itemsToZip = Get-ChildItem -Path $ProjectDir -Force | Where-Object { $exclude -notcontains $_.Name }
    Compress-Archive -Path $itemsToZip.FullName -DestinationPath $backupZip -Force
    Write-Ok "[+] Backup cree : $backupZip"

    $dbPath = Join-Path $ProjectDir "data\jobalerts.db"
    if (Test-Path $dbPath) {
        $dbBackup = Join-Path $backupDir "api_emploi-db-$timestamp.sqlite3"
        Copy-Item $dbPath $dbBackup
        Write-Ok "[+] Backup DB cree : $dbBackup"
    }
    Write-Host ""

    # --- Add + commit ---
    Write-Info "[*] Ajout des fichiers..."
    git add -A

    $commitMsg = if ($Message) { $Message } else { "chore: sync api_emploi -- $(Get-Date -Format 'yyyy-MM-dd HH:mm')" }
    Write-Info "[*] Commit : $commitMsg"
    git commit -m $commitMsg
    if ($LASTEXITCODE -ne 0) {
        Write-Err "[!] Le commit a echoue"
        exit 1
    }
} else {
    # Rien a committer, mais des commits locaux peuvent deja attendre d'etre
    # pousses (ex: un push precedent qui a echoue) : on continue quand meme
    # vers l'etape push plutot que de s'arreter ici.
    Write-Warn "[~] Rien a committer -- verification des commits en attente de push..."
}

# --- Push (Git Credential Manager gere l'authentification GitHub) ---
Write-Host ""
Write-Info "[*] Push GitHub sur $branch..."
git push origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Err "[!] Le push a echoue"
    exit 1
}

Write-Host ""
Write-Ok "[+] Push reussi !"
git log --oneline -5
