# -*- coding: utf-8 -*-
"""
Scheduled wrapper for AkShare -> SQLite market data updates.

This script is intended for systemd/cron. It adds:
- process locking to avoid overlapping updates
- whole-run retries when the update script exits non-zero
- append-only logs under logs/data_update.log by default
"""

import argparse
import fcntl
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "market_data.sqlite3"
DEFAULT_LOG_PATH = REPO_ROOT / "logs" / "data_update.log"
DEFAULT_LOCK_PATH = REPO_ROOT / "data" / "data_update.lock"
DEFAULT_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
DEFAULT_BENCHMARK_CODES = ["000001.SH", "000300.SH"]


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return shlex.split(value)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_line(log_file, message: str):
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    print(line, file=log_file, flush=True)


def build_update_command(args: argparse.Namespace) -> list[str]:
    python_bin = Path(args.python)
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    command = [
        str(python_bin),
        str(REPO_ROOT / "tools" / "updata_data.py"),
        "--start-date",
        args.start_date,
        "--sqlite-db-path",
        str(Path(args.sqlite_db_path).expanduser()),
        "--max-workers",
        str(args.max_workers),
        "--retries",
        str(args.fetch_retries),
        "--retry-delay",
        str(args.fetch_retry_delay),
        "--adj",
        args.adj,
        "--benchmark-codes",
        *args.benchmark_codes,
        "--no-progress",
    ]

    if args.end_date:
        command.extend(["--end-date", args.end_date])
    if args.force_full:
        command.append("--force-full")
    if args.dry_run:
        command.append("--dry-run")
    if args.show_progress:
        command.remove("--no-progress")

    extra_args = list(args.extra_args or [])
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]
    command.extend(extra_args)
    return command


def run_command(command: list[str], log_file) -> int:
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        print(line, end="", file=log_file, flush=True)
    return process.wait()


def run_with_retries(args: argparse.Namespace, log_file) -> int:
    attempts = max(1, int(args.run_retries))
    command = build_update_command(args)
    redacted_command = " ".join(shlex.quote(part) for part in command)

    for attempt in range(1, attempts + 1):
        write_line(log_file, f"开始第 {attempt}/{attempts} 次数据更新")
        write_line(log_file, f"命令: {redacted_command}")
        return_code = run_command(command, log_file)
        if return_code == 0:
            write_line(log_file, "数据更新完成")
            return 0

        write_line(log_file, f"数据更新失败，退出码 {return_code}")
        if attempt < attempts:
            wait_seconds = max(0.0, float(args.run_retry_delay)) * attempt
            write_line(log_file, f"{wait_seconds:.0f}s 后重试整轮更新")
            time.sleep(wait_seconds)

    write_line(log_file, f"数据更新失败，已尝试 {attempts} 次")
    return return_code or 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="定时更新 AkShare ETF 行情数据到 SQLite")
    parser.add_argument("--python", default=os.getenv("ETF_UPDATE_PYTHON", str(DEFAULT_PYTHON)), help="Python解释器路径")
    parser.add_argument("--start-date", default=os.getenv("ETF_SCHEDULE_START_DATE", "20150101"), help="起始日期 YYYYMMDD")
    parser.add_argument("--end-date", default=os.getenv("ETF_SCHEDULE_END_DATE", ""), help="结束日期 YYYYMMDD，默认由更新脚本取今天")
    parser.add_argument("--sqlite-db-path", default=os.getenv("SQLITE_DB_PATH", str(DEFAULT_DB_PATH)), help="SQLite数据库路径")
    parser.add_argument("--max-workers", type=int, default=env_int("ETF_UPDATE_MAX_WORKERS", 4), help="并发拉取数量")
    parser.add_argument("--fetch-retries", type=int, default=env_int("AKSHARE_RETRY_TIMES", 5), help="单个AkShare调用尝试次数")
    parser.add_argument("--fetch-retry-delay", type=float, default=env_float("AKSHARE_RETRY_DELAY", 3.0), help="单个AkShare调用重试退避基准秒数")
    parser.add_argument("--run-retries", type=int, default=env_int("ETF_UPDATE_RUN_RETRIES", 3), help="整轮更新失败后的尝试次数")
    parser.add_argument("--run-retry-delay", type=float, default=env_float("ETF_UPDATE_RUN_RETRY_DELAY", 300.0), help="整轮更新重试退避基准秒数")
    parser.add_argument("--benchmark-codes", nargs="*", default=env_list("ETF_UPDATE_BENCHMARK_CODES", DEFAULT_BENCHMARK_CODES), help="同步更新的基准代码；传空值可禁用")
    parser.add_argument("--adj", default=os.getenv("AKSHARE_ADJ", "").strip(), choices=["", "qfq", "hfq"], help="AkShare复权参数")
    parser.add_argument("--log-path", default=os.getenv("ETF_UPDATE_LOG_PATH", str(DEFAULT_LOG_PATH)), help="日志文件路径")
    parser.add_argument("--lock-path", default=os.getenv("ETF_UPDATE_LOCK_PATH", str(DEFAULT_LOCK_PATH)), help="锁文件路径")
    parser.add_argument("--force-full", action="store_true", help="强制全量更新")
    parser.add_argument("--dry-run", action="store_true", help="只拉取不写入")
    parser.add_argument("--show-progress", action="store_true", help="显示tqdm进度条")
    parser.add_argument("extra_args", nargs=argparse.REMAINDER, help="透传给 tools/updata_data.py 的额外参数，需放在 -- 之后")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_path = Path(args.log_path).expanduser()
    lock_path = Path(args.lock_path).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w") as lock_file, log_path.open("a", encoding="utf-8") as log_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            write_line(log_file, "已有数据更新任务在运行，本次跳过")
            return 0

        lock_file.write(str(os.getpid()))
        lock_file.truncate()
        lock_file.flush()
        return run_with_retries(args, log_file)


if __name__ == "__main__":
    raise SystemExit(main())
