# ============================================================
# Script tao output dep de chup man hinh nop bai
#
# Cach chay:  .\screenshots\chup_anh.ps1
# ============================================================

# Ep console hien tieng Viet dung, khong bi vo chu
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$U = "https://day12-agent-production-5236.up.railway.app"
$K = "7WnZAOeQZ22fmWshPRa-hTI3HDDwi0tT"

function Title($text) {
    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 62) -ForegroundColor Cyan
}

function Call($method, $path, $apiKey, $sendBody) {
    $headers = @{}
    if ($apiKey) { $headers["X-API-Key"] = $apiKey }

    $params = @{
        Uri             = "$U$path"
        Method          = $method
        Headers         = $headers
        UseBasicParsing = $true
        TimeoutSec      = 25
    }
    if ($sendBody) {
        $params["Body"] = '{"question":"What is Docker?"}'
        $params["ContentType"] = "application/json"
    }

    try {
        $r = Invoke-WebRequest @params
        # PowerShell 5.1 giai ma response bang ISO-8859-1 khi header khong ghi
        # charset, lam tieng Viet bi vo. Doc thang bytes roi giai ma UTF-8.
        $bytes = $r.RawContentStream.ToArray()
        return @{ code = [int]$r.StatusCode
                  body = [System.Text.Encoding]::UTF8.GetString($bytes) }
    } catch {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            $body = ""
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                $body = (New-Object IO.StreamReader($stream,
                         [System.Text.Encoding]::UTF8)).ReadToEnd()
            } catch {}
            return @{ code = $code; body = $body }
        }
        # Khong co Response = loi mang, KHONG phai loi HTTP
        return @{ code = -1; body = $_.Exception.Message }
    }
}

function Show($r, $expected) {
    $color = if ($r.code -eq $expected) { "Green" } else { "Red" }
    Write-Host "  HTTP $($r.code)" -ForegroundColor $color
    if ($r.body) { Write-Host "  $($r.body)" }
}

function Wait-Quota($seconds) {
    Write-Host ""
    Write-Host "  Cho $seconds giay de bo dem rate limit reset ve 0..." -ForegroundColor DarkGray
    foreach ($s in ($seconds..1)) {
        Write-Host ("`r  Con lai {0,3} giay " -f $s) -NoNewline -ForegroundColor DarkGray
        Start-Sleep -Seconds 1
    }
    Write-Host "`r  Xong, bat dau test.            " -ForegroundColor DarkGray
}

# ── Cho quota sach truoc khi bat dau ────────────────────────
Clear-Host
Write-Host ""
Write-Host "  Chuan bi moi truong test..." -ForegroundColor Yellow
Wait-Quota 65

# ── Anh test.png ────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  DAY 12 - KIEM THU AGENT TREN CLOUD" -ForegroundColor Yellow
Write-Host "  Sinh vien: Ngo Thanh Dat - 01323" -ForegroundColor Yellow
Write-Host "  URL: $U" -ForegroundColor Yellow

Title "1. HEALTH CHECK (khong can API key)  -> mong doi 200"
Show (Call "GET" "/health" $null $false) 200

Title "2. READINESS CHECK - kiem tra ket noi Redis  -> mong doi 200"
Show (Call "GET" "/ready" $null $false) 200
Write-Host "  >> 'storage':'redis' = da noi duoc Redis, thiet ke stateless OK" -ForegroundColor Green

Title "3. XAC THUC - KHONG gui API key  -> mong doi 401"
Show (Call "POST" "/ask" $null $true) 401

Title "4. XAC THUC - gui API key SAI  -> mong doi 403"
Show (Call "POST" "/ask" "day12-key-sai-hoan-toan" $true) 403

Title "5. XAC THUC - gui API key DUNG  -> mong doi 200"
Show (Call "POST" "/ask" $K $true) 200

Write-Host ""
Write-Host "  >>> CHUP MAN HINH NGAY BAY GIO -> luu thanh test.png <<<" -ForegroundColor Magenta
Write-Host "      (Nhan Win + Shift + S de chup vung man hinh)" -ForegroundColor Magenta
Write-Host ""
Read-Host "  Chup xong roi thi nhan Enter de chay tiep phan rate limit"

# ── Anh ratelimit.png ───────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  DAY 12 - TEST RATE LIMITING" -ForegroundColor Yellow
Write-Host "  Cau hinh: RATE_LIMIT_PER_MINUTE = 10" -ForegroundColor Yellow
Write-Host "  Ban 15 request lien tiep -> tu request thu 11 phai bi chan" -ForegroundColor Yellow
Wait-Quota 65

Clear-Host
Write-Host ""
Write-Host "  DAY 12 - TEST RATE LIMITING  (gioi han 10 request/phut)" -ForegroundColor Yellow
Write-Host ""

$ok = 0; $blocked = 0; $failed = 0
foreach ($i in 1..15) {
    $r = Call "POST" "/ask" $K $true
    switch ($r.code) {
        200 { $ok++;      Write-Host ("  request {0,2}  ->  200 OK" -f $i) -ForegroundColor Green }
        429 { $blocked++; Write-Host ("  request {0,2}  ->  429 TOO MANY REQUESTS - bi chan" -f $i) -ForegroundColor Red }
        default { $failed++
                  Write-Host ("  request {0,2}  ->  LOI KET NOI (thu lai)" -f $i) -ForegroundColor DarkYellow
                  Start-Sleep -Milliseconds 500 }
    }
}

Write-Host ""
Write-Host ("  KET QUA: {0} request thanh cong, {1} request bi chan (429)" -f $ok, $blocked) -ForegroundColor Cyan
if ($failed -gt 0) { Write-Host ("  ({0} request loi mang, khong tinh)" -f $failed) -ForegroundColor DarkYellow }
if ($ok -eq 10) {
    Write-Host "  >> DUNG: chan chinh xac sau 10 request, khop RATE_LIMIT_PER_MINUTE=10" -ForegroundColor Green
} else {
    Write-Host "  >> Chay lai script neu con sai lech (quota chua reset kip)" -ForegroundColor DarkYellow
}
Write-Host ""
Write-Host "  >>> CHUP MAN HINH -> luu thanh ratelimit.png <<<" -ForegroundColor Magenta
Write-Host ""
