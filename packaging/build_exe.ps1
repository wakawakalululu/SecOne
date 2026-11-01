param(
    [string]$Python = "",
    [switch]$Clean,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    if (-not $Python) {
        $embedded = Join-Path $Root ".python\python.exe"
        if (Test-Path $embedded) { $Python = $embedded } else { $Python = "python" }
    }

    Write-Host "Python: $Python"
    & $Python -c "import sys; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw "Python 不可用：$Python" }

    if (-not $SkipTests) {
        Write-Host "运行测试 ..."
        & $Python -m pytest tests -q
        if ($LASTEXITCODE -ne 0) { throw "测试失败，已停止打包" }
    }

    $nuitkaOk = $false
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Python -c "import nuitka" 2>$null | Out-Null
        $nuitkaOk = ($LASTEXITCODE -eq 0)
    }
    catch {
        $nuitkaOk = $false
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if (-not $nuitkaOk) {
        throw "未安装 Nuitka。请先运行：`"$Python`" -m pip install nuitka ordered-set zstandard"
    }

    $dist = Join-Path $Root "dist"
    $build = Join-Path $Root "build\nuitka"
    if ($Clean) {
        Remove-Item $dist, $build -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $dist, $build | Out-Null

    $env:PYTHONPATH = Join-Path $Root "src"
    Write-Host "Nuitka standalone 构建 ..."
    & $Python -m nuitka `
        --standalone `
        --assume-yes-for-downloads `
        --enable-plugin=pyside6 `
        --windows-console-mode=disable `
        --windows-icon-from-ico=assets/secone.ico `
        --output-dir=$build `
        --output-filename=SecOne.exe `
        --company-name="SecOne Contributors" `
        --product-name="SecOne" `
        --file-description="SecOne local AI security analysis workstation" `
        --file-version="1.0.0.0" `
        --product-version="1.0.0.0" `
        --include-package=secone `
        --nofollow-import-to=pytest `
        --nofollow-import-to=tests `
        run_secone.py
    if ($LASTEXITCODE -ne 0) { throw "Nuitka 构建失败" }

    $built = Get-ChildItem $build -Directory -Filter "*.dist" | Select-Object -First 1
    if (-not $built) { throw "未找到 Nuitka standalone 输出目录" }

    $target = Join-Path $dist "SecOne"
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item $built.FullName $target -Recurse

    foreach ($item in @("config", "assets", "licenses")) {
        Copy-Item (Join-Path $Root $item) (Join-Path $target $item) -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $target "models") | Out-Null
    Copy-Item (Join-Path $Root "models\model.json") (Join-Path $target "models\model.json") -Force
    Copy-Item (Join-Path $Root "models\README.md") (Join-Path $target "models\README.md") -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $target "runtime") | Out-Null
    Copy-Item (Join-Path $Root "runtime\README.md") (Join-Path $target "runtime\README.md") -Force
    Copy-Item (Join-Path $Root "LICENSE") $target -Force
    Copy-Item (Join-Path $Root "NOTICE.md") $target -Force
    Copy-Item (Join-Path $Root "THIRD_PARTY_NOTICES.md") $target -Force
    foreach ($dir in @("data", "workspace", "output", "logs")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $target $dir) | Out-Null
    }

    Write-Host ""
    Write-Host "构建完成：$target\SecOne.exe"
    Write-Host "下一步：用 Inno Setup 编译 packaging\SecOne.iss"
}
finally {
    Pop-Location
}
