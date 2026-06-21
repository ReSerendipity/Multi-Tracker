import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST_ROOT = ROOT / "downloads" / "manifests"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def command_env():
    env = os.environ.copy()
    env.pop("HERMES_HOME", None)
    env.pop("HERMES_GIT_BASH_PATH", None)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LARK_CLI_NO_PROXY"] = "1"
    return env


def normalize_command(args):
    if not args:
        return args
    executable = shutil.which(args[0]) or args[0]
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd", "/c", executable, *args[1:]]
    return [executable, *args[1:]]


def run_step(name, args, *, timeout=None):
    started_perf = time.perf_counter()
    started_at = now_str()
    print(f"[{name}] {' '.join(args)}")
    result = subprocess.run(
        normalize_command(args),
        cwd=ROOT,
        env=command_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return {
        "name": name,
        "started_at": started_at,
        "ended_at": now_str(),
        "returncode": result.returncode,
        "elapsed_seconds": round(time.perf_counter() - started_perf, 3),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "args": args,
    }


def latest_manifest(pattern, since):
    if not MANIFEST_ROOT.exists():
        return None
    candidates = [
        path
        for path in MANIFEST_ROOT.glob(pattern)
        if path.is_file() and path.stat().st_mtime >= since
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_manifest_summary(path):
    if not path:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}
    return payload.get("summary")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def platform_enabled(args, platform):
    return args.platform in {"all", platform}


def bili_dry_run_summary(args):
    import download_bili_following_latest as bili

    config = bili.load_config()
    creators = bili.load_creators(config, args.bili_max_creators)
    existing = bili.existing_bvids(config)
    return {
        "tracked_creators": len(creators),
        "existing_bvids": len(existing),
        "note": "Bili dry-run does not list remote videos; real run uses download_bili_following_latest.py.",
    }


def build_bili_command(args):
    cmd = [
        sys.executable,
        str(ROOT / "download_bili_following_latest.py"),
        "--videos-per-creator",
        str(args.bili_videos_per_creator),
        "--retries",
        str(args.bili_retries),
    ]
    if args.bili_max_creators is not None:
        cmd.extend(["--max-creators", str(args.bili_max_creators)])
    if args.bili_max_total_videos is not None:
        cmd.extend(["--max-total-videos", str(args.bili_max_total_videos)])
    if args.bili_only_today:
        cmd.append("--only-today")
    if args.bili_skip_comments:
        cmd.append("--skip-comments")
    return cmd


def build_douyin_download_command(args):
    cmd = [
        sys.executable,
        str(ROOT / "download_douyin_latest.py"),
        "--from-feishu",
        "--videos-per-creator",
        str(args.douyin_videos_per_creator),
        "--model",
        args.douyin_model,
        "--device",
        args.douyin_device,
        "--cdp-port",
        str(args.douyin_cdp_port),
    ]
    if args.douyin_max_creators is not None:
        cmd.extend(["--max-creators", str(args.douyin_max_creators)])
    if args.douyin_transcribe:
        cmd.append("--transcribe")
    else:
        cmd.append("--skip-transcribe")
    if args.douyin_force:
        cmd.append("--force")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.no_douyin_skip_existing:
        cmd.append("--no-skip-existing-feishu")
    if not args.include_existing_bili_creators:
        cmd.append("--skip-bili-linked-creators")
    return cmd


def build_douyin_sync_command(args, manifest_path):
    cmd = [
        sys.executable,
        str(ROOT / "sync_douyin_to_feishu.py"),
        "--manifest",
        str(manifest_path),
    ]
    if args.include_existing_bili_creators:
        cmd.append("--include-existing-bili-creators")
    return cmd


def build_douyin_enrich_command(args):
    cmd = [
        sys.executable,
        str(ROOT / "enrich_douyin_feishu.py"),
    ]
    if args.douyin_enrich_overwrite:
        cmd.append("--overwrite")
    return cmd


def parse_args():
    parser = argparse.ArgumentParser(description="Run latest-video ingestion for Bilibili and Douyin creators.")
    parser.add_argument("--platform", choices=["all", "bili", "douyin"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Do not write or download Bili; parse Douyin only.")
    parser.add_argument("--stop-on-error", action="store_true")

    parser.add_argument("--bili-videos-per-creator", type=int, default=3)
    parser.add_argument("--bili-max-creators", type=int, default=None)
    parser.add_argument("--bili-max-total-videos", type=int, default=None)
    parser.add_argument("--bili-retries", type=int, default=1)
    parser.add_argument("--bili-only-today", action="store_true")
    parser.add_argument("--bili-skip-comments", action="store_true")

    parser.add_argument("--douyin-videos-per-creator", type=int, default=1)
    parser.add_argument("--douyin-max-creators", type=int, default=None)
    parser.add_argument("--douyin-transcribe", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--douyin-model", default="large-v3-turbo")
    parser.add_argument("--douyin-device", default="cuda")
    parser.add_argument("--douyin-cdp-port", type=int, default=9333)
    parser.add_argument("--douyin-force", action="store_true")
    parser.add_argument("--douyin-enrich", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--douyin-enrich-overwrite", action="store_true")
    parser.add_argument("--no-douyin-skip-existing", action="store_true")
    parser.add_argument(
        "--include-existing-bili-creators",
        action="store_true",
        help="When syncing Douyin, also create Douyin video rows for creators that already have a Bili MID.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    run_started_mtime = time.time()
    result = {
        "started_at": now_str(),
        "platform": args.platform,
        "dry_run": args.dry_run,
        "steps": [],
        "manifests": {},
        "summaries": {},
        "failures": [],
    }

    if platform_enabled(args, "bili"):
        if args.dry_run:
            summary = bili_dry_run_summary(args)
            result["summaries"]["bili"] = summary
            print(json.dumps({"bili_dry_run": summary}, ensure_ascii=False, indent=2))
        else:
            before = time.time()
            step = run_step("bili_download", build_bili_command(args), timeout=None)
            result["steps"].append(step)
            manifest = latest_manifest("*-bili-latest-download.json", before)
            if manifest:
                result["manifests"]["bili_download"] = str(manifest)
                result["summaries"]["bili_download"] = read_manifest_summary(manifest)
            if step["returncode"] != 0:
                result["failures"].append({"step": "bili_download", "returncode": step["returncode"]})
                if args.stop_on_error:
                    result["ended_at"] = now_str()
                    write_json(MANIFEST_ROOT / f"{ts_slug()}-all-platform-latest.json", result)
                    raise SystemExit(step["returncode"])

    if platform_enabled(args, "douyin"):
        before = time.time()
        step = run_step("douyin_download", build_douyin_download_command(args), timeout=None)
        result["steps"].append(step)
        douyin_manifest = latest_manifest("*-douyin-latest-download.json", before)
        if douyin_manifest:
            result["manifests"]["douyin_download"] = str(douyin_manifest)
            douyin_summary = read_manifest_summary(douyin_manifest)
            result["summaries"]["douyin_download"] = douyin_summary
        else:
            douyin_summary = None
        if step["returncode"] != 0:
            result["failures"].append({"step": "douyin_download", "returncode": step["returncode"]})
            if args.stop_on_error:
                result["ended_at"] = now_str()
                write_json(MANIFEST_ROOT / f"{ts_slug()}-all-platform-latest.json", result)
                raise SystemExit(step["returncode"])
        if not args.dry_run and douyin_manifest and (douyin_summary or {}).get("downloaded", 0) > 0:
            sync_before = time.time()
            sync_step = run_step("douyin_feishu_sync", build_douyin_sync_command(args, douyin_manifest), timeout=None)
            result["steps"].append(sync_step)
            sync_manifest = latest_manifest("*-douyin-feishu-sync.json", sync_before)
            if sync_manifest:
                result["manifests"]["douyin_feishu_sync"] = str(sync_manifest)
                result["summaries"]["douyin_feishu_sync"] = read_manifest_summary(sync_manifest)
            if sync_step["returncode"] != 0:
                result["failures"].append({"step": "douyin_feishu_sync", "returncode": sync_step["returncode"]})
                if args.stop_on_error:
                    result["ended_at"] = now_str()
                    write_json(MANIFEST_ROOT / f"{ts_slug()}-all-platform-latest.json", result)
                    raise SystemExit(sync_step["returncode"])
        if not args.dry_run and args.douyin_enrich and step["returncode"] == 0:
            enrich_before = time.time()
            enrich_step = run_step("douyin_feishu_enrich", build_douyin_enrich_command(args), timeout=None)
            result["steps"].append(enrich_step)
            enrich_manifest = latest_manifest("*-douyin-feishu-enrich.json", enrich_before)
            if enrich_manifest:
                result["manifests"]["douyin_feishu_enrich"] = str(enrich_manifest)
                result["summaries"]["douyin_feishu_enrich"] = read_manifest_summary(enrich_manifest)
            if enrich_step["returncode"] != 0:
                result["failures"].append({"step": "douyin_feishu_enrich", "returncode": enrich_step["returncode"]})
                if args.stop_on_error:
                    result["ended_at"] = now_str()
                    write_json(MANIFEST_ROOT / f"{ts_slug()}-all-platform-latest.json", result)
                    raise SystemExit(enrich_step["returncode"])

    result["ended_at"] = now_str()
    result["summary"] = {
        "steps": len(result["steps"]),
        "failed_steps": len(result["failures"]),
        "dry_run": args.dry_run,
    }
    manifest_path = MANIFEST_ROOT / f"{ts_slug()}-all-platform-latest.json"
    write_json(manifest_path, result)
    print(json.dumps({"manifest": str(manifest_path), "summary": result["summary"], "summaries": result["summaries"]}, ensure_ascii=False, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
