
# Helix plugin script for 3Scale SSO and API Key Management

This Python script automates the process of authenticating with Keycloak SSO, managing your 3Scale developer account, and generating or listing 3Scale API keys for your services. It simplifies the setup of API access by handling user authentication and interactions with the 3Scale Admin API. This command can be used as a plugin in helix

---

## Features

- **Keycloak SSO Integration**: Authenticates users via Red Hat SSO (Keycloak) using username/password or by reusing existing tokens.
- **3Scale Account Management**: Automatically finds or creates a 3Scale developer account based on the authenticated SOEID (Keycloak username) and email.
- **Service Listing**: Lists all available 3Scale services (models) and indicates which ones your account already has an API key for, including their proxy endpoints and authentication methods.
- **API Key Initialization**: Generates a new API key for a specified service, or returns an existing one if available.
- **Persistent Configuration**: Stores Keycloak tokens in a hidden `.ini` file in your home directory (`~/.threescale_sso_config.ini`) to minimize re-authentication prompts.

---

## Prerequisites

Before running the script, ensure you have the following:

- **Python 3.9.18 or higher**  
  (Tested with Python 3.9.18+)

- **Required Python Libraries**  
  Installed via `pip`:
  - `requests`
  - `pyjwt`
  - `lxml` (optional, but commonly used for robustness)

- **Environment Variables**  
  Critical API URLs and keys must be set as environment variables.

---

## Setup and Installation

### 1. Download the Script and Dependencies

Save the provided Python script as `mlaas.py`.  
Create a `requirements.txt` file in the same directory:

```
requests>=2.25.1  
pyjwt>=2.0.0
```

### 2. Recommended: Create a Python Virtual Environment

```bash
python -m venv venv

# On Windows:
.env\Scriptsctivate

# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## Set Environment Variables

Replace the placeholder values with your actual Keycloak and 3Scale details.

- `KEYCLOAK_URL`: e.g., `https://your-keycloak-instance.com`
- `KEYCLOAK_REALM`: e.g., `your_realm_name`
- `KEYCLOAK_CLIENT_ID`: e.g., `your_client_id_for_this_app`
- `KEYCLOAK_CLIENT_SECRET`: e.g., `your_client_password_for_this_app`
- `THREESCALE_ADMIN_API_URL`: e.g., `https://your-admin-portal.3scale.net/admin/api/`
- `THREESCALE_ADMIN_API_KEY`: Your 3Scale Admin Portal API Key

### Windows (Command Prompt)

```cmd
set KEYCLOAK_URL=https://your-keycloak-instance.com
set KEYCLOAK_REALM=your_realm_name
set KEYCLOAK_CLIENT_ID=your_client_id_for_this_app
set THREESCALE_ADMIN_API_URL=https://your-admin-portal.3scale.net/admin/api/
set THREESCALE_ADMIN_API_KEY=Your3scaleAdminAPIKey
set KEYCLOAK_CLIENT_SECRET=YourClientSecret
```

### Windows (PowerShell)

```powershell
$env:KEYCLOAK_URL="https://your-keycloak-instance.com"
$env:KEYCLOAK_REALM="your_realm_name"
$env:KEYCLOAK_CLIENT_ID="your_client_id_for_this_app"
$env:THREESCALE_ADMIN_API_URL="https://your-admin-portal.3scale.net/admin/api/"
$env:THREESCALE_ADMIN_API_KEY="Your3scaleAdminAPIKey"
# Optional:
$env:KEYCLOAK_CLIENT_SECRET="YourClientSecret"
```

### macOS / Linux (Bash/Zsh)

```bash
export KEYCLOAK_URL="https://your-keycloak-instance.com"
export KEYCLOAK_REALM="your_realm_name"
export KEYCLOAK_CLIENT_ID="your_client_id_for_this_app"
export THREESCALE_ADMIN_API_URL="https://your-admin-portal.3scale.net/admin/api/"
export THREESCALE_ADMIN_API_KEY="Your3scaleAdminAPIKey"
# Optional:
export KEYCLOAK_CLIENT_SECRET="YourClientSecret"
```

To make these persistent, add them to your shell profile (e.g., `~/.bashrc`, `~/.zshrc`) and run:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

---

## Usage

Navigate to the directory where `mlaas.py` is located.

### Running Without Arguments (Shows Help)

```bash
python mlaas.py
# OR if using PyInstaller executable:
./mlaas       # On Linux/macOS
mlaas.exe     # On Windows
```

---

### Listing Services and API Key Status

```bash
python mlaas.py --list
```

---

### Initializing an API Key for a Service

#### By Service Name:

```bash
python mlaas.py --init name="Your Service Name"
```

#### By Service ID:

```bash
python mlaas.py --init id="123456"
```

---

### Interactive Flow (No Arguments)

If you run the script without `--list` or `--init`, it will:

1. Attempt Keycloak authentication.
2. Find or create your 3Scale account.
3. List all available services with their proxy URLs and authentication methods.
4. Prompt you to select a service by number.
5. Proceed to generate or retrieve your API key.

---

## Packaging as a Standalone Executable

Use **PyInstaller** to build a platform-specific executable.

### 1. Install PyInstaller

```bash
pip install pyinstaller
```

### 2. Build the Executable

```bash
pyinstaller --onefile --name mlaas mlaas.py
```

### 3. Locate the Executable

- **Windows**: `dist\mlaas.exe`
- **macOS / Linux**: `dist/mlaas`

---

## Configuration File

The script saves Keycloak token information in:

- **Linux/macOS**: `~/.threescale_sso_config.ini`
- **Windows**: `C:\Users\<YourUsername>\.threescale_sso_config.ini`

This helps reduce the need to re-authenticate frequently by reusing stored tokens.
