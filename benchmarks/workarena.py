import random
import os
import socket
import sys
import traceback

from browsergym.core.env import BrowserEnv
from browsergym.workarena import ATOMIC_TASKS
from time import sleep


def _supports_socket_shutdown() -> bool:
    s1, s2 = socket.socketpair()
    try:
        s1.shutdown(socket.SHUT_RDWR)
        return True
    except OSError:
        return False
    finally:
        s1.close()
        s2.close()


def _parse_bool_env(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


headless_env = os.environ.get("BROWSERGYM_HEADLESS")
if headless_env is None:
    headless = not bool(os.environ.get("DISPLAY"))
else:
    headless = _parse_bool_env(headless_env)

if not headless and not os.environ.get("DISPLAY"):
    print(
        "Cannot run with headless=False because DISPLAY is not set. "
        "Set BROWSERGYM_HEADLESS=1 or start an X server.",
        file=sys.stderr,
    )
    raise SystemExit(2)

if not _supports_socket_shutdown():
    print(
        "Playwright browsers cannot start in this environment because socket.shutdown() "
        "is blocked (Operation not permitted). Run on a less restricted host/container "
        "(e.g., without a seccomp profile blocking shutdown(2)).",
        file=sys.stderr,
    )
    raise SystemExit(2)


seed_env = os.environ.get("BROWSERGYM_SEED")
seed = int(seed_env) if seed_env is not None else None
if seed is not None:
    random.seed(seed)

# Reuse a single ServiceNow instance across tasks when possible so we don't mix instances mid-run.
task_kwargs = {}
try:
    from browsergym.workarena.instance import SNowInstance

    instance = SNowInstance()
    task_kwargs["instance"] = instance
    print(f"Using ServiceNow instance: {instance.snow_url}")
except Exception as e:
    print(
        f"WARNING: Could not create a shared ServiceNow instance ({e}). "
        "Each task will pick its own instance.",
        file=sys.stderr,
    )

tasks = list(ATOMIC_TASKS)
random.shuffle(tasks)

max_tasks_env = os.environ.get("BROWSERGYM_MAX_TASKS")
max_tasks = int(max_tasks_env) if max_tasks_env else None
if max_tasks is not None:
    tasks = tasks[:max_tasks]

print("Running tasks:", tasks)
for i, task in enumerate(tasks):
    print("Task:", task)

    # Instantiate a new environment
    env = None
    try:
        env = BrowserEnv(
            task_entrypoint=task,
            task_kwargs=task_kwargs,
            headless=headless,
        )
        reset_seed = seed + i if seed is not None else None
        obs, info = env.reset(seed=reset_seed)
        # print(f"Task obs: {obs}, info: {info}")
        # save the obs and info for debugging
        with open(f"try_obs_{task}.txt", "w") as f:
            f.write(f"obs: {obs}\n")
            f.write(f"info: {info}\n")



        # Cheat functions use Playwright to automatically solve the task
        env.chat.add_message(role="assistant", msg="On it. Please wait...")
        cheat_messages = []
        env.task.cheat(env.page, cheat_messages)

        # Send cheat messages to chat
        for cheat_msg in cheat_messages:
            env.chat.add_message(role=cheat_msg["role"], msg=cheat_msg["message"])

        # Post solution to chat
        env.chat.add_message(role="assistant", msg="I'm done!")

        # Validate the solution
        reward, stop, message, info = env.task.validate(env.page, cheat_messages)
        if reward == 1:
            env.chat.add_message(role="user", msg="Yes, that works. Thanks!")
        else:
            env.chat.add_message(role="user", msg=f"No, that doesn't work. {info.get('message', '')}")

        sleep(3)
    except Exception:
        print(f"ERROR while running {task}:", file=sys.stderr)
        traceback.print_exc()
        if env is not None and getattr(env, "task", None) is not None:
            task_obj = env.task
            instance_obj = getattr(task_obj, "instance", None)
            if instance_obj is not None and hasattr(instance_obj, "snow_url"):
                print(f"Instance URL: {instance_obj.snow_url}", file=sys.stderr)
            if hasattr(task_obj, "start_url"):
                print(f"Start URL: {getattr(task_obj, 'start_url')}", file=sys.stderr)
            if hasattr(task_obj, "config"):
                print(f"Config: {getattr(task_obj, 'config')}", file=sys.stderr)
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
