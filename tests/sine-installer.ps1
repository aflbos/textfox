$ErrorActionPreference = "Stop"

$installer = Join-Path (Split-Path -Parent $PSScriptRoot) "tools/install-sine.ps1"
$repo = Split-Path -Parent $PSScriptRoot
$modId = "textfox-waterfox"
$root = Join-Path ([IO.Path]::GetTempPath()) ("textfox-tests-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $root | Out-Null

function Assert-True($Condition, [string]$Message) {
  if (-not $Condition) { throw $Message }
}

function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
  try {
    & $Action | Out-Null
  } catch {
    if ($_.Exception.Message -notmatch $Pattern) { throw }
    return
  }
  throw "O comando deveria ter falhado."
}

function New-Profile([string]$Name, [string]$Json) {
  $profile = Join-Path $root $Name
  $mods = Join-Path $profile "chrome/sine-mods"
  New-Item -ItemType Directory -Path $mods -Force | Out-Null
  $manifest = Join-Path $mods "mods.json"
  [IO.File]::WriteAllText($manifest, $Json)
  return @{
    Path = $profile
    Mods = $mods
    Manifest = $manifest
    Mod = (Join-Path $mods $modId)
    Backups = (Join-Path $profile "chrome/textfox-sine-backups")
  }
}

function Get-Manifest($Profile) {
  return (Get-Content -LiteralPath $Profile.Manifest -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-Backups($Profile) {
  if (Test-Path -LiteralPath $Profile.Backups) {
    Get-ChildItem -LiteralPath $Profile.Backups -Directory
  }
}

function New-InstallerCopy([string]$Name) {
  $checkout = Join-Path $root $Name
  $tools = Join-Path $checkout "tools"
  [IO.Directory]::CreateDirectory($tools) | Out-Null
  foreach ($item in "theme.json", "preferences.json", "user.js", "LICENSE", "chrome") {
    Copy-Item -LiteralPath (Join-Path $repo $item) -Destination $checkout -Recurse
  }
  $script = Join-Path $tools "install-sine.ps1"
  Copy-Item -LiteralPath $installer -Destination $script
  return $script
}

$original = '{"original":{"homepage":"https://github.com/adriankarlen/textfox","enabled":true},"outro":{"enabled":true,"extra":{"value":7}}}'
$cases = [ordered]@{
  "JSON inválido antes de instalar" = {
    $profile = New-Profile "invalid" '{'
    Assert-Throws { & $installer -ProfilePath $profile.Path } '.+'
    Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "A falha de leitura deixou um mod parcialmente instalado."
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq '{') "O JSON inválido foi modificado."
  }
  "JSON válido com raiz incorreta" = {
    foreach ($value in 'null', '[]', '42') {
      $profile = New-Profile ("wrong-root-" + [guid]::NewGuid()) $value
      Assert-Throws { & $installer -ProfilePath $profile.Path } 'objeto JSON'
      Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "Uma raiz inválida deixou arquivos instalados."
    }
  }
  "Instalação e atualização com backup" = {
    $profile = New-Profile "installed" $original
    & $installer -ProfilePath $profile.Path
    $data = Get-Manifest $profile
    Assert-True ($data.$modId.enabled -and $data.$modId.'no-updates') "O mod local ficou inativo ou com atualizações habilitadas."
    Assert-True (-not $data.original.enabled) "O tema original continuou habilitado."
    Assert-True ($data.outro.enabled -and $data.outro.extra.value -eq 7) "Outro mod foi alterado."
    Assert-True ($data.$modId.preferences -ceq "preferences.json") "O painel de preferências não foi registrado."
    $prefsPath = Join-Path $profile.Mod $data.$modId.preferences
    $prefs = Get-Content -LiteralPath $prefsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $controls = @($prefs | Where-Object property)
    Assert-True ($controls.Count -eq 18) "O pacote não oferece os dezoito controles esperados."
    $entrypoint = Join-Path $profile.Mod $data.$modId.style.chrome
    Assert-True (Test-Path -LiteralPath $entrypoint -PathType Leaf) "O CSS registrado não existe."
    $firstBackup = @(Get-Backups $profile)
    Assert-True ($firstBackup.Count -eq 1) "O registro antigo não foi arquivado."
    Assert-True ([IO.File]::ReadAllText((Join-Path $firstBackup[0].FullName "mods.json")) -ceq $original) "O backup não preservou o registro original."

    $previousContent = "/* marcador da instalação anterior */"
    [IO.File]::WriteAllText($entrypoint, $previousContent)
    & $installer -ProfilePath $profile.Path
    Assert-True ([IO.File]::ReadAllText($entrypoint) -cne $previousContent) "A atualização não instalou o CSS novo."
    $bak = @(Get-Backups $profile)
    $package = @($bak | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "previous/chrome/userChrome.css") })
    Assert-True ($bak.Count -eq 2 -and $package.Count -eq 1) "A atualização não arquivou a cópia anterior."
    Assert-True ([IO.File]::ReadAllText((Join-Path $package[0].FullName "previous/chrome/userChrome.css")) -ceq $previousContent) "O backup perdeu a cópia anterior."
  }
  "Falha ao publicar com a instalação anterior presente" = {
    $profile = New-Profile "locked" $original
    & $installer -ProfilePath $profile.Path
    $entrypoint = Join-Path $profile.Mod "chrome/userChrome.css"
    [IO.File]::WriteAllText($entrypoint, "versão anterior")
    $before = [IO.File]::ReadAllText($profile.Manifest)
    $file = [IO.File]::Open($profile.Manifest, "Open", "Read", "Read")
    try {
      Assert-Throws { & $installer -ProfilePath $profile.Path } '.+'
    } finally {
      $file.Dispose()
    }
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $before) "O registro mudou após falhar a publicação."
    Assert-True ([IO.File]::ReadAllText($entrypoint) -ceq "versão anterior") "A cópia anterior não voltou ao lugar."
  }
  "Remoção isolada, idempotente e recuperável" = {
    $profile = New-Profile "remove" $original
    $otherFiles = Join-Path $profile.Mods "outro"
    New-Item -ItemType Directory -Path $otherFiles | Out-Null
    [IO.File]::WriteAllText((Join-Path $otherFiles "data.txt"), "preservar")
    & $installer -ProfilePath $profile.Path
    $before = [IO.File]::ReadAllText($profile.Manifest)
    $file = [IO.File]::Open($profile.Manifest, "Open", "Read", "Read")
    try {
      Assert-Throws { & $installer -ProfilePath $profile.Path -Uninstall } '.+'
    } finally {
      $file.Dispose()
    }
    Assert-True (Test-Path -LiteralPath $profile.Mod) "A remoção não restaurou o pacote ao falhar."
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $before) "A remoção incompleta alterou o registro."

    & $installer -ProfilePath $profile.Path -Uninstall
    Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "O mod continuou na pasta ativa."
    $data = Get-Manifest $profile
    Assert-True ($null -eq $data.$modId) "O registro local continuou ativo."
    Assert-True ($data.outro.extra.value -eq 7 -and (Test-Path -LiteralPath (Join-Path $otherFiles "data.txt"))) "A remoção afetou outro mod."
    Assert-True (-not $data.original.enabled) "A remoção alterou a preferência do tema original."
    $retired = @(Get-Backups $profile | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "previous/theme.json") })
    Assert-True ($retired.Count -eq 1) "A remoção não arquivou o pacote."
    $count = @(Get-Backups $profile).Count
    & $installer -ProfilePath $profile.Path -Uninstall
    Assert-True (@(Get-Backups $profile).Count -eq $count) "Uma segunda remoção alterou os backups."
  }
  "Identificador inválido e colisão com outro mod" = {
    $profile = New-Profile "collision" ('{"' + $modId + '":{"id":"' + $modId + '","homepage":"https://example.com/mod","enabled":true}}')
    $before = [IO.File]::ReadAllText($profile.Manifest)
    Assert-Throws { & $installer -ProfilePath $profile.Path -ModId "..\fora" } 'ModId|identificador'
    Assert-Throws { & $installer -ProfilePath $profile.Path } 'outro mod'
    Assert-Throws { & $installer -ProfilePath $profile.Path -Uninstall } 'outro mod'
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $before) "Um mod alheio foi sobrescrito."
  }
  "Mod local com os mesmos caminhos CSS continua intacto" = {
    $id = "outro-local"
    $json = '{"outro-local":{"id":"outro-local","homepage":"","style":{"chrome":"chrome/userChrome.css","content":"chrome/userContent.css"}}}'
    $profile = New-Profile "local-collision" $json
    $package = Join-Path $profile.Mods $id
    [IO.Directory]::CreateDirectory($package) | Out-Null
    $manifest = Join-Path $package "theme.json"
    $foreign = '{"id":"outro-local","name":"Outro tema"}'
    [IO.File]::WriteAllText($manifest, $foreign)
    foreach ($remove in $false, $true) {
      Assert-Throws { & $installer -ProfilePath $profile.Path -ModId $id -Uninstall:$remove } 'outro mod'
      Assert-True ([IO.File]::ReadAllText($manifest) -ceq $foreign) "O pacote alheio mudou."
      Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $json) "O registro alheio mudou."
    }
    Assert-True (-not (Test-Path -LiteralPath $profile.Backups)) "A colisão criou um backup."
  }
  "Atualização e remoção com identificador personalizado" = {
    $profile = New-Profile "custom-id" '{}'
    $id = "meu-textfox"
    & $installer -ProfilePath $profile.Path -ModId $id
    & $installer -ProfilePath $profile.Path -ModId $id
    & $installer -ProfilePath $profile.Path -ModId $id -Uninstall
    Assert-True ($null -eq (Get-Manifest $profile).$id) "O registro personalizado continuou ativo."
  }
  "Primeira instalação interrompida permite retomar ou cancelar" = {
    $copy = New-InstallerCopy "interrupted-source"
    $source = [IO.File]::ReadAllText($copy)
    $published = '$newMoved = $true'
    Assert-True ($source.Contains($published)) "O ponto de interrupção não está no instalador."
    [IO.File]::WriteAllText($copy, $source.Replace($published, "$published`n    [Environment]::Exit(86)"), [Text.UTF8Encoding]::new($true))
    $shell = (Get-Process -Id $PID).Path
    foreach ($cancel in $false, $true) {
      $profile = New-Profile "interrupted-$cancel" $original
      $id = "meu-textfox"
      $dest = Join-Path $profile.Mods $id
      & $shell -NoProfile -ExecutionPolicy Bypass -File $copy -ProfilePath $profile.Path -ModId $id
      Assert-True ($LASTEXITCODE -eq 86 -and [IO.Directory]::Exists($dest)) "O processo não parou após publicar o pacote."
      Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $original) "O registro mudou antes da interrupção."
      # Sine can change another mod between attempts; recovery must use the current registry.
      $latest = $original.Replace('"value":7', '"value":9')
      [IO.File]::WriteAllText($profile.Manifest, $latest)
      & $installer -ProfilePath $profile.Path -ModId $id -Uninstall:$cancel
      if ($cancel) {
        Assert-True (-not [IO.Directory]::Exists($dest)) "O pacote parcial continuou ativo."
        Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $latest) "Cancelar mudou o registro."
      } else {
        $data = Get-Manifest $profile
        Assert-True ($data.$id.enabled -and $data.outro.extra.value -eq 9) "A retomada perdeu dados do registro."
        Assert-True ([IO.File]::Exists((Join-Path $dest $data.$id.style.chrome))) "O pacote retomado está incompleto."
      }
    }
  }
  "Pasta sem registro e execução concorrente" = {
    $profile = New-Profile "busy" '{}'
    $lock = [IO.File]::Open((Join-Path $profile.Mods ".textfox-sine.lock"), "OpenOrCreate", "ReadWrite", "None")
    try {
      Assert-Throws { & $installer -ProfilePath $profile.Path } 'reservar a instala'
    } finally {
      $lock.Dispose()
    }
    Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "Uma segunda execução alterou os arquivos ativos."
    New-Item -ItemType Directory -Path $profile.Mod | Out-Null
    $unregistered = Join-Path $profile.Mod "keep.txt"
    [IO.File]::WriteAllText($unregistered, "preservar")
    Assert-Throws { & $installer -ProfilePath $profile.Path } 'pasta .+ existe'
    Assert-Throws { & $installer -ProfilePath $profile.Path -Uninstall } 'pasta .+ existe'
    Assert-True ((Test-Path -LiteralPath $unregistered) -and [IO.File]::ReadAllText($profile.Manifest) -ceq '{}') "A pasta sem registro foi alterada."
  }
  "Comprovante de uma instalação concluída não autoriza remover pasta sem registro" = {
    $profile = New-Profile "completed-receipt" '{}'
    & $installer -ProfilePath $profile.Path
    [IO.File]::WriteAllText($profile.Manifest, '{}')
    foreach ($cancel in $false, $true) {
      Assert-Throws { & $installer -ProfilePath $profile.Path -Uninstall:$cancel } 'publicação pendente'
    }
    Assert-True ([IO.File]::Exists((Join-Path $profile.Mod "theme.json"))) "O pacote foi movido."
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq '{}') "O registro foi alterado."
  }
  "Seleção ambígua e caminho absoluto do perfil" = {
    $profile = New-Profile "with [special]" '{}'
    $appdata = $env:APPDATA
    try {
      $env:APPDATA = Join-Path $root "appdata"
      $waterfox = Join-Path $env:APPDATA "Waterfox"
      New-Item -ItemType Directory -Path $waterfox -Force | Out-Null
      $ini = Join-Path $waterfox "installs.ini"
      [IO.File]::WriteAllLines($ini, [string[]]@("[First]", "Default=$($profile.Path)", "[Second]", "Default=Profiles/other"))
      Assert-Throws { & $installer } 'Informe -ProfilePath'
      Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "O instalador escolheu um perfil em caso de ambiguidade."
      [IO.File]::WriteAllLines($ini, [string[]]@("[First]", "Default=$($profile.Path)"))
      & $installer
      Assert-True (Test-Path -LiteralPath (Join-Path $profile.Mod "chrome/userChrome.css")) "O caminho absoluto do perfil não foi usado."
    } finally {
      $env:APPDATA = $appdata
    }
  }
  "Publicação move o registro antigo e falha" = {
    $profile = New-Profile "partial-registry" $original
    & $installer -ProfilePath $profile.Path
    $before = [IO.File]::ReadAllText($profile.Manifest)
    $entrypoint = Join-Path $profile.Mod "chrome/userChrome.css"
    [IO.File]::WriteAllText($entrypoint, "versão anterior")
    $copy = New-InstallerCopy "failure-source"
    # Model the on-disk state documented for Win32 ERROR_UNABLE_TO_MOVE_REPLACEMENT_2.
    $publish = '[IO.File]::Replace($replacement, $modsJson, $backup)'
    $source = [IO.File]::ReadAllText($copy)
    Assert-True ($source.Contains($publish)) "O ponto de simulação não está no instalador."
    [IO.File]::WriteAllText($copy, $source.Replace($publish, ('[IO.File]::Move($modsJson, $backup)' + [Environment]::NewLine + '    throw "ReplaceFileW 1177"')), [Text.UTF8Encoding]::new($true))
    Assert-Throws { & $copy -ProfilePath $profile.Path } 'ReplaceFileW 1177'
    Assert-True (Test-Path -LiteralPath $profile.Manifest -PathType Leaf) "O registro ativo não foi restaurado."
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $before) "O registro restaurado perdeu dados."
    Assert-True ([IO.File]::ReadAllText($entrypoint) -ceq "versão anterior") "O pacote ativo não foi restaurado."
  }
  "Pacote ou manifesto incompleto impede atualização" = {
    $profile = New-Profile "incomplete" $original
    & $installer -ProfilePath $profile.Path
    $before = [IO.File]::ReadAllText($profile.Manifest)
    $entrypoint = Join-Path $profile.Mod "chrome/userChrome.css"
    [IO.File]::WriteAllText($entrypoint, "versão anterior")
    $copy = New-InstallerCopy "incomplete-source"
    $checkout = Split-Path -Parent (Split-Path -Parent $copy)
    $preferences = Join-Path $checkout "preferences.json"
    Remove-Item -LiteralPath $preferences
    Assert-Throws { & $copy -ProfilePath $profile.Path } 'preferences.json'
    Copy-Item -LiteralPath (Join-Path $repo "preferences.json") -Destination $preferences
    Remove-Item -LiteralPath (Join-Path $checkout "chrome/userContent.css")
    Assert-Throws { & $copy -ProfilePath $profile.Path } 'userContent.css'
    [IO.File]::WriteAllText((Join-Path $checkout "theme.json"), '{"version":"2"}')
    Assert-Throws { & $copy -ProfilePath $profile.Path } 'theme.json'
    Assert-True ([IO.File]::ReadAllText($profile.Manifest) -ceq $before) "O manifesto ativo mudou ao receber uma atualização incompleta."
    Assert-True ([IO.File]::ReadAllText($entrypoint) -ceq "versão anterior") "A atualização incompleta trocou o pacote ativo."
  }
  "Datas de outros mods preservadas como texto" = {
    $profile = New-Profile "dates" '{"outro":{"enabled":true,"values":["2025-01-01T12:00:00.000Z","2025-01-01T12:00:00+02:00"]}}'
    & $installer -ProfilePath $profile.Path
    $written = [IO.File]::ReadAllText($profile.Manifest)
    Assert-True ($written.Contains('"2025-01-01T12:00:00.000Z","2025-01-01T12:00:00+02:00"')) "As datas de outro mod foram reformatadas."
  }
  "Preferência do Sine pode ser alterada antes da remoção" = {
    $profile = New-Profile "toggle" $original
    & $installer -ProfilePath $profile.Path
    $registered = [IO.File]::ReadAllText($profile.Manifest)
    [IO.File]::WriteAllText($profile.Manifest, $registered.Replace('"no-updates":true', '"no-updates":false'))
    & $installer -ProfilePath $profile.Path -Uninstall
    Assert-True (-not (Test-Path -LiteralPath $profile.Mod)) "A preferência de atualização impediu a remoção."
  }
  "Identifica o textfox original pelo repositório do Sine" = {
    $profile = New-Profile "upstream" '{"original":{"homepage":"adriankarlen/textfox","enabled":true},"fork":{"homepage":"adriankarlen/textfox-fork","enabled":true}}'
    & $installer -ProfilePath $profile.Path
    $data = Get-Manifest $profile
    Assert-True (-not $data.original.enabled) "O textfox original informado sem URL continuou ativo."
    Assert-True $data.fork.enabled "Outro repositório foi desativado."
  }
}

$failed = 0
try {
  foreach ($case in $cases.GetEnumerator()) {
    try {
      & $case.Value
      Write-Host "PASS $($case.Key)"
    } catch {
      $failed++
      Write-Host "FAIL $($case.Key): $($_.Exception.Message)"
    }
  }
} finally {
  $target = [IO.Path]::GetFullPath($root)
  if ([IO.Path]::GetDirectoryName($target) -eq [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) -and
      [IO.Path]::GetFileName($target) -match '^textfox-tests-[0-9a-f-]{36}$') {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}
if ($failed) { throw "$failed de $($cases.Count) cenários falharam." }
Write-Host "$($cases.Count) cenários passaram."
# The interrupted-install fixture deliberately leaves a nonzero $LASTEXITCODE.
exit 0
