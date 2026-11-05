param(
    [Parameter(Mandatory)] [string]$Image,
    [Parameter(Mandatory)] [int]$DiskNumber,
    [Parameter(Mandatory)] [string]$Log
)
$ErrorActionPreference = 'Stop'
Start-Transcript -Path $Log -Force | Out-Null
try {
    # Safety checks: must be the ~32 GB USB card, never a boot/system disk.
    $disk = Get-Disk -Number $DiskNumber
    $sizeGB = $disk.Size / 1GB
    if ($disk.IsBoot -or $disk.IsSystem) { throw "Disk $DiskNumber is a boot/system disk. Aborting." }
    if ($disk.BusType -ne 'USB') { throw "Disk $DiskNumber is not USB ($($disk.BusType)). Aborting." }
    if ($sizeGB -lt 28 -or $sizeGB -gt 33) { throw "Disk $DiskNumber is $([math]::Round($sizeGB,1)) GB, not the 32 GB card. Aborting." }
    Write-Host "Target: disk $DiskNumber, $($disk.FriendlyName), $([math]::Round($sizeGB,1)) GB, $($disk.BusType)"

    # Remove partitions so Windows has no mounted volumes on the card.
    Clear-Disk -Number $DiskNumber -RemoveData -RemoveOEM -Confirm:$false
    Write-Host "Cleared partitions."

    $sector = 512
    $head = 1MB  # written last, so Windows doesn't mount the new partitions mid-write
    $buf = New-Object byte[] (4MB)
    $headBuf = New-Object byte[] $head
    $sha = [Security.Cryptography.SHA256]::Create()

    $dev = New-Object IO.FileStream("\\.\PhysicalDrive$DiskNumber", [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    $in = [IO.File]::OpenRead($Image)
    $gz = New-Object IO.Compression.GZipStream($in, [IO.Compression.CompressionMode]::Decompress)
    [int64]$total = 0
    $fill = 0
    $lastReport = 0
    try {
        while ($true) {
            # Fill the buffer completely (GZipStream returns short reads).
            $fill = 0
            while ($fill -lt $buf.Length) {
                $n = $gz.Read($buf, $fill, $buf.Length - $fill)
                if ($n -le 0) { break }
                $fill += $n
            }
            if ($fill -eq 0) { break }
            $null = $sha.TransformBlock($buf, 0, $fill, $null, 0)
            $writeLen = $fill
            if ($writeLen % $sector -ne 0) {
                $pad = $sector - ($writeLen % $sector)
                [Array]::Clear($buf, $writeLen, $pad)
                $writeLen += $pad
            }
            # Split this chunk into the part inside the first 1 MB (saved) and the rest (written now).
            $start = $total
            $end = $total + $writeLen
            if ($start -lt $head) {
                $headPart = [int][math]::Min([int64]$writeLen, [int64]($head - $start))
                [Array]::Copy($buf, 0, $headBuf, $start, $headPart)
                if ($writeLen -gt $headPart) {
                    $dev.Position = $head
                    $dev.Write($buf, $headPart, $writeLen - $headPart)
                }
            } else {
                $dev.Position = $start
                $dev.Write($buf, 0, $writeLen)
            }
            $total += $fill
            if ($total - $lastReport -ge 256MB) { Write-Host ("Written {0:N0} MB" -f ($total / 1MB)); $lastReport = $total }
            if ($fill -lt $buf.Length) { break }
        }
        $null = $sha.TransformFinalBlock((New-Object byte[] 0), 0, 0)
        $dev.Position = 0
        $dev.Write($headBuf, 0, [int][math]::Min([int64]$head, [int64]([math]::Ceiling($total / $sector) * $sector)))
        $dev.Flush()
    } finally {
        $gz.Dispose(); $in.Dispose(); $dev.Dispose()
    }
    $imgHash = [BitConverter]::ToString($sha.Hash).Replace('-', '')
    Write-Host ("Wrote {0:N0} bytes. Image SHA256 {1}" -f $total, $imgHash)

    # Read back the same number of bytes and compare.
    $sha2 = [Security.Cryptography.SHA256]::Create()
    $rd = New-Object IO.FileStream("\\.\PhysicalDrive$DiskNumber", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        [int64]$left = $total
        while ($left -gt 0) {
            $want = [int][math]::Min([int64]$buf.Length, [int64]([math]::Ceiling($left / $sector) * $sector))
            $n = $rd.Read($buf, 0, $want)
            if ($n -le 0) { throw "Read-back ended early with $left bytes left." }
            $use = [int][math]::Min([int64]$n, $left)
            $null = $sha2.TransformBlock($buf, 0, $use, $null, 0)
            $left -= $use
        }
        $null = $sha2.TransformFinalBlock((New-Object byte[] 0), 0, 0)
    } finally { $rd.Dispose() }
    $diskHash = [BitConverter]::ToString($sha2.Hash).Replace('-', '')
    Write-Host "Card SHA256  $diskHash"
    if ($diskHash -eq $imgHash) { Write-Host "RESULT: VERIFIED" } else { Write-Host "RESULT: MISMATCH" }
    Update-Disk -Number $DiskNumber
} catch {
    Write-Host "RESULT: FAILED - $($_.Exception.Message)"
} finally {
    Stop-Transcript | Out-Null
}
