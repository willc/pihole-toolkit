# pihole-toolkit

A command-line interface for managing Pi-hole v6 servers from your local computer.

## Features

- Colorized terminal output (auto-disabled when piped)
- View query statistics and blocking status
- See top permitted/blocked domains and top clients
- Enable/disable blocking with optional timer
- Check for Pi-hole updates and refresh gravity (blocklists)
- Configuration via file, environment variables, or CLI flags

## Requirements

- Python 3.10+
- Pi-hole v6

## Installation

```bash
git clone https://github.com/willc/pihole-toolkit.git
cd pihole-toolkit
pip install -r requirements.txt
```

Optionally add an alias to your shell profile:

```bash
echo "alias pihole='python3 $(pwd)/pihole_cli.py'" >> ~/.zshrc
```

## Configuration

Run the interactive setup:

```bash
pihole configure
```

This saves your Pi-hole host and password to `~/.config/pihole-cli/config.json` with restricted permissions (owner-only).

Alternatively, use environment variables:

```bash
export PIHOLE_HOST=10.0.0.100
export PIHOLE_PASSWORD=your_password
```

Or pass credentials via CLI:

```bash
pihole --host 10.0.0.100 --password your_password stats
```

Priority: CLI flags > environment variables > config file > defaults

## Usage

### View Statistics

```bash
pihole stats
```

```
Pi-hole Statistics

  Total Queries       112,877
  Queries Blocked     19,835
  Percent Blocked     17.6%
  Unique Domains      2,564
  Queries Forwarded   6,852
  Queries Cached      85,986
  Clients (active)    32
  Clients (total)     32
  Gravity size        983,062
```

### View Status

```bash
pihole status
```

Shows blocking state, Pi-hole version, and whether updates are available.

### Top Domains

```bash
pihole top -n 10
```

Shows top 10 permitted and blocked domains.

### Top Clients

```bash
pihole clients -n 10
```

### Enable/Disable Blocking

```bash
pihole enable
pihole disable
pihole disable -d 300    # Disable for 5 minutes
```

### Check for Updates

```bash
pihole update            # Check FTL, Core, and Web versions
pihole update -g         # Also refresh gravity (blocklists)
```

### Raw JSON Output

```bash
pihole json
```

### Show Configuration

```bash
pihole config
```

## Commands

| Command | Description |
|---------|-------------|
| `stats` | Show query statistics |
| `status` | Show blocking status, version, and update availability |
| `top -n N` | Top N permitted and blocked domains |
| `clients -n N` | Top N clients by query count |
| `update` | Check for Pi-hole updates |
| `update -g` | Check for updates and refresh gravity |
| `json` | Raw JSON statistics |
| `enable` | Enable blocking |
| `disable [-d SEC]` | Disable blocking (optionally for N seconds) |
| `configure` | Interactive setup |
| `config` | Show current configuration |

## License

MIT
