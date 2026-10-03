"""Релей от ноутбука к ВМ Hostkey: API/метрики Mercury + метрики нод GB10.

Четыре `-L`-сессии и пять `-R`-сессий (по одному форварду на соединение), которые
демон держит живыми:
  -L на gb10-1 (порт 5023): 9101 → node-exporter, 9401 → dcgm-exporter
  -L на gb10-2 (порт 5024): 9102 → node-exporter, 9402 → dcgm-exporter
  -R на ВМ: 8040 → шлюз Mercury, 9101/9401 → gb10-1, 9102/9402 → gb10-2

Каждый форвард — своё соединение: их слишком много вешается на одну ssh-сессию при
keep-alive скрейпах, и у ssh.exe на Windows есть лимит одновременных форвардов.

С ВМ адрес 10.0.0.9 не достигается напрямую, поэтому релей — ноут.

Команды: install | uninstall | start | stop | status | daemon
Файлы задачи: рядом со скриптом vm-relay.log / vm-relay.status.json / vm-relay.stop
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TASK_NAME = "vm-relay"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
CHECK_STEP = 10
# Каждое ssh-соединение держит не больше 40 одновременных форвардов, а Prometheus
# ходит по keep-alive. Дети переизбираются по этому таймеру, чтобы лимит не исчерпался.
CHILD_TTL_S = 600

VM_HOST = "82.25.174.72"
VM_USER = "root"
GW_HOST = "10.0.0.9"
KEY = str(Path.home() / ".ssh" / "id_ed25519")

BASE = [
    "-o", "BatchMode=yes",
    "-o", "IdentitiesOnly=yes",
    "-i", KEY,
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=12",
    "-N",
]

CHILDREN = [
    ("gb10-1 node", BASE + [
        "-p", "5023", "-L", "9101:127.0.0.1:9100", f"yskryuk3@{GW_HOST}",
    ]),
    ("gb10-1 dcgm", BASE + [
        "-p", "5023", "-L", "9401:127.0.0.1:9400", f"yskryuk3@{GW_HOST}",
    ]),
    ("gb10-2 node", BASE + [
        "-p", "5024", "-L", "9102:127.0.0.1:9100", f"yskryuk3@{GW_HOST}",
    ]),
    ("gb10-2 dcgm", BASE + [
        "-p", "5024", "-L", "9402:127.0.0.1:9400", f"yskryuk3@{GW_HOST}",
    ]),
    # Публикация тоже по одному процессу на порт: на общей сессии с пятью -R
    # скопившиеся half-closed каналы вешали очередь вокруг 9102.
    ("pub api", BASE + ["-R", f"0.0.0.0:8040:{GW_HOST}:8040", f"{VM_USER}@{VM_HOST}"]),
    ("pub node-a", BASE + ["-R", "0.0.0.0:9101:127.0.0.1:9101", f"{VM_USER}@{VM_HOST}"]),
    ("pub dcgm-a", BASE + ["-R", "0.0.0.0:9401:127.0.0.1:9401", f"{VM_USER}@{VM_HOST}"]),
    ("pub node-b", BASE + ["-R", "0.0.0.0:9102:127.0.0.1:9102", f"{VM_USER}@{VM_HOST}"]),
    ("pub dcgm-b", BASE + ["-R", "0.0.0.0:9402:127.0.0.1:9402", f"{VM_USER}@{VM_HOST}"]),
]


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with (ROOT / f"{TASK_NAME}.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def write_status(**fields):
    status = {}
    path = ROOT / f"{TASK_NAME}.status.json"
    if path.exists():
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    status.update(fields)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def pid_alive(pid):
    if not pid:
        return False
    proc = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=NO_WINDOW,
    )
    out = proc.stdout or ""
    return str(pid) in out


def cmd_daemon():
    procs = {}
    born = {}
    write_status(pid=os.getpid(), started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log("демон запущен")
    stopf = ROOT / f"{TASK_NAME}.stop"
    stopf.unlink(missing_ok=True)  #fresh start: старый stop-файл не должен гасить новый демон
    while True:
        if stopf.exists():
            stopf.unlink()
            for p in procs.values():
                p.terminate()
            log("остановлен командой stop")
            write_status(stopped_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            return
        now = time.time()
        changed = False
        for name, args in CHILDREN:
            proc = procs.get(name)
            alive = proc is not None and proc.poll() is None
            if alive and now - born[name] < CHILD_TTL_S:
                continue
            if proc is not None:
                why = "жив, но пора обновить" if alive else \
                    f"завершился (rc={proc.returncode})"
                log(f"{name}: {why}, перезапуск")
                proc.terminate()
            procs[name] = subprocess.Popen(
                ["ssh", *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
            born[name] = time.time()
            log(f"{name}: ssh поднят (pid {procs[name].pid})")
            changed = True
        if changed:
            write_status(
                children={n: p.pid for n, p in procs.items()},
                checked_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        time.sleep(CHECK_STEP)


def cmd_install():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pythonw = Path(sys.executable)
    ps = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$action = New-ScheduledTaskAction -Execute '{pythonw}' -Argument '\\"{SCRIPT}\\" daemon' -WorkingDirectory '{ROOT}'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User \\"$env:USERNAME\\"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan)
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName '{TASK_NAME}'
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        print(f"не удалось зарегистрировать задачу: {proc.stderr.strip()}")
        return 1
    log(f"задача {TASK_NAME} зарегистрирована (при входе) и запущена; демон: {pythonw}")
    print(f"задача {TASK_NAME} зарегистрирована и запущена")
    return 0


def cmd_uninstall():
    for args in (["schtasks", "/End", "/TN", TASK_NAME],
                 ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]):
        subprocess.run(args, capture_output=True, creationflags=NO_WINDOW)
    for key in ("stop", "status"):
        try:
            (ROOT / f"{TASK_NAME}.{ 'stop' if key == 'stop' else 'status.json'}").unlink()
        except FileNotFoundError:
            pass
    print(f"задача {TASK_NAME} удалена")
    return 0


def cmd_start():
    # старый демон мог оставить stop-файл — убираем до подъёма, иначе новый сразу встанет
    for p in ((ROOT / f"{TASK_NAME}.stop",)):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    subprocess.Popen(
        ["pythonw", str(SCRIPT), "daemon"] if Path(sys.executable).with_name("pythonw.exe").is_file()
        else [sys.executable, str(SCRIPT), "daemon"],
        creationflags=NO_WINDOW,
    )
    print("демон relays запущен вручную")
    return 0


def cmd_stop():
    (ROOT / f"{TASK_NAME}.stop").write_text("stop", encoding="utf-8")
    subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], capture_output=True, creationflags=NO_WINDOW)
    print("остановка запрошена")
    return 0


def cmd_status():
    status = {}
    path = ROOT / f"{TASK_NAME}.status.json"
    if path.exists():
        status = json.loads(path.read_text(encoding="utf-8"))
    alive = pid_alive(status.get("pid"))
    print(f"{TASK_NAME}: {'демон работает' if alive else 'демон не запущен'} (pid {status.get('pid')})")
    for name, pid in (status.get("children") or {}).items():
        print(f"  {name}: pid {pid} {'жив' if pid_alive(pid) else 'мёртв'}")
    print(f"  проверено: {status.get('checked_at')}")
    log_path = ROOT / f"{TASK_NAME}.log"
    if log_path.exists():
        tail = log_path.read_text(encoding="utf-8").strip().splitlines()[-5:]
        print("  лог:", " | ".join(t.split(" ", 1)[-1] for t in tail))
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    return {
        "daemon": cmd_daemon,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
    }.get(cmd, cmd_status)()


if __name__ == "__main__":
    sys.exit(main() or 0)
