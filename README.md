# pihole-toolkit

A command-line interface for managing Pi-hole v6 servers.

## Features

- View query statistics and blocking status
- See top permitted/blocked domains and top clients
- Enable/disable blocking with optional timer
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

## Configuration

Run the interactive setup:

```bash
python3 pihole_cli.py configure
```

This saves your Pi-hole host and password to `~/.config/pihole-cli/config.json` with restricted permissions.

Alternatively, use environment variables:

```bash
export PIHOLE_HOST=10.0.0.100
export PIHOLE_PASSWORD=your_password
```

Or pass credentials via CLI:

```bash
python3 pihole_cli.py --host 10.0.0.100 --password your_password stats
```

Priority: CLI flags > environment variables > config file > defaults

## Usage

### View Statistics

```bash
python3 pihole_cli.py stats
```

Output:
```
=== Pi-hole Statistics ===

Total Queries:       112,877
Queries Blocked:     19,835
Percent Blocked:     17.6%
Unique Domains:      2,564
Queries Forwarded:   6,852
Queries Cached:      85,986
Clients (active):    32
Clients (total):     32
Gravity size:        983,062
```

### View Status

```bash
python3 pihole_cli.py status
```

### Top Domains

```bash
python3 pihole_cli.py top -n 10
```

Shows top 10 permitted and blocked domains.

### Top Clients

```bash
python3 pihole_cli.py clients -n 10
```

### Enable/Disable Blocking

```bash
# Enable blocking
python3 pihole_cli.py enable

# Disable blocking indefinitely
python3 pihole_cli.py disable

# Disable for 5 minutes (300 seconds)
python3 pihole_cli.py disable -d 300
```

### Raw JSON Output

```bash
python3 pihole_cli.py json
```

### Show Configuration

```bash
python3 pihole_cli.py config
```

## Commands

| Command | Description |
|---------|-------------|
| `stats` | Show query statistics |
| `status` | Show blocking status and version |
| `top -n N` | Top N permitted and blocked domains |
| `clients -n N` | Top N clients by query count |
| `json` | Raw JSON statistics |
| `enable` | Enable blocking |
| `disable [-d SEC]` | Disable blocking (optionally for N seconds) |
| `configure` | Interactive setup |
| `config` | Show current configuration |

## License

MIT
