# PowerShell script to verify GitHub profile setup

Write-Host "GitHub Profile Setup Verification"
Write-Host "================================="
Write-Host ""

# Check if README.md exists
if (Test-Path -Path "README.md") {
    Write-Host "[OK] README.md file exists."
    
    # Check if README contains animation
    $readmeContent = Get-Content -Path "README.md" -Raw
    if ($readmeContent -match "github-contribution-grid-snake.svg") {
        Write-Host "[OK] README contains GitHub snake animation."
    } else {
        Write-Host "[WARNING] README may not have a valid animation link."
    }
} else {
    Write-Host "[ERROR] README.md file not found!"
}

Write-Host ""
Write-Host "Next Steps:"
Write-Host "1. Create a new repository named 'ChiR24' on GitHub"
Write-Host "2. Initialize Git in this folder (if not already done):"
Write-Host "   git init"
Write-Host "3. Stage and commit all changes:"
Write-Host "   git add ."
Write-Host "   git commit -m 'Update profile with GitHub snake animation'"
Write-Host "4. Connect and push to GitHub:"
Write-Host "   git remote add origin https://github.com/ChiR24/ChiR24.git"
Write-Host "   git push -u origin main"
Write-Host ""
Write-Host "Your profile should appear at: https://github.com/ChiR24" 