[CmdletBinding()]
param([string]$Prefix)

$installArgs = @{
    Action = 'uninstall'
}
if ($PSBoundParameters.ContainsKey('Prefix')) {
    $installArgs.Prefix = $Prefix
}
& (Join-Path $PSScriptRoot 'scripts\manage_install.ps1') @installArgs
exit $LASTEXITCODE
