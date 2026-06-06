param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $FactoryArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = $env:AIASK_FACTORY_PYTHON

function Set-DefaultEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    $Current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($Current)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Set-Env {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Preferred = "F:\Python311\python.exe"
    if (Test-Path -LiteralPath $Preferred) {
        $Python = $Preferred
    } else {
        $Python = "python"
    }
}

Set-DefaultEnv -Name "PYTHONIOENCODING" -Value "utf-8"
Set-DefaultEnv -Name "PYTHONUNBUFFERED" -Value "1"

Set-DefaultEnv -Name "FACTOR_MINING_FACTORY_ENABLED" -Value "1"
Set-DefaultEnv -Name "STRATEGY_FACTORY_FACTOR_CATALOG_ENABLED" -Value "1"
Set-DefaultEnv -Name "INCUBATION_FACTORY_OWNS_PAPER_TRADING" -Value "true"
Set-DefaultEnv -Name "INCUBATION_FACTORY_PAPER_INTAKE_ENABLED" -Value "1"
Set-DefaultEnv -Name "INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT" -Value "300"
Set-DefaultEnv -Name "STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED" -Value "1"
Set-DefaultEnv -Name "STRATEGY_FACTORY_EVENT_RUNTIME_MODE" -Value "refresh"

Set-Env -Name "STRATEGY_FACTORY_EXECUTION_MODE" -Value "stock_first_observe_primary"
Set-Env -Name "STRATEGY_FACTORY_OBSERVE_FIRST_ENABLED" -Value "1"
Set-Env -Name "STRATEGY_FACTORY_WIDE_INTAKE_OBSERVE_ENABLED" -Value "1"

Set-DefaultEnv -Name "STRATEGY_TRADE_PREDICTION_PROMOTION_GATE_ENABLED" -Value "0"
Set-DefaultEnv -Name "STRATEGY_TRADE_PREDICTION_BUDGET_FEEDBACK_ENABLED" -Value "0"
Set-DefaultEnv -Name "STRATEGY_TRADE_PREDICTION_FACTOR_DECAY_ENABLED" -Value "0"

Set-DefaultEnv -Name "LIVE_TRADING_ENABLED" -Value "0"
Set-DefaultEnv -Name "LIVE_TRADING_ALLOW_WRITE" -Value "0"
Set-DefaultEnv -Name "BROKER_ALLOW_WRITE" -Value "0"
Set-DefaultEnv -Name "LIVE_TRADING_READ_ONLY" -Value "1"
Set-DefaultEnv -Name "BROKER_READ_ONLY" -Value "1"

Set-Location -LiteralPath $Root
Write-Host "Starting complete AIASK Strategy Factory runtime..."
Write-Host "  - strategy_factory: enabled"
Write-Host "  - factor_mining_factory: enabled"
Write-Host "  - incubation_factory: enabled"
Write-Host "  - market_event_ingest: enabled unless --no-event-ingest or MARKET_EVENT_INGEST_ENABLED=0"
Write-Host "  - incubation paper intake: enabled=$env:INCUBATION_FACTORY_PAPER_INTAKE_ENABLED, batch_limit=$env:INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT"
Write-Host "  - evidence-first: factor_ic_generic=$env:STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED, event_runtime=$env:STRATEGY_FACTORY_EVENT_RUNTIME_MODE"
Write-Host "  - strategy mode: execution=$env:STRATEGY_FACTORY_EXECUTION_MODE, observe_first=$env:STRATEGY_FACTORY_OBSERVE_FIRST_ENABLED, wide_intake=$env:STRATEGY_FACTORY_WIDE_INTAKE_OBSERVE_ENABLED"
Write-Host "  - trade prediction hard controls: promotion=$env:STRATEGY_TRADE_PREDICTION_PROMOTION_GATE_ENABLED, budget=$env:STRATEGY_TRADE_PREDICTION_BUDGET_FEEDBACK_ENABLED, factor_decay=$env:STRATEGY_TRADE_PREDICTION_FACTOR_DECAY_ENABLED"
Write-Host "  - live trading writes: LIVE_TRADING_ENABLED=$env:LIVE_TRADING_ENABLED, LIVE_TRADING_ALLOW_WRITE=$env:LIVE_TRADING_ALLOW_WRITE, BROKER_ALLOW_WRITE=$env:BROKER_ALLOW_WRITE"

& $Python -u "$Root\scripts\factories\run_three_factories.py" @FactoryArgs
exit $LASTEXITCODE
