# CPE Guesser

CPE Guesser is a command-line tool or web service designed to guess the CPE (Common Platform Enumeration) name based on one or more keywords. The resulting CPE can then be used with tools like [cve-search](https://github.com/cve-search/cve-search) or [vulnerability-lookup](https://github.com/cve-search/vulnerability-lookup) to perform actual searches using CPE names.

## Requirements

- [Valkey](https://valkey.io/) (Redis-compatible)
- Python >= 3.13

## Installation

### Using uv

```bash
uv tool install git+https://github.com/cve-search/cpe-guesser.git
```

### Using pip

```bash
pip install git+https://github.com/cve-search/cpe-guesser.git
```

## Configuration

Default configuration:
- Valkey: `127.0.0.1:6379` database 8
- API server port: 8000
- Download path: `./data/`

If you need a custom configuration, copy the [settings file](./config/config.yaml) to one of the default's search locations
or use `--config` switch.

## Usage

### Quick Start

For this to work you will need to have a running Redis protocol compatible database running on the address and port
configured in **configuration file**.

1. **Initialize the database** with CPE dictionary:
   ```bash
   # This will used a cached version of the file if it exists or download it otherwise
   cpe-import --cached -f nvd-json https://nvd.nist.gov/feeds/json/cpe/2.0/nvdcpe-2.0.tar.gz
   ```

2. **Query via CLI**:
   ```bash
   cpe-lookup tomcat
   # query with keywords
   cpe-lookup --unique microsoft sql server
   # query by vendor and product
   cpe-lookup -v microsoft -p outlook --limit 5
   ```

3. **Start the web server**:
   ```bash
   cpe-server
   ```

### CLI Tools

| Command | Description |
|---------|-------------|
| `cpe-import` | Import CPE data from NVD JSON, newline-delimited CPE, or any text |
| `cpe-extract` | Extract CPE strings from arbitrary text files using regex |
| `cpe-lookup` | Query CPE database from command line |
| `cpe-server` | Start HTTP API server |

#### cpe-import

Imports CPE data into the database

```bash
# Download and import NVD JSON feed
cpe-import --cached -f nvd-json https://nvd.nist.gov/feeds/json/cpe/2.0/nvdcpe-2.0.tar.gz

# Import from local file
cpe-import -f nvd-json ./data/nvdcpe-2.0.json

# Import newline-delimited CPE strings
cpe-import -f nd-cpe one_cpe_per_line.txt

# Import from any text file (auto-detects CPE strings)
cpe-import -f any-text arbitrary_text.txt

# Replace existing database
cpe-import --cached -f nvd-json https://nvd.nist.gov/feeds/json/cpe/2.0/nvdcpe-2.0.tar.gz
```

#### cpe-extract

Extract CPE 2.3 strings from any text input:

```bash
# From a file
cpe-extract arbitrary_text.txt

# From stdin
curl -s https://vulnerability.circl.lu/dumps/cvelistv5.ndjson | cpe-extract -
```

#### cpe-lookup

Query the database and return results in json. This is perfect to query a local instance.

```bash
# Basic search
cpe-lookup tomcat

# Multiple keywords
cpe-lookup microsoft sql server

# Get only the best match
cpe-lookup --unique tomcat

# Filter by vendor
cpe-lookup -v microsoft -p outlook

# Limit results
cpe-lookup --limit 5 nginx

# Show all results
cpe-lookup --all nginx
```

#### cpe-server

Start the HTTP API server, using parameters defined in **configuration file**:

```bash
cpe-server
```

## HTTP API

The web server provides two API versions:

### v2 API (Recommended)

#### POST /v2/search

Search for CPEs matching keywords.

**Request:**
```json
{
  "query": ["some arbitrary text that will be tokenized", "some other text or keywords"],
  "vendor": "apache",
  "product": "tomcat",
  "limit": 10
}
```

**Response:**
```json
[
  [
    32,
    "cpe:2.3:a:apache:apache"
  ],
  [
    32,
    "cpe:2.3:a:apache:tomcat"
  ]
]
```

### v1 API (Legacy)

#### POST /v1/search

Legacy search endpoint with basic keyword matching. 

**Request:**
```json
{
  "query": ["tomcat"],
  "limit": 5
}
```

**Response:** Same format as v2/search.


### API Usage

```bash
# Search
curl -s -X POST http://localhost:8000/v2/search \
  -d '{"query": ["openssl", "encrypt"]}' | jq .

# Unique match
curl -s -X POST http://localhost:8000/v2/search \
  -d '{"query": ["debian", "linux"], "limit": 1}' | jq .

# Match from arbitrary text
curl -s -X POST http://localhost:8000/v2/search \
  -d '{"query": ["A severe vulnerability has been found on Debian Linux"]}' | jq .

# Search by vendor
curl -s -X POST http://localhost:8000/v2/search \
  -d '{"vendor": "debian"}' | jq .
  
# Search by product
curl -s -X POST http://localhost:8000/v2/search \
  -d '{"product": "cron"}' | jq .

# Search by vendor and product
curl -s -X POST http://localhost:8000/v2/search \
    -d '{"vendor":"debian", "product": "cron"}' | jq .

# Search by vendor / product and arbitrary text
curl -s -X POST http://localhost:8000/v2/search \
    -d '{"vendor":"debian", "query": ["A vulnerability has been found in cron"]}' | jq .
```

## Containers

### Docker Compose

```bash
docker-compose up --build -d
# Wait for import to complete
```

### Podman Compose

```bash
podman-compose up --build -d
# Wait for import to complete
```

## License

Software is open source and released under a 2-Clause BSD License.

```
Copyright (C) 2021-2025 Alexandre Dulaunoy
Copyright (C) 2021-2025 Esa Jokinen
```

We welcome contributions! All contributors collectively own the CPE Guesser project. By contributing, contributors also acknowledge the [Developer Certificate of Origin](https://developercertificate.org/) when submitting pull requests or using other methods of contribution.
