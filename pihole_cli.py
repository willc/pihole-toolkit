#!/usr/bin/env python3
"""Pi-hole Management CLI Tool"""

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path

import requests


CONFIG_DIR = Path.home() / ".config" / "pihole-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_HOST = "10.0.0.100"


# ── Colors ──────────────────────────────────────────────────────────

class Color:
    """ANSI color codes, disabled when output is not a terminal."""

    _enabled = sys.stdout.isatty()

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @classmethod
    def c(cls, code: str, text: str) -> str:
        if not cls._enabled:
            return text
        return f"{code}{text}{cls.RESET}"

    @classmethod
    def bold(cls, text: str) -> str:
        return cls.c(cls.BOLD, text)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.c(cls.DIM, text)

    @classmethod
    def red(cls, text: str) -> str:
        return cls.c(cls.RED, text)

    @classmethod
    def green(cls, text: str) -> str:
        return cls.c(cls.GREEN, text)

    @classmethod
    def yellow(cls, text: str) -> str:
        return cls.c(cls.YELLOW, text)

    @classmethod
    def blue(cls, text: str) -> str:
        return cls.c(cls.BLUE, text)

    @classmethod
    def cyan(cls, text: str) -> str:
        return cls.c(cls.CYAN, text)


def load_config() -> dict:
    """Load configuration from file."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict) -> None:
    """Save configuration to file with restricted permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    # Restrict file permissions to owner only (600)
    CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)


def get_config_value(key: str, cli_value: str | None, env_var: str, default: str | None = None) -> str | None:
    """Get config value with priority: CLI > env var > config file > default."""
    if cli_value:
        return cli_value
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value
    config = load_config()
    if key in config:
        return config[key]
    # Fallback: check "token" if looking for "password" (migration from v5 config)
    if key == "password" and "token" in config:
        return config["token"]
    return default


class PiholeClient:
    """Client for interacting with Pi-hole v6 API."""

    def __init__(self, host: str, password: str | None = None):
        self.host = host
        self.base_url = f"http://{host}/api"
        self.password = password
        self.session = requests.Session()
        self.sid = None

    def _authenticate(self, force: bool = False) -> bool:
        """Authenticate with Pi-hole and get session ID.

        Args:
            force: If True, get a new SID even if we have one cached.
        """
        if not self.password:
            return False
        if self.sid and not force:
            return True

        try:
            response = self.session.post(
                f"{self.base_url}/auth",
                json={"password": self.password},
                timeout=10,
            )
            data = response.json()

            if response.status_code == 429:
                hint = data.get("error", {}).get("hint", "")
                print(f"Error: API session limit reached. {hint}")
                print("Try again in a few minutes or increase max_sessions in Pi-hole settings.")
                sys.exit(1)

            response.raise_for_status()

            if data.get("session", {}).get("valid"):
                self.sid = data["session"]["sid"]
                # Clear cookies - Pi-hole doesn't like both cookie and query param
                self.session.cookies.clear()
                return True
            return False
        except requests.exceptions.RequestException:
            return False
        except json.JSONDecodeError:
            return False

    def _request(self, endpoint: str, method: str = "GET", data: dict | None = None, retry_auth: bool = True) -> dict:
        """Make a request to the Pi-hole API."""
        url = f"{self.base_url}/{endpoint}"

        # Append SID directly to URL to avoid URL encoding issues
        # (Pi-hole SIDs contain + and = which break when encoded)
        if self.password:
            if not self.sid:
                self._authenticate()
            if self.sid:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}sid={self.sid}"

        try:
            if method == "GET":
                response = self.session.get(url, timeout=10)
            elif method == "POST":
                response = self.session.post(url, json=data, timeout=10)
            elif method == "DELETE":
                response = self.session.delete(url, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Handle 401 by re-authenticating and retrying once
            if response.status_code == 401 and retry_auth and self.password:
                self.sid = None  # Clear stale session
                if self._authenticate(force=True):
                    return self._request(endpoint, method, data, retry_auth=False)

            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Pi-hole at {self.base_url}")
            sys.exit(1)
        except requests.exceptions.Timeout:
            print("Error: Connection timed out")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            error_msg = f"Error: HTTP {e.response.status_code}"
            try:
                err_data = e.response.json()
                if "error" in err_data:
                    error_msg += f" - {err_data['error'].get('message', '')}"
                    hint = err_data['error'].get('hint')
                    if hint:
                        error_msg += f" ({hint})"
            except (json.JSONDecodeError, KeyError):
                pass
            print(error_msg)
            sys.exit(1)
        except json.JSONDecodeError:
            print("Error: Invalid response from Pi-hole")
            sys.exit(1)

    def get_summary(self) -> dict:
        """Get summary statistics."""
        return self._request("stats/summary")

    def get_status(self) -> dict:
        """Get Pi-hole blocking status."""
        return self._request("dns/blocking")

    def get_version(self) -> dict:
        """Get Pi-hole version information."""
        return self._request("info/version")

    def get_top_domains(self, count: int = 10, blocked: bool = False) -> dict:
        """Get top domains.

        Args:
            count: Number of domains to return.
            blocked: If True, return blocked domains; otherwise permitted.
        """
        blocked_param = "&blocked=true" if blocked else ""
        return self._request(f"stats/top_domains?count={count}{blocked_param}")

    def get_top_clients(self, count: int = 10) -> dict:
        """Get top clients."""
        return self._request(f"stats/top_clients?count={count}")

    def update_gravity(self) -> str:
        """Trigger a gravity (blocklist) update. Returns streaming text output."""
        url = f"{self.base_url}/action/gravity"

        if self.password:
            if not self.sid:
                self._authenticate()
            if self.sid:
                url = f"{url}?sid={self.sid}"

        try:
            response = self.session.post(url, timeout=120, stream=True)

            # Handle 401 by re-authenticating
            if response.status_code == 401 and self.password:
                self.sid = None
                if self._authenticate(force=True):
                    url = f"{self.base_url}/action/gravity?sid={self.sid}"
                    response = self.session.post(url, timeout=120, stream=True)

            response.raise_for_status()
            return response.text
        except requests.exceptions.ConnectionError:
            print(f"Error: Could not connect to Pi-hole at {self.base_url}")
            sys.exit(1)
        except requests.exceptions.Timeout:
            print("Error: Gravity update timed out")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP {e.response.status_code}")
            sys.exit(1)

    def set_blocking(self, enabled: bool, duration: int | None = None) -> dict:
        """Enable or disable Pi-hole blocking.

        Args:
            enabled: True to enable blocking, False to disable.
            duration: Seconds to disable for (only used when enabled=False).
        """
        data = {"blocking": enabled}
        if not enabled and duration is not None:
            data["timer"] = duration
        return self._request("dns/blocking", method="POST", data=data)


def format_number(value: str | int) -> str:
    """Format a number with commas."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def format_percentage(value: str | float) -> str:
    """Format a percentage value."""
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return str(value)


def cmd_stats(client: PiholeClient, args):
    """Display Pi-hole statistics."""
    summary = client.get_summary()
    queries = summary.get("queries", {})

    total = queries.get("total", 0)
    blocked = queries.get("blocked", 0)
    percent = (blocked / total * 100) if total > 0 else 0

    print(f"\n{Color.bold('Pi-hole Statistics')}\n")
    print(f"  {Color.dim('Total Queries')}       {Color.bold(format_number(total))}")
    print(f"  {Color.dim('Queries Blocked')}     {Color.red(format_number(blocked))}")
    print(f"  {Color.dim('Percent Blocked')}     {Color.yellow(f'{percent:.1f}%')}")
    print(f"  {Color.dim('Unique Domains')}      {format_number(queries.get('unique_domains', 'N/A'))}")
    print(f"  {Color.dim('Queries Forwarded')}   {format_number(queries.get('forwarded', 'N/A'))}")
    print(f"  {Color.dim('Queries Cached')}      {Color.green(format_number(queries.get('cached', 'N/A')))}")
    print(f"  {Color.dim('Clients (active)')}    {format_number(summary.get('clients', {}).get('active', 'N/A'))}")
    print(f"  {Color.dim('Clients (total)')}     {format_number(summary.get('clients', {}).get('total', 'N/A'))}")
    print(f"  {Color.dim('Gravity size')}        {format_number(summary.get('gravity', {}).get('domains_being_blocked', 'N/A'))}")
    print()


def cmd_status(client: PiholeClient, args):
    """Display Pi-hole status."""
    status = client.get_status()
    version = client.get_version()

    blocking_status = status.get("blocking")
    is_enabled = blocking_status == "enabled" or blocking_status is True
    blocking_text = Color.green("ENABLED") if is_enabled else Color.red("DISABLED")
    timer = status.get("timer")

    # Extract version info from nested structure
    version_info = version.get("version", {})
    ftl_info = version_info.get("ftl", {}).get("local", {})
    core_info = version_info.get("core", {}).get("local", {})

    # Check for updates
    ftl_remote = version_info.get("ftl", {}).get("remote", {})
    core_remote = version_info.get("core", {}).get("remote", {})
    ftl_update = ftl_info.get("hash") != ftl_remote.get("hash")
    core_update = core_info.get("hash") != core_remote.get("hash")

    print(f"\n{Color.bold('Pi-hole Status')}\n")
    print(f"  {Color.dim('Blocking')}      {blocking_text}")
    if timer:
        print(f"  {Color.dim('Timer')}         {Color.yellow(f'{timer}s remaining')}")
    print(f"  {Color.dim('FTL Version')}   {ftl_info.get('version', 'N/A')}")
    print(f"  {Color.dim('Core')}          {core_info.get('version', 'N/A')}")
    print(f"  {Color.dim('Branch')}        {ftl_info.get('branch', 'N/A')}")

    if ftl_update or core_update:
        updates = []
        if ftl_update:
            updates.append(f"FTL {ftl_remote.get('version')}")
        if core_update:
            updates.append(f"Core {core_remote.get('version')}")
        print(f"\n  {Color.yellow('Updates available: ' + ', '.join(updates))}")
    print()


def cmd_top(client: PiholeClient, args):
    """Display top queries and blocked domains."""
    if not client.password:
        print("Error: Password required. Use --token option or run 'configure'.")
        sys.exit(1)

    permitted = client.get_top_domains(args.count, blocked=False)
    blocked = client.get_top_domains(args.count, blocked=True)

    print(f"\n{Color.bold(f'Top {args.count} Permitted Domains')}\n")
    for item in permitted.get("domains", [])[:args.count]:
        count = format_number(item.get('count', 0))
        domain = item.get('domain', 'unknown')
        print(f"  {Color.green(f'{count:>8}')}  {domain}")

    print(f"\n{Color.bold(f'Top {args.count} Blocked Domains')}\n")
    for item in blocked.get("domains", [])[:args.count]:
        count = format_number(item.get('count', 0))
        domain = item.get('domain', 'unknown')
        print(f"  {Color.red(f'{count:>8}')}  {domain}")
    print()


def cmd_clients(client: PiholeClient, args):
    """Display top clients."""
    if not client.password:
        print("Error: Password required. Use --token option or run 'configure'.")
        sys.exit(1)

    data = client.get_top_clients(args.count)

    print(f"\n{Color.bold(f'Top {args.count} Clients')}\n")
    for item in data.get("clients", [])[:args.count]:
        name = item.get("name") or item.get("ip", "unknown")
        count = format_number(item.get("count", 0))
        print(f"  {Color.cyan(f'{count:>8}')}  {name}")
    print()


def cmd_json(client: PiholeClient, args):
    """Output raw JSON data."""
    summary = client.get_summary()
    print(json.dumps(summary, indent=2))


def cmd_enable(client: PiholeClient, args):
    """Enable Pi-hole blocking."""
    if not client.password:
        print("Error: Password required. Use --token option or run 'configure'.")
        sys.exit(1)

    result = client.set_blocking(True)
    blocking = result.get("blocking")

    if blocking:
        print(f"\n{Color.green('Pi-hole blocking ENABLED')}")
    else:
        print(f"\nUnexpected response: {result}")
    print()


def cmd_disable(client: PiholeClient, args):
    """Disable Pi-hole blocking."""
    if not client.password:
        print("Error: Password required. Use --token option or run 'configure'.")
        sys.exit(1)

    duration = getattr(args, "duration", None)
    result = client.set_blocking(False, duration)
    blocking = result.get("blocking")

    if not blocking:
        if duration:
            minutes, seconds = divmod(duration, 60)
            if minutes > 0:
                print(f"\n{Color.red(f'Pi-hole blocking DISABLED for {minutes}m {seconds}s')}")
            else:
                print(f"\n{Color.red(f'Pi-hole blocking DISABLED for {seconds}s')}")
        else:
            print(f"\n{Color.red('Pi-hole blocking DISABLED indefinitely')}")
    else:
        print(f"\nUnexpected response: {result}")
    print()


def cmd_update(client: PiholeClient, args):
    """Check for updates and optionally update gravity."""
    if not client.password:
        print("Error: Password required. Use --token option or run 'configure'.")
        sys.exit(1)

    version = client.get_version()
    version_info = version.get("version", {})

    print(f"\n{Color.bold('Pi-hole Version Check')}\n")

    components = [
        ("FTL", "ftl"),
        ("Core", "core"),
        ("Web", "web"),
    ]

    has_update = False
    for label, key in components:
        local = version_info.get(key, {}).get("local", {})
        remote = version_info.get(key, {}).get("remote", {})
        local_ver = local.get("version", "N/A")
        remote_ver = remote.get("version", "N/A")
        needs_update = local.get("hash") != remote.get("hash")

        if needs_update:
            has_update = True
            print(f"  {Color.dim(label + ':'):14} {local_ver} -> {Color.yellow(remote_ver)}")
        else:
            print(f"  {Color.dim(label + ':'):14} {Color.green(local_ver)} {Color.dim('(up to date)')}")

    if has_update:
        print(f"\n  {Color.yellow('Updates available.')} Run 'pihole -up' on the Pi-hole to update.")

    # Gravity update
    if getattr(args, "gravity", False):
        print(f"\n{Color.bold('Updating Gravity')}\n")
        output = client.update_gravity()
        # Clean ANSI escape codes from Pi-hole output and print
        clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]|\[K', '', output)
        for line in clean.splitlines():
            line = line.strip()
            if not line:
                continue
            # Match checkmark variants (UTF-8 ✓ or mangled bytes)
            if re.match(r'\[(\u2713|â.?)\]', line):
                text = re.sub(r'^\[.\]\.?\s*', '', line)
                print(f"  {Color.green('✓')} {text}")
            # Match X/cross variants
            elif re.match(r'\[(\u2717|â.?)\]', line):
                text = re.sub(r'^\[.\]\.?\s*', '', line)
                print(f"  {Color.red('✗')} {text}")
            elif line.startswith('[i]'):
                print(f"  {Color.dim('·')} {line[4:]}")
            elif line.startswith('Sample of'):
                print(f"    {Color.dim(line)}")
            elif line.startswith('- '):
                print(f"    {Color.dim(line)}")
            else:
                print(f"  {line}")
        print(f"\n  {Color.green('Gravity update complete.')}")

    print()


def cmd_configure(client: PiholeClient, args):
    """Configure Pi-hole CLI settings."""
    config = load_config()

    print("\n=== Pi-hole CLI Configuration ===\n")
    print(f"Config file: {CONFIG_FILE}\n")
    print("Note: Pi-hole v6 uses your web interface password for API auth.\n")

    # Get host
    current_host = config.get("host", DEFAULT_HOST)
    host_input = input(f"Pi-hole host [{current_host}]: ").strip()
    if host_input:
        config["host"] = host_input
    elif "host" not in config:
        config["host"] = current_host

    # Get password
    current_password = config.get("password", "")
    password_display = "********" if current_password else "(not set)"
    password_input = input(f"Password [{password_display}]: ").strip()
    if password_input:
        config["password"] = password_input

    save_config(config)
    print(f"\nConfiguration saved to {CONFIG_FILE}")
    print("(File permissions set to owner-only for security)")
    print()


def cmd_config_show(client: PiholeClient, args):
    """Show current configuration."""
    config = load_config()

    print("\n=== Current Configuration ===\n")
    print(f"Config file: {CONFIG_FILE}")
    print(f"  Exists: {CONFIG_FILE.exists()}\n")

    # Show effective values with sources
    host = get_config_value("host", None, "PIHOLE_HOST", DEFAULT_HOST)
    password = get_config_value("password", None, "PIHOLE_PASSWORD")

    print("Effective values (CLI > env > config > default):\n")
    print(f"  Host:     {host}")
    if os.environ.get("PIHOLE_HOST"):
        print("            (from PIHOLE_HOST env var)")
    elif config.get("host"):
        print("            (from config file)")
    else:
        print("            (default)")

    if password:
        print("  Password: ********")
        if os.environ.get("PIHOLE_PASSWORD"):
            print("            (from PIHOLE_PASSWORD env var)")
        else:
            print("            (from config file)")
    else:
        print("  Password: (not set)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Pi-hole v6 Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  PIHOLE_HOST         Pi-hole host address
  PIHOLE_PASSWORD     Pi-hole web interface password

Configuration file: ~/.config/pihole-cli/config.json
  Run 'pihole_cli.py configure' to set up.

Priority: command line > environment variable > config file > default
""",
    )
    parser.add_argument(
        "--host",
        help="Pi-hole host address (default: 10.0.0.100)",
    )
    parser.add_argument(
        "--password", "--token",
        dest="password",
        help="Pi-hole web interface password",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show Pi-hole statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # status command
    status_parser = subparsers.add_parser("status", help="Show Pi-hole status")
    status_parser.set_defaults(func=cmd_status)

    # top command
    top_parser = subparsers.add_parser(
        "top", help="Show top queries and blocked domains (requires password)"
    )
    top_parser.add_argument(
        "-n", "--count", type=int, default=10, help="Number of items to show"
    )
    top_parser.set_defaults(func=cmd_top)

    # clients command
    clients_parser = subparsers.add_parser(
        "clients", help="Show top clients (requires password)"
    )
    clients_parser.add_argument(
        "-n", "--count", type=int, default=10, help="Number of clients to show"
    )
    clients_parser.set_defaults(func=cmd_clients)

    # json command
    json_parser = subparsers.add_parser("json", help="Output raw JSON statistics")
    json_parser.set_defaults(func=cmd_json)

    # enable command
    enable_parser = subparsers.add_parser(
        "enable", help="Enable Pi-hole blocking (requires password)"
    )
    enable_parser.set_defaults(func=cmd_enable)

    # disable command
    disable_parser = subparsers.add_parser(
        "disable", help="Disable Pi-hole blocking (requires password)"
    )
    disable_parser.add_argument(
        "-d",
        "--duration",
        type=int,
        metavar="SECONDS",
        help="Disable for specified seconds (default: indefinite)",
    )
    disable_parser.set_defaults(func=cmd_disable)

    # update command
    update_parser = subparsers.add_parser(
        "update", help="Check for Pi-hole updates and update gravity"
    )
    update_parser.add_argument(
        "-g", "--gravity",
        action="store_true",
        help="Also update gravity (blocklists)",
    )
    update_parser.set_defaults(func=cmd_update)

    # configure command
    configure_parser = subparsers.add_parser(
        "configure", help="Configure Pi-hole CLI settings (host, password)"
    )
    configure_parser.set_defaults(func=cmd_configure)

    # config show command
    config_show_parser = subparsers.add_parser(
        "config", help="Show current configuration"
    )
    config_show_parser.set_defaults(func=cmd_config_show)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Resolve host and password with priority: CLI > env > config > default
    host = get_config_value("host", args.host, "PIHOLE_HOST", DEFAULT_HOST)
    password = get_config_value("password", args.password, "PIHOLE_PASSWORD")

    client = PiholeClient(host, password)
    args.func(client, args)


if __name__ == "__main__":
    main()
