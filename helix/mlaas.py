import os
import requests
import getpass
import json
import jwt
import datetime
import subprocess
import xml.etree.ElementTree as ET
import argparse
import logging
import configparser
from functools import lru_cache
import sys # Import sys for stdout handler

# --- Constants and Configuration Setup ---
# Store the config file in the user's home directory for persistence
CONFIG_DIR = os.path.expanduser("~")
CONFIG_FILE_NAME = ".threescale_sso_config.ini"
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)

# --- Setup Logging ---
# Main logger for general script messages
logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# User-facing logger for critical output that should always be seen
user_output_logger = logging.getLogger('user_output')
user_output_logger.setLevel(logging.INFO) # Always INFO for user output
user_output_logger.propagate = False # Prevent messages from going to the root logger

# Create a handler for user_output_logger that always prints to console
# and set its level to INFO
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s') # No level name, just the message
ch.setFormatter(formatter)
user_output_logger.addHandler(ch)

# --- Centralized Configuration Management ---
def get_config():
    """Loads or initializes the configuration."""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            config.read(CONFIG_FILE_PATH)
            logger.debug(f"Configuration loaded from {CONFIG_FILE_PATH}")
        except configparser.Error as e:
            logger.error(f"Error reading configuration file: {e}. Starting with an empty configuration.")
            # Optionally, delete corrupted file: os.remove(CONFIG_FILE_PATH)
    return config

def save_config(config):
    """Saves the configuration to the hidden file."""
    try:
        with open(CONFIG_FILE_PATH, 'w') as f:
            config.write(f)
        logger.debug(f"Configuration saved to {CONFIG_FILE_PATH}")
    except IOError as e:
        logger.error(f"Error saving configuration to file: {e}")

# --- Environment Variable Handling ---
def get_env_variable(var_name: str, optional: bool = False, default: str = None) -> str:
    """
    Retrieves an environment variable.
    Exits if the variable is not set and is not optional.
    """
    value = os.getenv(var_name, default)
    if value is None and not optional:
        logger.error(f"Error: Environment variable '{var_name}' is not set.")
        if var_name == "KEYCLOAK_URL":
            logger.error("Please set the following environment variables before running:")
            logger.error("  KEYCLOAK_URL          (e.g., https://your-keycloak-instance.com)")
            logger.error("  KEYCLOAK_REALM        (e.g., your_realm_name)")
            logger.error("  KEYCLOAK_CLIENT_ID    (e.g., your_client_id_for_this_app)")
            logger.error("  KEYCLOAK_CLIENT_SECRET (Optional, if your client is confidential)")
            logger.error("  THREESCALE_ADMIN_API_URL (e.g., https://your-admin-portal.3scale.net/admin/api/)")
            logger.error("  THREESCALE_ADMIN_API_KEY (Your 3scale Admin Portal API Key)")
            logger.error("\nNote: GENERATED_API_KEY will be automatically set after successful operations.")
        exit(1)
    return value

# --- API Request Session ---
api_session = requests.Session()

def make_api_call(method: str, endpoint: str, params: dict = None, data: dict = None, headers: dict = None, 
                  is_threescale_admin_api: bool = True, is_json_response: bool = False) -> [ET.Element, dict, None]:
    """
    Makes an API call using the shared session.
    Handles common response parsing and error checking.
    Returns XML root element for 3Scale Admin API (default), or JSON dict if is_json_response is True.
    Returns None on failure.
    """
    base_url = ""
    if is_threescale_admin_api:
        base_url = get_env_variable("THREESCALE_ADMIN_API_URL")
        if not base_url.endswith('/'):
            base_url += '/'
    
    url = f"{base_url}{endpoint}" if is_threescale_admin_api else endpoint

    logger.debug(f"\n--- Making {method} request to: {url} ---")
    logger.debug(f"API Input - Params: {params}")
    logger.debug(f"API Input - Data: {data}")
    logger.debug(f"API Input - Headers: {headers}")

    try:
        response = api_session.request(method, url, params=params, data=data, headers=headers, timeout=30)
        response.raise_for_status()

        logger.debug(f"Response Status Code: {response.status_code}")
        logger.debug(f"Raw API Output: {response.text}")

        if is_json_response:
            return response.json()
        elif is_threescale_admin_api:
            return ET.fromstring(response.text)
        else:
            return response.json()

    except requests.exceptions.HTTPError as e:
#        logger.error(f"HTTP Error occurred: . Status Code: {response.status_code}")
#        logger.debug(f"Raw API Output (Error): {response.text}")
        try:
            error_details = response.json()
            logger.error("Error Details (JSON):")
            logger.error(json.dumps(error_details, indent=2))
        except json.JSONDecodeError:
            logger.info(f"Could not decode error response (non-JSON): {response.text}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error occurred: {e}")
        return None
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout Error occurred after 30 seconds: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"An unexpected Request Error occurred: {e}")
        return None
    except ET.ParseError as e:
        logger.error(f"Error parsing XML response: {e}")
        logger.error(f"Raw response text: {response.text}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {e}")
        logger.error(f"Raw response text: {response.text}")
        return None

# --- System Utilities ---
def get_current_system_username() -> str:
    """
    Attempts to get the current system username using 'whoami' command.
    Returns an empty string if command fails.
    """
    try:
        result = subprocess.run(["whoami"], capture_output=True, text=True, check=True, timeout=5)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Could not get system username via 'whoami': {e}. Defaulting to empty string.")
        return ""

# --- Keycloak Specific Helpers ---
def sso_login_and_get_credentials(keycloak_url: str, keycloak_realm: str, keycloak_client_id: str, 
                                  keycloak_client_secret: str) -> tuple[str, str, str, str]:
    """
    Performs SSO login, manages the access token by attempting to reuse from config.
    Retrieves email and SOEID from Keycloak access token.
    If reauthentication is needed, prompts for SOEID and password.
    Returns (keycloak_access_token, soeid, password, email_id).
    Password will be None if token is reused.
    """
    access_token = None
    email_id = None
    soeid = None
    password = None 

    config = get_config()
    token_section_name = "KeycloakToken"
    
    if config.has_section(token_section_name):
        current_access_token = config.get(token_section_name, 'access_token', fallback=None)
        
        if current_access_token:
            logger.info("Found existing Keycloak token in config. Attempting to validate and reuse...")
            try:
                decoded_token = jwt.decode(current_access_token, options={"verify_signature": False})
                expiration_timestamp = decoded_token.get('exp')
                email_id_from_token = decoded_token.get('email')
                soeid_from_token = decoded_token.get('preferred_username') or decoded_token.get('sub')

                current_time_utc_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()

                if expiration_timestamp and email_id_from_token and soeid_from_token and \
                   expiration_timestamp > current_time_utc_timestamp + 60:
                    
                    access_token = current_access_token
                    email_id = email_id_from_token
                    soeid = soeid_from_token
                    logger.info("Existing token is valid, has required claims, and not expired. Reusing token.")
                    logger.debug(f"Inferred SOEID from token: {soeid}")
                    logger.debug(f"Inferred Email from token: {email_id}")
                    return access_token, soeid, password, email_id
                else:
                    logger.info("Existing token is expired, missing required claims (email/SOEID), or close to expiration. Will re-authenticate.")
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception) as e:
                logger.warning(f"Error validating existing token: {e}. Will re-authenticate.")
    else:
        logger.info("No Keycloak token section found in config. Will perform a new login.")

    # --- New authentication needed ---
    default_soeid = get_current_system_username()
    soeid_prompt = f"Enter your SOEID (Red Hat SSO Username) (default: {default_soeid}): " if default_soeid else "Enter your SOEID (Red Hat SSO Username): "
    
    soeid = input(soeid_prompt)
    if not soeid and default_soeid:
        soeid = default_soeid
        logger.info(f"Using default SOEID: {soeid}")

    if not soeid:
        logger.error("SOEID is required to proceed. Exiting.")
        return None, None, None, None

    password = getpass.getpass(f"Enter your Red Hat SSO Password for user '{soeid}': ")

    token_url = f"{keycloak_url}/realms/{keycloak_realm}/protocol/openid-connect/token"
    logger.debug(f"Attempting to connect to Keycloak at: {token_url}")
    logger.debug(f"Using Keycloak Client ID: {keycloak_client_id}")

    payload = {
        "grant_type": "password",
        "client_id": keycloak_client_id,
        "username": soeid,
        "password": password,
        "scope": "openid profile email"
    }
    if keycloak_client_secret:
        payload["client_secret"] = keycloak_client_secret

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_data = make_api_call("POST", token_url, data=payload, headers=headers, is_threescale_admin_api=False, is_json_response=True)
    
    if token_data and 'access_token' in token_data:
        access_token = token_data['access_token']
        try:
            decoded_token = jwt.decode(access_token, options={"verify_signature": False})
            email_id = decoded_token.get('email')
            if not email_id:
                logger.warning("Email claim not found in the new Keycloak access token.")
        except (jwt.InvalidTokenError, Exception) as e:
            logger.warning(f"Error decoding new Keycloak token to get email: {e}")

        if not config.has_section(token_section_name):
            config.add_section(token_section_name)
        for key, value in token_data.items():
            config.set(token_section_name, key, str(value))
        save_config(config)

        logger.info("\n--- Keycloak Login Successful! ---")
        logger.debug(f"Access Token (Bearer): {access_token[:30]}... (truncated)")
        logger.debug(f"Expires In (seconds): {token_data.get('expires_in')}")
        if email_id:
            logger.info(f"Associated Email ID: {email_id}")
    else:
        logger.error("Failed to obtain access token from Keycloak.")
        return None, soeid, password, None

    return access_token, soeid, password, email_id

# --- 3Scale Specific Helpers ---
def find_account_by_soeid(soeid: str, threescale_admin_api_key: str) -> str | None:
    """
    Checks if an SOEID exists in 3Scale by finding the account.
    Returns account ID if found, otherwise None.
    """
    logger.info(f"\nChecking if SOEID '{soeid}' exists in 3Scale...")
    endpoint = "accounts/find.xml"
    params = {
        "access_token": threescale_admin_api_key,
        "username": soeid
    }
    
    root = make_api_call("GET", endpoint, params=params)

    if root is not None:
        account_id_element = root.find("id")
        if account_id_element is not None and account_id_element.text:
            account_id = account_id_element.text
            logger.info(f"Account found! Account ID: {account_id}")
            return account_id
        else:
            logger.info("Account not found for the given SOEID.")
            return None
    return None

def create_threescale_account_via_signup(soeid: str, emailid: str, password: str, threescale_admin_api_key: str) -> str | None:
    """
    Creates a new 3Scale developer account using the signup API.
    Returns the new account's ID if successful.
    """
    logger.info(f"\nAttempting to create new 3scale account for SOEID '{soeid}'...")
    signup_endpoint = "signup.xml"

    payload = {
        "access_token": threescale_admin_api_key,
        "username": soeid,
        "email": emailid,
        "org_name": emailid, 
        "password": password,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/xml"
    }

    root = make_api_call("POST", signup_endpoint, data=payload, headers=headers)

    if root is not None:
        # The 'root' element itself IS the 'account' element in this response
        account_element = root 
        
        # Now, proceed to find 'id' directly within the account_element (which is 'root')
        account_id_element = account_element.find("id") 
        if account_id_element is not None and account_id_element.text:
            new_account_id = account_id_element.text
            logger.info(f"Successfully created 3scale account! New Account ID: {new_account_id}")
            return new_account_id
        else:
            logger.error("Could not find account ID in signup response.")
    
    # This specific error message "Could not find 'account' element in signup response." 
    # will no longer be hit by the fix above, but the general "Failed to create 3scale account." 
    # message is still good if root is None or id is missing.
    logger.error("Failed to create 3scale account.")
    return None

@lru_cache(maxsize=1)
def list_services(threescale_admin_api_key: str) -> list[dict]:
    """
    Lists all available services (models) from 3Scale.
    Returns a list of dictionaries with service ID and name.
    """
    logger.info("\nListing all available services (models)...")
    endpoint = "services.xml"
    params = {
        "access_token": threescale_admin_api_key,
        "page": 1,
        "per_page": 500
    }

    root = make_api_call("GET", endpoint, params=params)
    services = []
    if root is not None:
        for service_element in root.findall("service"):
            service_id = service_element.find("id")
            service_name = service_element.find("name")
            # Extract the backend_api_url
            backend_api_url = service_element.find("backend_api_url") 

            if service_id is not None and service_id.text and \
               service_name is not None and service_name.text:
                services.append({
                    "id": service_id.text,
                    "name": service_name.text,
                    "url": backend_api_url.text if backend_api_url is not None else "N/A" # Add URL here
                })
        logger.info(f"Found {len(services)} services.")
        return services
    return []

@lru_cache(maxsize=4)
def get_account_applications(account_id: str, threescale_admin_api_key: str) -> list[dict]:
    """
    Gets all registered applications for a given account.
    Returns a list of dictionaries with application details.
    """
    logger.info(f"\nGetting applications for Account ID: {account_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params)
    applications = []
    if root is not None:
        for app_element in root.findall("application"):
            app_data = {
                "id": app_element.findtext("id"),
                "name": app_element.findtext("name"),
                "user_key": app_element.findtext("user_key"),
                "service_id": app_element.findtext("service_id")
            }
            plan_element = app_element.find("plan")
            if plan_element is not None:
                app_data["plan_id"] = plan_element.findtext("id")
            
            if all(app_data.get(k) for k in ["id", "name", "user_key", "plan_id", "service_id"]):
                applications.append(app_data)
            else:
                logger.debug(f"Skipping incomplete application element. Missing critical data. Parsed: {app_data}, Raw: {ET.tostring(app_element, encoding='unicode')}")

        logger.info(f"Found {len(applications)} applications for account {account_id}.")
        return applications
    return []

@lru_cache(maxsize=16)
def get_application_plans(service_id: str, threescale_admin_api_key: str) -> list[dict]:
    """
    Gets application plans for a specific service.
    Returns a list of dictionaries with plan ID and name.
    """
    logger.info(f"\nGetting application plans for Service ID: {service_id}...")
    endpoint = f"services/{service_id}/application_plans.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params)
    plans = []
    if root is not None:
        for plan_element in root.findall("plan"):
            plan_id = plan_element.find("id")
            plan_name = plan_element.find("name")
            if plan_id is not None and plan_id.text and \
               plan_name is not None and plan_name.text:
                plans.append({
                    "id": plan_id.text,
                    "name": plan_name.text
                })
        logger.info(f"Found {len(plans)} application plans for service {service_id}.")
        return plans
    return []

def register_application(account_id: str, plan_id: str, app_name: str, threescale_admin_api_key: str) -> dict | None:
    """
    Registers a new application for an account, effectively creating an API key.
    Returns the application ID and API key if successful.
    """
    logger.info(f"\nRegistering new application '{app_name}' for Account ID: {account_id} with Plan ID: {plan_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    
    data_payload = {
        "name": app_name,
        "plan_id": plan_id,
        "access_token": threescale_admin_api_key
    }
    
    root = make_api_call("POST", endpoint, data=data_payload)

    if root is not None:
        application_id = root.findtext("id")
        api_key = root.findtext("user_key")
        
        if application_id and api_key:
            user_output_logger.info("Application registered successfully!")
            logger.info(f"Application ID: {application_id}")
            user_output_logger.info(f"Generated API Key: {api_key}")
            return {"app_id": application_id, "api_key": api_key}
        else:
            logger.error("Failed to get application ID or API key from response.")
            return None
    return None

# --- Main Program Orchestration ---
def main():
    parser = argparse.ArgumentParser(
        description="Automate 3Scale API key generation and account management.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-l', '--list', action='store_true', 
                        help="List services for which the account does not have an API key.")
    parser.add_argument('-i', '--init', type=str, metavar="SERVICE_IDENTIFIER",
                        help="Initialize (get/create) an API key for a specific service.\n"
                             "Provide as 'name=<servicename>' or 'id=<serviceid>'.")
    
    args = parser.parse_args()

    logger.info("--- 3Scale API Automation Script ---")

    keycloak_url = get_env_variable("KEYCLOAK_URL")
    keycloak_realm = get_env_variable("KEYCLOAK_REALM")
    keycloak_client_id = get_env_variable("KEYCLOAK_CLIENT_ID")
    keycloak_client_secret = get_env_variable("KEYCLOAK_CLIENT_SECRET", optional=True, default="")
    threescale_admin_api_url = get_env_variable("THREESCALE_ADMIN_API_URL")
    threescale_admin_api_key = get_env_variable("THREESCALE_ADMIN_API_KEY")

    keycloak_access_token, soeid, password, email_id = sso_login_and_get_credentials(
        keycloak_url, keycloak_realm, keycloak_client_id, keycloak_client_secret
    )

    if not keycloak_access_token:
        logger.error("Keycloak authentication failed. Exiting.")
        return

    if not email_id:
        logger.warning("Could not retrieve email ID from Keycloak token. Account creation might require it.")
        email_id = input("Please enter your email ID for 3scale account creation (e.g., your_email@example.com): ")
        if not email_id:
            logger.error("Email ID is crucial for 3scale account creation and was not provided. Exiting.")
            return

    logger.info(f"Authenticated Keycloak Access Token obtained. SOEID (used as Keycloak Username): {soeid}")
    logger.info(f"Using Email ID from Keycloak: {email_id}")

    account_id = find_account_by_soeid(soeid, threescale_admin_api_key)

    if not account_id:
        logger.info(f"\nSOEID '{soeid}' does NOT exist in 3Scale.")
        logger.info("Proceeding to create a new 3scale account using collected email ID...")
        
        temp_password_for_signup = password 
        if temp_password_for_signup is None:
            logger.info("\nTo create your 3scale account, a password is required.")
            temp_password_for_signup = getpass.getpass(f"Enter a password to set for your new 3scale account (for SOEID '{soeid}'): ")
            if not temp_password_for_signup:
                logger.error("Password is required for 3scale account creation. Exiting.")
                return

        account_id = create_threescale_account_via_signup(soeid, email_id, temp_password_for_signup, threescale_admin_api_key)
        
        if not account_id:
            logger.error("Failed to create 3scale account. Exiting.")
            return
        else:
            logger.info(f"Successfully created 3scale account with ID: {account_id}.")
    else:
        logger.info(f"SOEID '{soeid}' exists in 3Scale with Account ID: {account_id}.")

    if args.list:
        logger.info("\n--- Listing Services and API Key Status ---")
        all_services = list_services(threescale_admin_api_key)
        existing_applications = get_account_applications(account_id, threescale_admin_api_key)

        existing_service_info = {app['service_id']: app['user_key'] for app in existing_applications}

        services_with_keys = []
        services_without_keys = []

        for service in all_services:
            if service['id'] in existing_service_info:
                service['api_key'] = existing_service_info[service['id']]
                services_with_keys.append(service)
            else:
                services_without_keys.append(service)

        if services_with_keys:
            user_output_logger.info("\nServices for which your account HAS an API key:")
            for i, service in enumerate(services_with_keys):
                user_output_logger.info(f"  {i+1}. ID: {service['id']}, Name: {service['name']}, URL: {service['url']}, API Key: {service['api_key']}")
        else:
            user_output_logger.info("\nYou do not have API keys for any services.")

        if services_without_keys:
            user_output_logger.info("\nServices for which your account does NOT have an API key:")
            for i, service in enumerate(services_without_keys):
                user_output_logger.info(f"  {i+1}. ID: {service['id']}, Name: {service['name']}, URL: {service['url']}")
        else:
            user_output_logger.info("\nYou have API keys for all available services.")

        logger.info("\n--- Listing Services and API Key Status Completed ---")
        return
    elif args.init:
        logger.info(f"\n--- Initializing API Key for Service: {args.init} ---") # Changed to logger
        identifier_type = None
        identifier_value = None

        if '=' in args.init:
            parts = args.init.split('=', 1)
            identifier_type = parts[0].strip().lower()
            identifier_value = parts[1].strip()
        
        if identifier_type not in ['name', 'id'] or not identifier_value:
            logger.error("Error: Invalid --init argument format. Use 'name=<servicename>' or 'id=<serviceid>'.")
            return

        all_services = list_services(threescale_admin_api_key)
        selected_service = None

        for service in all_services:
            if identifier_type == 'id' and service['id'] == identifier_value:
                selected_service = service
                break
            elif identifier_type == 'name' and service['name'].lower() == identifier_value.lower():
                selected_service = service
                break
        
        if not selected_service:
            logger.error(f"Error: Service with {identifier_type} '{identifier_value}' not found.")
            return

        logger.info(f"\nFound target Service: ID={selected_service['id']}, Name={selected_service['name']}") # Changed to user_output_logger

        application_plans = get_application_plans(selected_service["id"], threescale_admin_api_key)

        if not application_plans:
            logger.error(f"\nNo application plans found for service '{selected_service['name']}'. Cannot create API key.")
            return

        target_plan_for_creation = application_plans[0] 

        existing_applications = get_account_applications(account_id, threescale_admin_api_key)
        
        api_key_to_use = None
        found_existing_exact_match = False

        for app in existing_applications:
            if app.get("service_id") == selected_service["id"] and \
               app.get("plan_id") == target_plan_for_creation["id"]:
                logger.info(f"Found existing application for Service ID '{selected_service['id']}' and Plan ID '{target_plan_for_creation['id']}'.")
                api_key_to_use = app["user_key"]
                found_existing_exact_match = True
                break

        if found_existing_exact_match:
            user_output_logger.info(f"Returning existing API Key: {api_key_to_use}") # Changed to user_output_logger
        else:
            logger.info("No existing application found for this service and target plan. Registering a new application...")
            
            logger.info(f"Targeting Application Plan for NEW creation: ID={target_plan_for_creation['id']}, Name={target_plan_for_creation['name']}")

            app_name = f"helix-app-{soeid}-{selected_service['id']}-{target_plan_for_creation['id']}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}" 
            
            new_app_details = register_application(
                account_id=account_id,
                plan_id=target_plan_for_creation["id"],
                threescale_admin_api_key=threescale_admin_api_key, 
                app_name=app_name
            )

            if new_app_details:
                api_key_to_use = new_app_details['api_key']
                logger.info("\n--- API Key generated successfully (new): {api_key_to_use} ---") # Changed to logger
            else:
                logger.error("\n--- ERROR: Failed to register application and create API Key. ---")
                return

        logger.info(f"--- Initialization for Service '{selected_service['name']}' Completed ---") # Changed to logger
        return

    else:
        user_output_logger.info("\n--- No specific command-line arguments provided. Proceeding with interactive flow. ---") # Changed to user_output_logger
        services = list_services(threescale_admin_api_key)

        if not services:
            logger.error("\nNo services (models) found in your 3Scale account. Cannot proceed with API key creation.")
            return

        user_output_logger.info("\nAvailable Services:") # Changed to user_output_logger
        for i, service in enumerate(services):
            user_output_logger.info(f"  {i+1}. ID: {service['id']}, Name={service['name']}") # Changed to user_output_logger

        selected_service = None
        while selected_service is None:
            try:
                choice = int(input("Enter the number of the service you want to select: "))
                if 1 <= choice <= len(services):
                    selected_service = services[choice - 1]
                    user_output_logger.info(f"\nYou selected Service: ID={selected_service['id']}, Name={selected_service['name']}") # Changed to user_output_logger
                else:
                    logger.error("Invalid choice. Please enter a number within the range.")
            except ValueError:
                logger.error("Invalid input. Please enter a number.")

        application_plans = get_application_plans(selected_service["id"], threescale_admin_api_key)

        if not application_plans:
            logger.error(f"\nNo application plans found for service '{selected_service['name']}'. Cannot create API key.")
            return

        api_key_to_use = None
        target_plan_for_creation = application_plans[0] 

        existing_applications = get_account_applications(account_id, threescale_admin_api_key)
        
        found_existing_exact_match = False
        for app in existing_applications:
            if app.get("service_id") == selected_service["id"] and \
               app.get("plan_id") == target_plan_for_creation["id"]:
                logger.info(f"Found existing application for Service ID '{selected_service['id']}' and Plan ID '{target_plan_for_creation['id']}'.")
                api_key_to_use = app["user_key"]
                found_existing_exact_match = True
                break

        if found_existing_exact_match:
            user_output_logger.info(f"Returning existing API Key: {api_key_to_use}") # Changed to user_output_logger
        else:
            logger.info("No existing application found for this service and target plan. Registering a new application...")
            
            logger.info(f"Targeting Application Plan for NEW creation: ID={target_plan_for_creation['id']}, Name={target_plan_for_creation['name']}")

            app_name = f"helix-app-{soeid}-{selected_service['id']}-{target_plan_for_creation['id']}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}" 
            
            new_app_details = register_application(
                account_id=account_id,
                plan_id=target_plan_for_creation["id"],
                threescale_admin_api_key=threescale_admin_api_key, 
                app_name=app_name
            )

            if new_app_details:
                api_key_to_use = new_app_details['api_key']
                user_output_logger.info("\n--- API Key generated successfully (new): \"{api_key_to_use}\" ---") # Changed to user_output_logger
            else:
                logger.error("\n--- ERROR: Failed to register application and create API Key. ---")
                return


        logger.info("\n--- 3Scale API Automation Script Completed ---") # Changed to logger

if __name__ == "__main__":
    main()