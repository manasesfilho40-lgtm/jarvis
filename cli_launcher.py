#!/usr/bin/env python3
"""
J.A.R.V.I.S Plugin CLI Launcher
Test any plugin interactively from the terminal.
Usage: python cli_launcher.py [plugin_name] [method] [args...]
"""

import asyncio
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


async def main():
    from core.startup import load_plugins, get_plugin_manager

    print("J.A.R.V.I.S Plugin CLI Launcher")
    print("=" * 50)
    await load_plugins()
    pm = get_plugin_manager()

    if len(sys.argv) > 1:
        return await run_direct(pm)

    print(f"\n{pm.plugin_count} plugins loaded.\n")
    print("Interactive mode. Type 'help' for commands.")
    print()

    while True:
        try:
            cmd = input("plugins> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            print("Goodbye.")
            break
        if cmd == "help":
            show_help()
        elif cmd == "list":
            show_plugins(pm)
        elif cmd.startswith("call "):
            await call_plugin(pm, cmd[5:])
        elif cmd.startswith("info "):
            show_plugin_info(pm, cmd[5:])
        else:
            print(f"Unknown command: {cmd}")


async def run_direct(pm):
    if len(sys.argv) < 3:
        print("Usage: python cli_launcher.py <plugin_name> <method> [args...]")
        return
    plugin_name = sys.argv[1]
    method_name = sys.argv[2]
    args = {}
    for arg in sys.argv[3:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            args[k] = v
    plugin = pm.get_plugin(plugin_name)
    if not plugin:
        print(f"Plugin '{plugin_name}' not found.")
        available = [p.manifest.name for p in pm.get_all_plugins()]
        print(f"Available: {', '.join(sorted(available))}")
        return
    method = getattr(plugin, method_name, None)
    if not method:
        print(f"Plugin '{plugin_name}' has no method '{method_name}'.")
        methods = [m for m in dir(plugin) if not m.startswith("_")]
        print(f"Available methods: {', '.join(sorted(methods))}")
        return
    if asyncio.iscoroutinefunction(method):
        result = await method(**args)
    else:
        result = method(**args)
    print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else result)


def show_plugins(pm):
    print(f"\n{'Name':<20} {'Version':<10} {'Status':<10} {'Hooks'}")
    print("-" * 60)
    for p in sorted(pm.get_all_plugins(), key=lambda x: x.manifest.name):
        status = "ENABLED" if p.enabled else "DISABLED"
        hooks = ", ".join(h.value for h in p._hooks) if p._hooks else ""
        print(f"{p.manifest.name:<20} {p.manifest.version:<10} {status:<10} {hooks}")
    print()


def show_plugin_info(pm, name):
    plugin = pm.get_plugin(name)
    if not plugin:
        print(f"Plugin '{name}' not found.")
        return
    print(f"\nName:        {plugin.manifest.name}")
    print(f"Version:     {plugin.manifest.version}")
    print(f"Description: {plugin.manifest.description}")
    print(f"Author:      {plugin.manifest.author or 'N/A'}")
    print(f"Status:      {'ENABLED' if plugin.enabled else 'DISABLED'}")
    print(f"Config:      {json.dumps(plugin.config, ensure_ascii=False, indent=2) if plugin.config else '(empty)'}")
    print(f"\nMethods:")
    for m in sorted(dir(plugin)):
        if not m.startswith("_") and callable(getattr(plugin, m)):
            print(f"  {m}")
    print()


async def call_plugin(pm, cmd):
    parts = shlex.split(cmd)
    if len(parts) < 2:
        print("Usage: call <plugin> <method> [key=value ...]")
        return
    plugin_name = parts[0]
    method_name = parts[1]
    args = {}
    for arg in parts[2:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            args[k] = v
    plugin = pm.get_plugin(plugin_name)
    if not plugin:
        print(f"Plugin '{plugin_name}' not found.")
        return
    method = getattr(plugin, method_name, None)
    if not method:
        print(f"No method '{method_name}' on plugin '{plugin_name}'.")
        return
    try:
        if asyncio.iscoroutinefunction(method):
            result = await method(**args)
        else:
            result = method(**args)
        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else result)
    except Exception as e:
        print(f"Error: {e}")


def show_help():
    print("""
Commands:
  help                    Show this help
  list                    List all loaded plugins
  info <plugin>           Show plugin details and methods
  call <p> <m> [k=v...]  Call plugin method with args
  exit, quit              Exit

Examples:
  call translator translate text="Hello" target_lang=pt
  call cli execute_command command=help
  call system_monitor get_system_info
  call weather get_coordinates city="Sao Paulo"
""")


if __name__ == "__main__":
    asyncio.run(main())