import subprocess, os
ROOT = r"%USERPROFILE%\Multi-platform information management tool"
env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
env.pop("HERMES_HOME", None)
env.pop("HERMES_GIT_BASH_PATH", None)

r = subprocess.run(
    ["lark-cli", "--profile", "default", "base", "+record-list", "--as", "user",
     "--base-token", "ZCf1bxiooaqQHPsEKQAcIaARndf",
     "--table-id", "tblx1hxfoi1Y4lk0", "--limit", "3",
     "--field-id", "博主名称", "--format", "json"],
    cwd=ROOT, capture_output=True, text=True,
    encoding="utf-8", errors="replace", env=env, timeout=30,
)
print("returncode:", r.returncode)
print("stdout len:", len(r.stdout))
print("stderr len:", len(r.stderr))
print("stdout[:500]:", repr(r.stdout[:500]))
print("stderr[:500]:", repr(r.stderr[:500]))
