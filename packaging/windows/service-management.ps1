$script:ScExePath = Join-Path $env:SystemRoot "System32\sc.exe"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)

    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated PowerShell session."
    }
}

function Invoke-ServiceCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    if (-not (Test-Path -LiteralPath $script:ScExePath)) {
        throw "sc.exe not found at $script:ScExePath"
    }

    & $script:ScExePath @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "$script:ScExePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function New-ScOption {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    return "$Name= $Value"
}

function Get-ServiceInstance {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $escapedName = $Name.Replace("'", "''")
    return Get-CimInstance -ClassName Win32_Service -Filter "Name='$escapedName'" -ErrorAction SilentlyContinue
}

function Wait-ForServiceState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedState,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do {
        $serviceInstance = Get-ServiceInstance -Name $Name
        if ($null -eq $serviceInstance) {
            return $null
        }

        if ($serviceInstance.State -eq $ExpectedState) {
            return $serviceInstance
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return Get-ServiceInstance -Name $Name
}

function Wait-ForServiceRemoval {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do {
        if ($null -eq (Get-ServiceInstance -Name $Name)) {
            return $true
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Stop-ServiceRegistration {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [int]$TimeoutSeconds = 30
    )

    $serviceInstance = Get-ServiceInstance -Name $Name
    if ($null -eq $serviceInstance) {
        return
    }

    if ($serviceInstance.State -ne "Stopped") {
        try {
            Stop-Service -Name $Name -Force -ErrorAction Stop
        }
        catch {
            $stopResult = Invoke-CimMethod -InputObject $serviceInstance -MethodName StopService -ErrorAction SilentlyContinue
            if ($null -ne $stopResult -and $stopResult.ReturnValue -notin @(0, 5)) {
                throw "Stopping service '$Name' failed with return value $($stopResult.ReturnValue)."
            }
        }

        $serviceInstance = Wait-ForServiceState -Name $Name -ExpectedState "Stopped" -TimeoutSeconds $TimeoutSeconds
        if ($null -ne $serviceInstance -and $serviceInstance.State -ne "Stopped" -and $serviceInstance.ProcessId -gt 0) {
            Stop-Process -Id $serviceInstance.ProcessId -Force -ErrorAction SilentlyContinue
            $serviceInstance = Wait-ForServiceState -Name $Name -ExpectedState "Stopped" -TimeoutSeconds 10
        }

        if ($null -ne $serviceInstance -and $serviceInstance.State -ne "Stopped") {
            throw "Service '$Name' did not stop within $TimeoutSeconds seconds."
        }
    }
}

function Remove-ServiceRegistration {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [int]$TimeoutSeconds = 45
    )

    Stop-ServiceRegistration -Name $Name -TimeoutSeconds $TimeoutSeconds

    $serviceInstance = Get-ServiceInstance -Name $Name
    if ($null -eq $serviceInstance) {
        return
    }

    $deleteResult = Invoke-CimMethod -InputObject $serviceInstance -MethodName Delete -ErrorAction SilentlyContinue
    if ($null -ne $deleteResult -and $deleteResult.ReturnValue -notin @(0, 16)) {
        if (-not (Wait-ForServiceRemoval -Name $Name -TimeoutSeconds $TimeoutSeconds)) {
            throw "Deleting service '$Name' failed with return value $($deleteResult.ReturnValue)."
        }

        return
    }

    if (-not (Wait-ForServiceRemoval -Name $Name -TimeoutSeconds $TimeoutSeconds)) {
        throw "Service '$Name' is still registered after the delete request. Close tools like Services.msc or Event Viewer and retry."
    }
}
