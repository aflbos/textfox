<#
.SYNOPSIS
  Instala, atualiza ou remove o textfox-waterfox como mod local do Sine.

.DESCRIPTION
  Use com o Waterfox fechado. O script valida o registro antes de trocar os
  arquivos e arquiva o registro anterior e a cópia substituída em
  <perfil>\chrome\textfox-sine-backups. Com -Uninstall, remove somente o
  pacote local e seu registro.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\install-sine.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\install-sine.ps1 -Uninstall
#>
[CmdletBinding()]
param(
  [string]$ProfilePath,
  [ValidatePattern('\A[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}\z')]
  [string]$ModId = "textfox-waterfox",
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$repo = Split-Path -Parent $PSScriptRoot

function Get-DefaultProfile {
  $root = Join-Path $env:APPDATA "Waterfox"
  $ini = Join-Path $root "installs.ini"
  if (-not (Test-Path -LiteralPath $ini -PathType Leaf)) {
    throw "Não encontrei $ini. Informe -ProfilePath."
  }
  $defaults = @(
    Get-Content -LiteralPath $ini -Encoding UTF8 |
      Where-Object { $_ -match '^Default=.+$' } |
      ForEach-Object {
        $value = ($_ -replace '^Default=', '') -replace '/', '\'
        if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $root $value }
        [IO.Path]::GetFullPath($value)
      } |
      Select-Object -Unique
  )
  if ($defaults.Count -ne 1) {
    throw "O Waterfox não tem um único perfil padrão em installs.ini. Informe -ProfilePath."
  }
  return $defaults[0]
}

function Assert-RegularPath([string]$Path, [switch]$Directory) {
  $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  if ($item -and (
      $item.PSIsContainer -ne $Directory.IsPresent -or
      ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
    )) {
    throw "O caminho não tem o tipo esperado ou é um link: $Path"
  }
}

function Convert-RegistryValue($Value) {
  if ($Value -is [System.Dynamic.ExpandoObject]) {
    $fields = [ordered]@{}
    foreach ($field in $Value) {
      $fields.Add($field.Key, (Convert-RegistryValue $field.Value))
    }
    return [pscustomobject]$fields
  }
  if ($Value -is [Collections.IList]) {
    # The outer comma keeps single-item and empty JSON arrays from unwrapping.
    return ,@(foreach ($element in $Value) { Convert-RegistryValue $element })
  }
  return ,$Value
}

function Read-Registry([string]$Json) {
  if ($Json -notmatch '^\s*\{') { throw "mods.json deve conter um objeto JSON." }
  if ($PSVersionTable.PSEdition -ne "Core") {
    return ConvertFrom-Json -InputObject $Json
  }

  # Use PowerShell's bundled JSON parser without auto-converting timestamp strings.
  $settings = [Newtonsoft.Json.JsonSerializerSettings]::new()
  $settings.DateParseHandling = [Newtonsoft.Json.DateParseHandling]::None
  $settings.Converters.Add([Newtonsoft.Json.Converters.ExpandoObjectConverter]::new())
  $parsed = [Newtonsoft.Json.JsonConvert]::DeserializeObject($Json, [System.Dynamic.ExpandoObject], $settings)
  return Convert-RegistryValue $parsed
}

if ($ModId -match '^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])$') {
  throw "ModId usa um nome reservado do Windows: $ModId"
}
if (-not $ProfilePath) { $ProfilePath = Get-DefaultProfile }
$profile = (Resolve-Path -LiteralPath $ProfilePath).ProviderPath
$chromeDir = Join-Path $profile "chrome"
$modsDir = Join-Path $chromeDir "sine-mods"
$modsJson = Join-Path $modsDir "mods.json"
$dest = Join-Path $modsDir $ModId
$lockPath = Join-Path $modsDir ".textfox-sine.lock"

Assert-RegularPath $chromeDir -Directory
Assert-RegularPath $modsDir -Directory
Assert-RegularPath $modsJson
if (-not (Test-Path -LiteralPath $modsJson -PathType Leaf)) {
  throw "Sine não encontrado: $modsJson não existe."
}

Assert-RegularPath $lockPath
try {
  $lock = [IO.File]::Open($lockPath, "OpenOrCreate", "ReadWrite", "None")
} catch {
  throw "Não consegui reservar a instalação em $modsDir. $($_.Exception.Message)"
}

try {
  $before = [IO.File]::ReadAllBytes($modsJson)
  $raw = $utf8.GetString($before).TrimStart([char]0xfeff)
  $mods = Read-Registry $raw
  $existing = $mods.PSObject.Properties[$ModId]
  if ($existing -and (
      $existing.Value.id -ne $ModId -or
      $existing.Value.homepage -ne "" -or
      $existing.Value.style.chrome -ne "chrome/userChrome.css" -or
      $existing.Value.style.content -ne "chrome/userContent.css"
    )) {
    throw "O identificador '$ModId' pertence a outro mod no registro do Sine."
  }
  Assert-RegularPath $dest -Directory
  $hasPackage = Test-Path -LiteralPath $dest -PathType Container
  if (-not $existing -and $hasPackage) {
    throw "A pasta $dest já existe e não pertence a um mod local registrado por este script."
  }
  if ($Uninstall -and -not $existing) {
    Write-Host "O mod local '$ModId' já está ausente."
    return
  }

  $disabledMods = @()
  if ($Uninstall) {
    $mods.PSObject.Properties.Remove($ModId)
  } else {
    $theme = Get-Content -LiteralPath (Join-Path $repo "theme.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($theme.name -isnot [string] -or [string]::IsNullOrWhiteSpace($theme.name) -or
        $theme.version -isnot [string] -or [string]::IsNullOrWhiteSpace($theme.version) -or
        $theme.style.chrome -cne "chrome/userChrome.css" -or $theme.style.content -cne "chrome/userContent.css") {
      throw "O theme.json precisa declarar o nome, a versão e os dois caminhos CSS do textfox."
    }
    $entry = [ordered]@{
      style        = [ordered]@{ chrome = $theme.style.chrome; content = $theme.style.content }
      id           = $ModId
      homepage     = ""
      name         = $theme.name
      version      = $theme.version
      description  = $theme.description
      updatedAt    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
      preferences  = ""
      "no-updates" = $true
      enabled      = $true
    }
    $mods | Add-Member -NotePropertyName $ModId -NotePropertyValue ([pscustomobject]$entry) -Force

    foreach ($property in $mods.PSObject.Properties) {
      $mod = $property.Value
      if ($mod.enabled -and $mod.homepage -match '^(?:(?:https?://)?(?:www\.)?github\.com/)?adriankarlen/textfox(?:\.git)?(?:[/?#]|$)') {
        $mod.enabled = $false
        $disabledMods += $property.Name
      }
    }
  }

  $backups = Join-Path $chromeDir "textfox-sine-backups"
  Assert-RegularPath $backups -Directory
  $runId = "$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')-$([guid]::NewGuid().ToString('N'))"
  $run = Join-Path $backups $runId
  $staged = Join-Path $run "staged"
  $previous = Join-Path $run "previous"
  $replacement = Join-Path $run "mods.new.json"
  $backup = Join-Path $run "mods.json"

  # Prepare the complete package and registry before moving anything active.
  [IO.Directory]::CreateDirectory($run) | Out-Null
  if (-not $Uninstall) {
    [IO.Directory]::CreateDirectory($staged) | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo "chrome") -Destination (Join-Path $staged "chrome") -Recurse
    foreach ($name in "theme.json", "user.js", "LICENSE") {
      Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $staged
    }
    foreach ($sheet in $theme.style.chrome, $theme.style.content) {
      if (-not (Test-Path -LiteralPath (Join-Path $staged $sheet) -PathType Leaf)) {
        throw "O pacote preparado está incompleto. Arquivo ausente: $sheet"
      }
    }
  }
  [IO.File]::WriteAllText($replacement, (ConvertTo-Json -InputObject $mods -Depth 100 -Compress -WarningAction Stop), $utf8)

  $oldMoved = $false
  $newMoved = $false
  try {
    if ($hasPackage) {
      [IO.Directory]::Move($dest, $previous)
      $oldMoved = $true
    }
    if (-not $Uninstall) {
      [IO.Directory]::Move($staged, $dest)
      $newMoved = $true
    }
    $current = [IO.File]::ReadAllBytes($modsJson)
    if ([Convert]::ToBase64String($current) -cne [Convert]::ToBase64String($before)) {
      throw "O mods.json mudou durante a operação. Feche o Waterfox e tente novamente."
    }
    # File.Replace swaps the registry atomically and saves the old bytes.
    [IO.File]::Replace($replacement, $modsJson, $backup)
  } catch {
    $failure = $_
    $recoveryErrors = @()
    try {
      # ReplaceFileW can throw after moving the active registry to the backup.
      if (-not [IO.File]::Exists($modsJson) -and [IO.File]::Exists($backup)) {
        [IO.File]::Move($backup, $modsJson)
      }
    } catch {
      $recoveryErrors += $_.Exception.Message
    }
    try {
      if ($newMoved) { [IO.Directory]::Move($dest, $staged) }
      if ($oldMoved) { [IO.Directory]::Move($previous, $dest) }
    } catch {
      $recoveryErrors += $_.Exception.Message
    }
    if ($recoveryErrors.Count) {
      throw "A operação falhou e a restauração automática também. Confira os arquivos em $run. Falha: $($failure.Exception.Message). Restauração: $($recoveryErrors -join '. ')"
    }
    throw $failure
  }

  foreach ($id in $disabledMods) { Write-Host "Mod original desabilitado: $id" }
  if ($Uninstall) {
    Write-Host "Mod local '$ModId' removido."
  } else {
    Write-Host "Mod local '$ModId' instalado em $dest"
  }
  Write-Host "Backup: $run"
} finally {
  $lock.Dispose()
}

if (Get-Process waterfox -ErrorAction SilentlyContinue) {
  Write-Host "O Waterfox está aberto. Reinicie-o para aplicar." -ForegroundColor Yellow
}
