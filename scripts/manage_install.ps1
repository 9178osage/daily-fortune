param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'update', 'uninstall')]
    [string]$Action,
    [string]$Prefix
)

$manager = Join-Path $PSScriptRoot 'manage_install.py'
$arguments = @('-I', '-B', $manager, $Action)
if ($PSBoundParameters.ContainsKey('Prefix')) {
    $arguments += @('--prefix', $Prefix)
}

$versionCheck = 'import sys; raise SystemExit(not sys.version_info >= (3, 9))'
foreach ($name in @('python.exe', 'py.exe')) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) {
        continue
    }
    $options = @()
    if ($name -eq 'py.exe') {
        $options += '-3'
    }
    & $command.Source @options -I -B -c $versionCheck *> $null
    if ($LASTEXITCODE -eq 0) {
        & $command.Source @options @arguments
        exit $LASTEXITCODE
    }
}

[Console]::Error.WriteLine('Daily Fortune requires Python 3.9 or newer: https://www.python.org/downloads/windows/')
exit 1
