# PowerShell script to verify GitHub profile setup
# Version 2.0 - Enhanced Profile Verification

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "     GitHub Profile Setup Verification v2.0    " -ForegroundColor Yellow
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

$errors = 0
$warnings = 0
$success = 0

# Function to display status
function Show-Status {
    param(
        [string]$Message,
        [string]$Type = "INFO"
    )
    
    switch ($Type) {
        "OK" { 
            Write-Host "[OK] $Message" -ForegroundColor Green
            $script:success++
        }
        "ERROR" { 
            Write-Host "[ERROR] $Message" -ForegroundColor Red
            $script:errors++
        }
        "WARNING" { 
            Write-Host "[!] $Message" -ForegroundColor Yellow
            $script:warnings++
        }
        "INFO" { 
            Write-Host "[i] $Message" -ForegroundColor Cyan
        }
    }
}

# Check core files
Write-Host "Checking Core Files:" -ForegroundColor Magenta
Write-Host "--------------------"

# Check README.md
if (Test-Path -Path "README.md") {
    Show-Status "README.md file exists" "OK"
    
    $readmeContent = Get-Content -Path "README.md" -Raw
    
    # Check for new features
    if ($readmeContent -match "readme-typing-svg") {
        Show-Status "Animated typing header found" "OK"
    } else {
        Show-Status "Animated typing header missing" "WARNING"
    }
    
    if ($readmeContent -match "capsule-render") {
        Show-Status "Wave banner animation found" "OK"
    } else {
        Show-Status "Wave banner animation missing" "WARNING"
    }
    
    if ($readmeContent -match "github-readme-stats") {
        Show-Status "GitHub stats widgets found" "OK"
    } else {
        Show-Status "GitHub stats widgets missing" "WARNING"
    }
    
    if ($readmeContent -match "github-profile-trophy") {
        Show-Status "Trophy section found" "OK"
    } else {
        Show-Status "Trophy section missing" "WARNING"
    }
} else {
    Show-Status "README.md file not found!" "ERROR"
}

# Check setup instructions
if (Test-Path -Path "SETUP_INSTRUCTIONS.md") {
    Show-Status "Setup instructions found" "OK"
} else {
    Show-Status "Setup instructions missing" "WARNING"
}

# Check GitHub Actions workflows
Write-Host ""
Write-Host "Checking GitHub Actions:" -ForegroundColor Magenta
Write-Host "------------------------"

if (Test-Path -Path ".github\workflows") {
    Show-Status "Workflows directory exists" "OK"
    
    if (Test-Path -Path ".github\workflows\metrics.yml") {
        Show-Status "Metrics workflow found" "OK"
    } else {
        Show-Status "Metrics workflow missing" "ERROR"
    }
    
    if (Test-Path -Path ".github\workflows\header.yml") {
        Show-Status "Header workflow found" "OK"
    } else {
        Show-Status "Header workflow missing" "WARNING"
    }
} else {
    Show-Status "GitHub Actions directory missing" "ERROR"
}

# Check assets
Write-Host ""
Write-Host "Checking Assets:" -ForegroundColor Magenta
Write-Host "----------------"

if (Test-Path -Path "assets") {
    Show-Status "Assets directory exists" "OK"
    
    if (Test-Path -Path "assets\custom-banner.html") {
        Show-Status "Custom banner template found" "OK"
    }
} else {
    Show-Status "Assets directory missing" "WARNING"
}

# Check Git configuration
Write-Host ""
Write-Host "Checking Git Configuration:" -ForegroundColor Magenta
Write-Host "---------------------------"

if (Test-Path -Path ".git") {
    Show-Status "Git repository initialized" "OK"
    
    # Check remote
    try {
        $remotes = git remote -v 2>$null
        if ($remotes) {
            Show-Status "Git remote configured" "OK"
        } else {
            Show-Status "No Git remote configured" "WARNING"
        }
    } catch {
        Show-Status "Could not check Git remotes" "WARNING"
    }
} else {
    Show-Status "Git not initialized" "WARNING"
}

# Display summary
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "                   SUMMARY                     " -ForegroundColor Yellow
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Success: $success" -ForegroundColor Green
Write-Host "Warnings: $warnings" -ForegroundColor Yellow
Write-Host "Errors: $errors" -ForegroundColor Red

# Provide next steps based on status
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Magenta
Write-Host "-----------"

if ($errors -gt 0) {
    Write-Host "Please fix the errors above before proceeding." -ForegroundColor Red
} else {
    Write-Host "1. Create repository:" -ForegroundColor Green
    Write-Host "   - Go to https://github.com/new" -ForegroundColor White
    Write-Host "   - Name it 'ChiR24' (your username)" -ForegroundColor White
    Write-Host "   - Make it PUBLIC" -ForegroundColor White
    Write-Host ""
    
    if (-not (Test-Path -Path ".git")) {
        Write-Host "2. Initialize Git:" -ForegroundColor Green
        Write-Host "   git init" -ForegroundColor White
        Write-Host ""
    }
    
    Write-Host "3. Stage and commit:" -ForegroundColor Green
    Write-Host "   git add ." -ForegroundColor White
    Write-Host "   git commit -m 'Awesome profile with advanced features'" -ForegroundColor White
    Write-Host ""
    
    Write-Host "4. Add remote and push:" -ForegroundColor Green
    Write-Host "   git remote add origin https://github.com/ChiR24/ChiR24.git" -ForegroundColor White
    Write-Host "   git branch -M main" -ForegroundColor White
    Write-Host "   git push -u origin main" -ForegroundColor White
    Write-Host ""
    
    Write-Host "5. Enable GitHub Actions:" -ForegroundColor Green
    Write-Host "   - Go to repository Settings > Actions > General" -ForegroundColor White
    Write-Host "   - Set to 'Read and write permissions'" -ForegroundColor White
    Write-Host "   - Save changes" -ForegroundColor White
    Write-Host ""
    
    Write-Host "6. Trigger workflows:" -ForegroundColor Green
    Write-Host "   - Go to Actions tab" -ForegroundColor White
    Write-Host "   - Run workflows manually for initial setup" -ForegroundColor White
    Write-Host ""
}

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Profile URL: " -NoNewline -ForegroundColor Yellow
Write-Host "https://github.com/ChiR24" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# ASCII Art celebration if no errors
if ($errors -eq 0) {
    Write-Host "     Congratulations!" -ForegroundColor Magenta
    Write-Host "  Your profile is ready to shine!" -ForegroundColor Magenta
    Write-Host "         * * *" -ForegroundColor Yellow
}