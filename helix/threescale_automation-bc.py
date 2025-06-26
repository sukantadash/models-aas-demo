import os
import requests
import getpass
import json
import jwt # Required for decoding JWTs
import datetime # Required for checking token expiration
import subprocess # Required for running 'whoami'
import xml.etree.ElementTree as ET
import argparse # New: for command-line argument parsing

# --- Configuration File Path ---
# Store the config file in the user's home directory for persistence
CONFIG_DIR = os.path.expanduser("~")
CONFIG_FILE_NAME = ".threescale_sso_config"
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)

# --- Logging Helper ---
def log_message(message: str, is_verbose: bool = False, is_error: bool = False):
    """
    Prints a message to the console.
    If is_verbose is True, prints only if the global verbose flag is set.
    Error messages are always printed.
    """
    global_verbose_flag = False # Default to False, updated in main()
    try:
        # Access args.verbose if main has started and args are parsed
        if 'args' in globals() and args.verbose:
            global_verbose_flag = True
    except NameError:
        pass # args not yet defined, stick to default

    if is_error or (is_verbose and global_verbose_flag) or (not is_verbose and not is_error):
        # Always print non-verbose messages, or verbose messages if flag is on, or error messages
        print(message)

# --- Centralized Helper Functions ---

def save_sso_token(token_data: dict, verbose: bool = False):
    """Saves the Keycloak token data to a hidden configuration file."""
    try:
        with open(CONFIG_FILE_PATH, 'w') as f:
            json.dump(token_data, f)
        log_message(f"Keycloak token data saved to {CONFIG_FILE_PATH}", is_verbose=True)
    except IOError as e:
        log_message(f"Error saving Keycloak token data to file: {e}", is_error=True)

def load_sso_token(verbose: bool = False) -> dict:
    """Loads Keycloak token data from the hidden configuration file."""
    if not os.path.exists(CONFIG_FILE_PATH):
        return {} # Return empty if file doesn't exist
    
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            token_data = json.load(f)
        log_message(f"Keycloak token data loaded from {CONFIG_FILE_PATH}", is_verbose=True)
        return token_data
    except (IOError, json.JSONDecodeError) as e:
        log_message(f"Error loading Keycloak token data from file: {e}", is_error=True)
        # Optionally, delete corrupted file
        # os.remove(CONFIG_FILE_PATH)
        return {}

def get_env_variable(var_name: str, optional: bool = False) -> str:
    """
    Retrieves an environment variable.
    Exits if the variable is not set and is not optional.
    """
    value = os.getenv(var_name)
    if value is None and not optional:
        log_message(f"Error: Environment variable '{var_name}' is not set.", is_error=True)
        if var_name == "KEYCLOAK_URL": # Only print full instructions for the first critical missing var
            log_message("Please set the following environment variables before running:", is_error=True)
            log_message("  KEYCLOAK_URL          (e.g., https://your-keycloak-instance.com)", is_error=True)
            log_message("  KEYCLOAK_REALM        (e.g., your_realm_name)", is_error=True)
            log_message("  KEYCLOAK_CLIENT_ID    (e.g., your_client_id_for_this_app)", is_error=True)
            log_message("  KEYCLOAK_CLIENT_SECRET (Optional, if your client is confidential)", is_error=True)
            log_message("  THREESCALE_ADMIN_API_URL (e.g., https://your-admin-portal.3scale.net/admin/api/)", is_error=True)
            log_message("  THREESCALE_ADMIN_API_KEY (Your 3scale Admin Portal API Key)", is_error=True)
            log_message("\nNote: GENERATED_API_KEY will be automatically set after successful operations.", is_error=True)
        exit(1)
    return value

def make_api_call(method: str, endpoint: str, params: dict = None, data: dict = None, headers: dict = None, is_threescale_admin_api: bool = True, is_json_response: bool = False, verbose: bool = False) -> [ET.Element, dict]:
    """
    Makes an API call.
    Handles common response parsing and error checking.
    Returns XML root element for 3Scale Admin API (default), or JSON dict if is_json_response is True.
    Prints API input (params, data, headers) and raw API output for debugging if verbose is True.
    """
    base_url = ""
    if is_threescale_admin_api:
        base_url = get_env_variable("THREESCALE_ADMIN_API_URL")
        if not base_url.endswith('/'):
            base_url += '/'
    
    url = f"{base_url}{endpoint}" if is_threescale_admin_api else endpoint

    if verbose:
        log_message(f"\n--- Making {method} request to: {url} ---", is_verbose=True)
        log_message(f"API Input - Params: {params}", is_verbose=True)
        log_message(f"API Input - Data: {data}", is_verbose=True)
        log_message(f"API Input - Headers: {headers}", is_verbose=True)

    try:
        response = requests.request(method, url, params=params, data=data, headers=headers)
        response.raise_for_status()

        if verbose:
            log_message(f"Response Status Code: {response.status_code}", is_verbose=True)
            log_message(f"Raw API Output: {response.text}", is_verbose=True) # Print raw output for debugging

        if is_json_response:
            return response.json()
        elif is_threescale_admin_api:
            # 3scale Admin API often returns XML
            return ET.fromstring(response.text)
        else:
            # Default to JSON if not explicitly XML or other 3scale admin API
            return response.json()

    except requests.exceptions.HTTPError as e:
        log_message(f"HTTP Error occurred: {e}", is_error=True)
        if verbose:
            log_message(f"Raw API Output (Error): {response.text}", is_verbose=True) # Also print raw output on error
        try:
            # Attempt to parse as JSON first for common error formats
            error_details = response.json()
            log_message("Error Details (JSON):", is_error=True)
            log_message(json.dumps(error_details, indent=2), is_error=True)
        except json.JSONDecodeError:
            # If not JSON, print raw text for XML errors etc.
            log_message(f"Could not decode error response (non-JSON): {response.text}", is_error=True)
        return None
    except requests.exceptions.ConnectionError as e:
        log_message(f"Connection Error occurred: {e}", is_error=True)
        return None
    except requests.exceptions.Timeout as e:
        log_message(f"Timeout Error occurred: {e}", is_error=True)
        return None
    except requests.exceptions.RequestException as e:
        log_message(f"An unexpected Request Error occurred: {e}", is_error=True)
        return None
    except ET.ParseError as e:
        log_message(f"Error parsing XML response: {e}", is_error=True)
        log_message(f"Raw response text: {response.text}", is_error=True)
        return None
    except json.JSONDecodeError as e:
        log_message(f"Error parsing JSON response: {e}", is_error=True)
        log_message(f"Raw response text: {response.text}", is_error=True)
        return None


def get_current_system_username() -> str:
    """
    Attempts to get the current system username using 'whoami' command.
    Returns an empty string if command fails.
    """
    try:
        result = subprocess.run(["whoami"], capture_output=True, text=True, check=True, timeout=5)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        log_message(f"Warning: Could not get system username via 'whoami': {e}. Defaulting to empty string.", is_verbose=True)
        return ""

def sso_login_and_get_credentials(keycloak_url: str, keycloak_realm: str, keycloak_client_id: str, keycloak_client_secret: str, verbose: bool = False) -> tuple[str, str, str, str]:
    """
    Performs SSO login, manages the access token.
    Retrieves email and SOEID from Keycloak access token if possible.
    If reauthentication is needed, prompts for SOEID and password.
    Returns (keycloak_access_token, soeid, password, emailid).
    Password will be None if token is reused.
    """
    access_token = None
    email_id = None
    soeid = None
    password = None # This will remain None if token is reused and no new login occurs

    # --- Attempt to reuse existing token from file ---
    token_data_from_file = load_sso_token(verbose)
    current_access_token = token_data_from_file.get('access_token')

    if current_access_token:
        log_message("\nFound existing KEYCLOAK_ACCESS_TOKEN in config file. Attempting to validate and reuse...", is_verbose=True)
        try:
            decoded_token = jwt.decode(current_access_token, options={"verify_signature": False})
            expiration_timestamp = decoded_token.get('exp')
            email_id_from_token = decoded_token.get('email')
            soeid_from_token = decoded_token.get('preferred_username') or decoded_token.get('sub') # Common Keycloak claims for username/soeid

            current_time_utc_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()

            # Check if token is valid, has email and SOEID claims, and is not near expiration
            if expiration_timestamp and email_id_from_token and soeid_from_token and \
               expiration_timestamp > current_time_utc_timestamp + 60: # 60-second buffer
                
                access_token = current_access_token
                email_id = email_id_from_token
                soeid = soeid_from_token
                log_message("Existing token is valid, has required claims, and not expired. Reusing token.", is_verbose=True)
                log_message(f"Inferred SOEID from token: {soeid}", is_verbose=True)
                log_message(f"Inferred Email from token: {email_id}", is_verbose=True)
                # No password needed for this path, so it remains None
                return access_token, soeid, password, email_id
            else:
                log_message("Existing token is expired, missing required claims (email/SOEID), or close to expiration. Will re-authenticate.", is_verbose=True)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception) as e:
            log_message(f"Error validating existing token: {e}. Will re-authenticate.", is_verbose=True)
    else:
        log_message("\nNo valid KEYCLOAK_ACCESS_TOKEN found in config file. Will perform a new login.", is_verbose=True)

    # --- If we reach here, we need to perform a new authentication ---

    # Prompt for SOEID (which is also the Keycloak username)
    default_soeid = get_current_system_username()
    soeid_prompt = f"Enter your SOEID (which is also your Red Hat SSO Username) (default: {default_soeid}): " if default_soeid else "Enter your SOEID (which is also your Red Hat SSO Username): "
    soeid = input(soeid_prompt) # Always prompt for user input
    if not soeid and default_soeid:
        soeid = default_soeid
        log_message(f"Using default SOEID: {soeid}") # This is an essential informational message

    if not soeid:
        log_message("SOEID is required to proceed. Exiting.", is_error=True)
        return None, None, None, None

    password = getpass.getpass(f"Enter your Red Hat SSO Password for user '{soeid}': ") # Always prompt for user input

    token_url = f"{keycloak_url}/realms/{keycloak_realm}/protocol/openid-connect/token"
    if verbose:
        log_message(f"\nAttempting to connect to Keycloak at: {token_url}", is_verbose=True)
        log_message(f"Using Keycloak Client ID: {keycloak_client_id}", is_verbose=True)

    payload = {
        "grant_type": "password",
        "client_id": keycloak_client_id,
        "username": soeid, # Use SOEID as username for Keycloak login
        "password": password,
        "scope": "openid profile email" # Requesting email scope
    }
    if keycloak_client_secret:
        payload["client_secret"] = keycloak_client_secret

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_data = make_api_call("POST", token_url, data=payload, headers=headers, is_threescale_admin_api=False, is_json_response=True, verbose=verbose)
    if token_data:
        access_token = token_data.get('access_token')
        if access_token:
            # Decode new token to get email
            try:
                decoded_token = jwt.decode(access_token, options={"verify_signature": False})
                email_id = decoded_token.get('email')
                if not email_id:
                    log_message("Warning: Email claim not found in the new Keycloak access token.", is_verbose=True)
            except (jwt.InvalidTokenError, Exception) as e:
                log_message(f"Error decoding new Keycloak token to get email: {e}", is_verbose=True)

            # Store the entire token_data (including refresh_token, etc.) to file
            save_sso_token(token_data, verbose)

            log_message("\n--- Keycloak Login Successful! ---", is_verbose=True)
            log_message(f"Access Token (Bearer): {access_token[:30]}... (truncated)", is_verbose=True)
            log_message(f"Expires In (seconds): {token_data.get('expires_in')}", is_verbose=True)
            if email_id:
                log_message(f"Associated Email ID: {email_id}", is_verbose=True)
        else:
            log_message("Login successful, but no access_token found in response.", is_verbose=True)
            return None, soeid, password, None # Return None for email if not found
    else:
        log_message("Failed to obtain access token from Keycloak.", is_error=True)
        return None, soeid, password, None # Return None for email if not found

    return access_token, soeid, password, email_id # Return password collected here

def find_account_by_soeid(soeid: str, threescale_admin_api_key: str, verbose: bool = False) -> str:
    """
    Checks if an SOEID exists in 3Scale by finding the account.
    Returns account ID if found, otherwise None.
    """
    log_message(f"\nChecking if SOEID '{soeid}' exists in 3Scale...", is_verbose=True)
    endpoint = "accounts/find.xml"
    params = {
        "access_token": threescale_admin_api_key, # Use 3scale Admin API Key here
        "username": soeid
    }
    
    root = make_api_call("GET", endpoint, params=params, verbose=verbose)

    if root is not None:
        account_id_element = root.find("id")
        if account_id_element is not None:
            account_id = account_id_element.text
            log_message(f"Account found! Account ID: {account_id}", is_verbose=True)
            return account_id
        else:
            log_message("Account not found for the given SOEID.", is_verbose=True)
            return None
    return None

def create_threescale_account_via_signup(soeid: str, emailid: str, password: str, threescale_admin_api_key: str, verbose: bool = False) -> str:
    """
    Creates a new 3Scale developer account using the signup API.
    Returns the new account's ID if successful.
    """
    log_message(f"\nAttempting to create new 3scale account for SOEID '{soeid}'...", is_verbose=True)
    signup_endpoint = "signup.xml" # Relative to THREESCALE_ADMIN_API_URL

    payload = {
        "access_token": threescale_admin_api_key,
        "username": soeid,
        "email": emailid,
        "org_name": emailid, # As per requirement: org_name as emailid
        "password": password,
        # Optional parameters as per your curl example:
        # "account_plan_id": "", 
        # "service_plan_id": "",
        # "application_plan_id": ""
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml" # 3scale signup.xml often expects/returns XML
    }

    # make_api_call is configured to return XML root by default for 3scale_admin_api
    root = make_api_call("POST", signup_endpoint, data=payload, headers=headers, is_threescale_admin_api=True, verbose=verbose)

    if root is not None:
        # The signup API might return the created account's details
        account_element = root.find("account")
        if account_element is not None:
            account_id_element = account_element.find("id")
            if account_id_element is not None:
                new_account_id = account_id_element.text
                log_message(f"Successfully created 3scale account! New Account ID: {new_account_id}")
                return new_account_id
            else:
                log_message("Could not find account ID in signup response.", is_verbose=True)
        else:
            log_message("Could not find 'account' element in signup response.", is_verbose=True)
    log_message("Failed to create 3scale account.", is_error=True)
    return None


def list_services(threescale_admin_api_key: str, verbose: bool = False) -> list[dict]:
    """
    Lists all available services (models) from 3Scale.
    Returns a list of dictionaries with service ID and name.
    """
    log_message("\nListing all available services (models)...", is_verbose=True)
    endpoint = "services.xml"
    params = {
        "access_token": threescale_admin_api_key,
        "page": 1,
        "per_page": 500
    }

    root = make_api_call("GET", endpoint, params=params, verbose=verbose)
    services = []
    if root is not None:
        for service_element in root.findall("service"):
            service_id = service_element.find("id")
            service_name = service_element.find("name")
            if service_id is not None and service_name is not None:
                services.append({
                    "id": service_id.text,
                    "name": service_name.text
                })
        log_message(f"Found {len(services)} services.", is_verbose=True)
        return services
    return []

def get_account_applications(account_id: str, threescale_admin_api_key: str, verbose: bool = False) -> list[dict]:
    """
    Gets all registered applications for a given account.
    Returns a list of dictionaries with application details.
    """
    log_message(f"\nGetting applications for Account ID: {account_id}...", is_verbose=True)
    endpoint = f"accounts/{account_id}/applications.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params, verbose=verbose)
    applications = []
    if root is not None:
        for app_element in root.findall("application"):
            app_id = app_element.find("id")
            app_name = app_element.find("name")
            user_key = app_element.find("user_key")
            
            # Correctly parse plan_id from the nested 'plan' element
            plan_element = app_element.find("plan")
            plan_id = plan_element.find("id") if plan_element is not None else None
            
            service_id = app_element.find("service_id")

            # --- OPTIMIZED VALIDATION HERE ---
            # Ensure all critical fields are found and are not empty strings after .text
            # Use explicit checks (is not None and has .text) for robustness.
            app_data = {}
            if app_id is not None and app_id.text:
                app_data["id"] = app_id.text
            if app_name is not None and app_name.text:
                app_data["name"] = app_name.text
            if user_key is not None and user_key.text:
                app_data["user_key"] = user_key.text
            if plan_id is not None and plan_id.text:
                app_data["plan_id"] = plan_id.text
            if service_id is not None and service_id.text:
                app_data["service_id"] = service_id.text
            
            # Only add to applications list if all critical fields are present
            if all(k in app_data for k in ["id", "name", "user_key", "plan_id", "service_id"]):
                applications.append(app_data)
            else:
                # Debugging info if an application element is malformed or incomplete
                if verbose:
                    log_message(f"Skipping incomplete application element. Missing critical data. Parsed: {app_data}, Raw: {ET.tostring(app_element, encoding='unicode')}", is_verbose=True)

        log_message(f"Found {len(applications)} applications for account {account_id}.", is_verbose=True)
        return applications
    return []

def get_application_plans(service_id: str, threescale_admin_api_key: str, verbose: bool = False) -> list[dict]:
    """
    Gets application plans for a specific service.
    Returns a list of dictionaries with plan ID and name.
    """
    log_message(f"\nGetting application plans for Service ID: {service_id}...", is_verbose=True)
    endpoint = f"services/{service_id}/application_plans.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params, verbose=verbose)
    plans = []
    if root is not None:
        # Changed 'application_plan' to 'plan' as per user's provided logic
        for plan_element in root.findall("plan"):
            plan_id = plan_element.find("id")
            plan_name = plan_element.find("name")
            if plan_id is not None and plan_name is not None:
                plans.append({
                    "id": plan_id.text,
                    "name": plan_name.text
                })
        log_message(f"Found {len(plans)} application plans for service {service_id}.", is_verbose=True)
        return plans
    return []

def register_application(account_id: str, plan_id: str, app_name: str, threescale_admin_api_key: str, verbose: bool = False) -> dict:
    """
    Registers a new application for an account, effectively creating an API key.
    Returns the application ID and API key if successful.
    """
    log_message(f"\nRegistering new application '{app_name}' for Account ID: {account_id} with Plan ID: {plan_id}...", is_verbose=True)
    endpoint = f"accounts/{account_id}/applications.xml"
    
    data_payload = {
        "name": app_name,
        "plan_id": plan_id,
        "access_token": threescale_admin_api_key # This is the correct parameter name for 3scale Admin API
    }
    
    root = make_api_call("POST", endpoint, data=data_payload, verbose=verbose)

    if root is not None:
        application_id = root.find("id")
        api_key = root.find("user_key")
        
        if application_id is not None and api_key is not None:
            log_message(f"Application registered successfully!")
            log_message(f"Application ID: {application_id.text}")
            log_message(f"Generated API Key: {api_key.text}")
            return {"app_id": application_id.text, "api_key": api_key.text}
        else:
            log_message("Failed to get application ID or API key from response.", is_verbose=True)
            return None
    return None

# --- Main Program Orchestration ---
def main():
    global args # Declare args as global so log_message can access it
    parser = argparse.ArgumentParser(description="Automate 3Scale API key generation and account management.")
    parser.add_argument('-l', '--list', action='store_true', 
                        help="List services for which the account does not have an API key.")
    parser.add_argument('-i', '--init', type=str, metavar="SERVICE_IDENTIFIER",
                        help="Initialize (get/create) an API key for a specific service. "
                             "Provide as 'name=servicename' or 'id=serviceid'.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Enable verbose logging for API calls and internal processes.")
    parser.add_argument('--help-commands', action='store_true', # Custom help flag
                        help='Show specific help for commands (equivalent to -h).')
    
    args = parser.parse_args()

    # If --help-commands is provided, print the parser help and exit
    if args.help_commands:
        parser.print_help()
        return

    # All top-level "script starting" messages should always be visible
    log_message("--- 3Scale API Automation Script ---", is_verbose=True)

    # 1. Get Environment Variables
    keycloak_url = get_env_variable("KEYCLOAK_URL")
    keycloak_realm = get_env_variable("KEYCLOAK_REALM")
    keycloak_client_id = get_env_variable("KEYCLOAK_CLIENT_ID")
    keycloak_client_secret = get_env_variable("KEYCLOAK_CLIENT_SECRET", optional=True)
    threescale_admin_api_url = get_env_variable("THREESCALE_ADMIN_API_URL")
    threescale_admin_api_key = get_env_variable("THREESCALE_ADMIN_API_KEY")

    # 2. Perform SSO Login and get SOEID, Password (if new login), and Email ID from Keycloak
    keycloak_access_token, soeid, password, email_id = sso_login_and_get_credentials(
        keycloak_url, keycloak_realm, keycloak_client_id, keycloak_client_secret, verbose=args.verbose
    )

    if not keycloak_access_token:
        log_message("Keycloak authentication failed. Exiting.", is_error=True)
        return

    if not email_id:
        log_message("Warning: Could not retrieve email ID from Keycloak token. Account creation might fail without it.", is_error=True)
        # Fallback: prompt user for email if it's crucial and not found in token
        email_id = input("Please enter your email ID for 3scale account creation (e.g., your_email@example.com): ")
        if not email_id:
            log_message("Email ID is crucial for 3scale account creation and was not provided. Exiting.", is_error=True)
            return

    log_message(f"\nAuthenticated Keycloak Access Token obtained. SOEID (used as Keycloak Username): {soeid}", is_verbose=True)
    log_message(f"Using Email ID from Keycloak: {email_id}", is_verbose=True)


    # 3. Check if SOEID account exists in 3Scale
    account_id = find_account_by_soeid(soeid, threescale_admin_api_key, verbose=args.verbose)

    if not account_id:
        log_message(f"\nSOEID '{soeid}' does NOT exist in 3Scale.")
        log_message("Proceeding to create a new 3scale account using collected email ID...")
        
        # If password was not collected during SSO (because Keycloak token was reused),
        # but we need to create a 3scale account, we must prompt for a password
        # as the signup API requires it.
        temp_password_for_signup = password 
        if temp_password_for_signup is None:
            log_message("\nTo create your 3scale account, a password is required.")
            temp_password_for_signup = getpass.getpass(f"Enter a password to set for your new 3scale account (for SOEID '{soeid}'): ")
            if not temp_password_for_signup:
                log_message("Password is required for 3scale account creation. Exiting.", is_error=True)
                return

        account_id = create_threescale_account_via_signup(soeid, email_id, temp_password_for_signup, threescale_admin_api_key, verbose=args.verbose)
        
        if not account_id:
            log_message("Failed to create 3scale account. Exiting.", is_error=True)
            return
        else:
            log_message(f"Successfully created 3scale account with ID: {account_id}.")
            log_message("Please wait a moment for account propagation before proceeding with API key generation.", is_verbose=True)
            # import time
            # time.sleep(5) 
    else:
        log_message(f"\nSOEID '{soeid}' exists in 3Scale with Account ID: {account_id}.", is_verbose=True)


    # --- Command-line argument driven flow ---
    if args.list:
        log_message("\n--- Listing Services without API Keys ---", is_verbose=True)
        all_services = list_services(threescale_admin_api_key, verbose=args.verbose)
        existing_applications = get_account_applications(account_id, threescale_admin_api_key, verbose=args.verbose)

        existing_service_ids = {app['service_id'] for app in existing_applications}

        services_without_keys = [
            service for service in all_services 
            if service['id'] not in existing_service_ids
        ]

        if services_without_keys:
            log_message("\nServices for which your account does NOT have an API key:")
            for i, service in enumerate(services_without_keys):
                log_message(f"  {i+1}. ID: {service['id']}, Name: {service['name']}")
        else:
            log_message("\nCongratulations! You have API keys for all available services.")
        
        log_message("\n--- Listing Services without API Keys Completed ---", is_verbose=True)
        return # Exit after listing

    elif args.init:
        log_message(f"\n--- Initializing API Key for Service: {args.init} ---", is_verbose=True)
        identifier_type = None
        identifier_value = None

        if '=' in args.init:
            parts = args.init.split('=', 1)
            identifier_type = parts[0].strip().lower()
            identifier_value = parts[1].strip()
        
        if identifier_type not in ['name', 'id'] or not identifier_value:
            log_message("Error: Invalid --init argument format. Use 'name=servicename' or 'id=serviceid'.", is_error=True)
            return

        all_services = list_services(threescale_admin_api_key, verbose=args.verbose)
        selected_service = None

        for service in all_services:
            if identifier_type == 'id' and service['id'] == identifier_value:
                selected_service = service
                break
            elif identifier_type == 'name' and service['name'].lower() == identifier_value.lower():
                selected_service = service
                break
        
        if not selected_service:
            log_message(f"Error: Service with {identifier_type} '{identifier_value}' not found.", is_error=True)
            return

        log_message(f"\nFound target Service: ID={selected_service['id']}, Name={selected_service['name']}")

        # Proceed with API key generation logic
        application_plans = get_application_plans(selected_service["id"], threescale_admin_api_key, verbose=args.verbose)

        if not application_plans:
            log_message(f"\nNo application plans found for service '{selected_service['name']}'. Cannot create API key.", is_error=True)
            return

        api_key_to_use = None
        
        # Default plan to use if no existing match found, or for new creation
        # IMPORTANT: Use this for new application creation
        target_plan_for_creation = application_plans[0] 

        existing_applications = get_account_applications(account_id, threescale_admin_api_key, verbose=args.verbose)

        # --- REVISED LOGIC TO PREVENT DUPLICATE APPLICATIONS FOR THE SAME SERVICE AND TARGET PLAN ---
        # Iterate through all *existing applications* for the user's account
        # and check if any match the selected service AND the intended target plan.
        
        found_existing_exact_match = False
        for app in existing_applications:
            # Check if this existing application belongs to the selected service AND
            # is associated with the specific plan we would *target* for a new application.
            if app.get("service_id") == selected_service["id"] and \
               app.get("plan_id") == target_plan_for_creation["id"]: # Match on both service_id and plan_id
                log_message(f"\nFound existing application for Service ID '{selected_service['id']}' and Plan ID '{target_plan_for_creation['id']}'.", is_verbose=True)
                api_key_to_use = app["user_key"]
                found_existing_exact_match = True
                break # Found the specific application, exit loop

        if found_existing_exact_match:
            log_message(f"Returning existing API Key: {api_key_to_use}", is_verbose=True)
        else: # No existing application found for this specific service and target plan
            log_message("\nNo existing application found for this service and target plan. Registering a new application...", is_verbose=True)
            
            # Ensure there are plans available for creation
            if not application_plans: 
                log_message(f"\nNo application plans available for service '{selected_service['name']}'. Cannot create API key.", is_error=True)
                return 

            log_message(f"\nTargeting Application Plan for NEW creation: ID={target_plan_for_creation['id']}, Name={target_plan_for_creation['name']}")

            app_name = f"helix-app-{soeid}-{selected_service['id']}-{target_plan_for_creation['id']}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}" 
            
            new_app_details = register_application(
                account_id=account_id,
                plan_id=target_plan_for_creation["id"],
                threescale_admin_api_key=threescale_admin_api_key, 
                app_name=app_name,
                verbose=args.verbose
            )

            if new_app_details:
                api_key_to_use = new_app_details['api_key']
                log_message(f"\n--- API Key generated successfully (new). ---", is_verbose=True)
            else:
                log_message("\n--- ERROR: Failed to register application and create API Key. ---", is_error=True)
                return

        log_message(f"\nFINAL API KEY: {api_key_to_use}")
        log_message("\nIf you need to use this API key in a new shell session, please export it manually:")
        log_message(f"  For Linux/macOS: export GENERATED_API_KEY=\"{api_key_to_use}\"")
        log_message(f"  For Windows (CMD): set GENERATED_API_KEY=\"{api_key_to_use}\"")
        log_message(f"  For Windows (PowerShell): $env:GENERATED_API_KEY=\"{api_key_to_use}\"")

        log_message(f"--- Initialization for Service '{selected_service['name']}' Completed ---", is_verbose=True) # Consolidated message
        return # Exit after initialization

    else:
        # --- Interactive Flow (Original Logic if no arguments are provided) ---
        log_message("\n--- No specific command-line arguments provided. Proceeding with interactive flow. ---")
        # 4. List all available models (services) and prompt user to select one
        services = list_services(threescale_admin_api_key, verbose=args.verbose)

        if not services:
            log_message("\nNo services (models) found in your 3Scale account. Cannot proceed with API key creation.", is_error=True)
            return

        log_message("\nAvailable Services:")
        for i, service in enumerate(services):
            log_message(f"  {i+1}. ID: {service['id']}, Name={service['name']}") # Corrected to show name

        selected_service = None
        while selected_service is None:
            try:
                choice = int(input("Enter the number of the service you want to select: ")) # Always prompt for user input
                if 1 <= choice <= len(services):
                    selected_service = services[choice - 1]
                    log_message(f"\nYou selected Service: ID={selected_service['id']}, Name={selected_service['name']}") # Essential output
                else:
                    log_message("Invalid choice. Please enter a number within the range.", is_error=True)
            except ValueError:
                log_message("Invalid input. Please enter a number.", is_error=True)

        # 5. Get application plans for the selected service
        application_plans = get_application_plans(selected_service["id"], threescale_admin_api_key, verbose=args.verbose)

        if not application_plans:
            log_message(f"\nNo application plans found for service '{selected_service['name']}'. Cannot create API key.", is_error=True)
            return

        api_key_to_use = None
        # Default plan to use if no existing match found, or for new creation
        # IMPORTANT: Use this for new application creation
        target_plan_for_creation = application_plans[0] 

        existing_applications = get_account_applications(account_id, threescale_admin_api_key, verbose=args.verbose)

        # --- REVISED LOGIC FOR -i AND INTERACTIVE FLOW START ---
        # Check if an existing API key exists for the SELECTED SERVICE AND TARGET PLAN
        found_existing_exact_match = False
        for app in existing_applications:
            # Check if this existing application belongs to the selected service AND
            # is associated with the specific plan we would *target* for a new application.
            if app.get("service_id") == selected_service["id"] and \
               app.get("plan_id") == target_plan_for_creation["id"]: # Match on both service_id and plan_id
                log_message(f"\nFound existing application for Service ID '{selected_service['id']}' and Plan ID '{target_plan_for_creation['id']}'.", is_verbose=True)
                api_key_to_use = app["user_key"]
                found_existing_exact_match = True
                break # Found the specific application, exit loop

        if found_existing_exact_match:
            log_message(f"Returning existing API Key: {api_key_to_use}", is_verbose=True) # Essential output
        else: # No existing application found for this specific service and target plan
            log_message("\nNo existing application found for this service and target plan. Registering a new application...", is_verbose=True)
            
            # Ensure there are plans available for creation
            if not application_plans: 
                log_message(f"\nNo application plans available for service '{selected_service['name']}'. Cannot create API key.", is_error=True)
                return 

            log_message(f"\nTargeting Application Plan for NEW creation: ID={target_plan_for_creation['id']}, Name={target_plan_for_creation['name']}", is_verbose=True)

            app_name = f"helix-app-{soeid}-{selected_service['id']}-{target_plan_for_creation['id']}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}" 
            
            new_app_details = register_application(
                account_id=account_id,
                plan_id=target_plan_for_creation["id"],
                threescale_admin_api_key=threescale_admin_api_key, 
                app_name=app_name,
                verbose=args.verbose
            )

            if new_app_details:
                api_key_to_use = new_app_details['api_key']
                log_message(f"\n--- API Key generated successfully (new). ---", is_verbose=True)
            else:
                log_message("\n--- ERROR: Failed to register application and create API Key. ---", is_error=True)
                return
        # --- REVISED LOGIC FOR -i AND INTERACTIVE FLOW END ---

        log_message(f"\nFINAL API KEY: {api_key_to_use}") # Essential output
        log_message("\nIf you need to use this API key in a new shell session, please export it manually:") # Essential output
        log_message(f"  For Linux/macOS: export GENERATED_API_KEY=\"{api_key_to_use}\"") # Essential output
        log_message(f"  For Windows (CMD): set GENERATED_API_KEY=\"{api_key_to_use}\"") # Essential output
        log_message(f"  For Windows (PowerShell): $env:GENERATED_API_KEY=\"{api_key_to_use}\"") # Essential output

        log_message("\n--- 3Scale API Automation Script Completed ---", is_verbose=True) # Consolidated message

if __name__ == "__main__":
    main()
