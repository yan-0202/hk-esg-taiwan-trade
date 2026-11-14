param([switch]$Classroom, [ValidateSet('gemini','deepseek')][string]$Provider = 'gemini')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$bundlePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $bundlePython) { $runtime = $bundlePython }
elseif ($pythonCommand) { $runtime = $pythonCommand.Source }
else { Write-Host 'Python 3.10+ required. Offline: open index.html'; exit 1 }
$env:QA_PROVIDER = $Provider
if ($Provider -eq 'gemini') {
    $env:QA_MODEL = 'gemini-3.5-flash-lite'
    Write-Host 'Set your Gemini API key on the localhost website after it opens. The key is held in server memory only.'
} else {
    $env:QA_MODEL = 'deepseek-flash'
    Write-Host 'DeepSeek API is BILLED by usage. This option is not free.'
    if (-not $env:DEEPSEEK_API_KEY) {
        $secretValue = Read-Host 'DeepSeek API key (hidden; not saved)' -AsSecureString
        $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretValue)
        try { $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
    }
}
Write-Host 'Stop classroom access: press Ctrl+C in this window. Max 60 cloud requests per launch.'

try {
    if ($Classroom) { & $runtime -u (Join-Path $PSScriptRoot 'qa_server.py') --lan --open }
    else { & $runtime -u (Join-Path $PSScriptRoot 'qa_server.py') --open }
} finally {
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
}
