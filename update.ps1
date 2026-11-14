[CmdletBinding()]
param([string]$Prefix)

$installArgs = @{
    Action = 'update'
}
if ($PSBoundParameters.ContainsKey('Prefix')) {
    $installArgs.Prefix = $Prefix
}
& (Join-Path $PSScriptRoot 'scripts\manage_install.ps1') @installArgs
exit $LASTEXITCODE
