[CmdletBinding()]
param([string]$Prefix)

$installArgs = @{
    Action = 'install'
}
if ($PSBoundParameters.ContainsKey('Prefix')) {
    $installArgs.Prefix = $Prefix
}
& (Join-Path $PSScriptRoot 'scripts\manage_install.ps1') @installArgs
exit $LASTEXITCODE
