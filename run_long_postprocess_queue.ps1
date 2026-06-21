$ErrorActionPreference = "Continue"
# This queue is only for videos over the old 30-minute threshold but within the
# current 1-hour ASR policy. Videos longer than 1 hour should not run Whisper.
$bvids = @(
  "BV1Nd596vEyU",
  "BV1NvRyBzEhq",
  "BV1fGjG66EK7",
  "BV1v1La6dEME"
)

$logDir = Join-Path $PSScriptRoot "downloads\manifests"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ("long-postprocess-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

foreach ($bvid in $bvids) {
  $start = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$start] START $bvid" | Tee-Object -FilePath $logPath -Append
  python .\postprocess_bili_videos.py --model large-v3-turbo --device cuda --force --bvid $bvid *>> $logPath
  $exitCode = $LASTEXITCODE
  $end = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$end] END $bvid exit=$exitCode" | Tee-Object -FilePath $logPath -Append
}

"[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] QUEUE_DONE" | Tee-Object -FilePath $logPath -Append
