import os
import requests
import getpass
import json
import jwt # Required for decoding JWTs
import datetime # Required for checking token expiration
import subprocess # Required for running 'whoami'
import xml.etree.ElementTree as ET # Moved this import to the top

# --- Centralized Helper Functions ---

def get_env_variable(var_name: str, optional: bool = False) -> str:
    """
    Retrieves an environment variable.
    Exits if the variable is not set and is not optional.
    """
    value = os.getenv(var_name)
    if value is None and not optional:
        print(f"Error: Environment variable '{var_name}' is not set.")
        if var_name == "KEYCLOAK_URL": # Only print full instructions for the first critical missing var
            print("Please set the following environment variables before running:")
            print("  KEYCLOAK_URL          (e.g., https://your-keycloak-instance.com)")
            print("  KEYCLOAK_REALM        (e.g., your_realm_name)")
            print("  KEYCLOAK_CLIENT_ID    (e.g., your_client_id_for_this_app)")
            print("  KEYCLOAK_CLIENT_SECRET (Optional, if your client is confidential)")
            print("  THREESCALE_ADMIN_API_URL (e.g., https://your-admin-portal.3scale.net/admin/api/)") # Added /admin/api/
            print("  THREESCALE_ADMIN_API_KEY (Your 3scale Admin Portal API Key)")
            print("\nNote: KEYCLOAK_ACCESS_TOKEN and GENERATED_API_KEY will be automatically set after successful operations.")
        exit(1)
    return value

def make_api_call(method: str, endpoint: str, params: dict = None, data: dict = None, headers: dict = None, is_threescale_admin_api: bool = True) -> ET.Element:
    """
    Makes an API call to the 3Scale Admin API or other specified API.
    Handles common response parsing and error checking.
    Returns XML root element for 3Scale Admin API, or JSON for others if specified.
    """
    base_url = ""
    if is_threescale_admin_api:
        base_url = get_env_variable("THREESCALE_ADMIN_API_URL")
        # Ensure the base_url ends with / if it's the 3scale admin API
        if not base_url.endswith('/'):
            base_url += '/'
    else:
        # For other APIs (like Keycloak), the full URL is constructed outside this function.
        # This function should then receive the full URL as `endpoint`.
        # For simplicity, if not threescale_admin_api, endpoint is assumed to be full URL.
        base_url = ""

    url = f"{base_url}{endpoint}" if is_threescale_admin_api else endpoint

    print(f"\n--- Making {method} request to: {url} ---")
    # print(f"Parameters: {params}") # Uncomment for debugging params
    # print(f"Data: {data}") # Uncomment for debugging data

    try:
        if method == "GET":
            response = requests.get(url, params=params, headers=headers)
        elif method == "POST":
            response = requests.post(url, data=data, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, params=params, headers=headers)
        else:
            print(f"Error: Unsupported HTTP method '{method}'.")
            return None

        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        print(f"Response Status Code: {response.status_code}")
        # print(f"Response Content:\n{response.text}") # Uncomment for debugging full response

        if is_threescale_admin_api:
            # 3scale Admin API often returns XML
            root = ET.fromstring(response.text)
            return root
        else:
            # For Keycloak or other JSON APIs
            return response.json()

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {e}")
        try:
            error_details = response.json()
            print("Error Details (JSON):")
            print(json.dumps(error_details, indent=2))
        except json.JSONDecodeError:
            print(f"Could not decode error response (non-JSON): {response.text}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error occurred: {e}")
        return None
    except requests.exceptions.Timeout as e:
        print(f"Timeout Error occurred: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"An unexpected Request Error occurred: {e}")
        return None
    except ET.ParseError as e:
        print(f"Error parsing XML response: {e}")
        print(f"Raw response text: {response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response text: {response.text}")
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
        print(f"Warning: Could not get system username via 'whoami': {e}. Defaulting to empty string.")
        return ""

def sso_login_and_get_soeid(keycloak_url: str, keycloak_realm: str, keycloak_client_id: str, keycloak_client_secret: str) -> tuple[str, str]:
    """
    Performs SSO login, manages access token, and prompts for SOEID if needed.
    Returns (keycloak_access_token, soeid).
    """
    access_token = None
    # Attempt to retrieve an existing access token from the environment
    current_access_token = os.getenv("KEYCLOAK_ACCESS_TOKEN")

    if current_access_token:
        print("\nFound existing KEYCLOAK_ACCESS_TOKEN in environment. Attempting to validate...")
        try:
            decoded_token = jwt.decode(current_access_token, options={"verify_signature": False})
            expiration_timestamp = decoded_token.get('exp')

            if expiration_timestamp:
                current_time_utc_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
                if expiration_timestamp > current_time_utc_timestamp + 60: # 60-second buffer
                    access_token = current_access_token
                    print("Existing token is valid and not expired. Reusing token.")
                else:
                    print("Existing token is expired or close to expiration. Will re-authenticate.")
            else:
                print("Existing token does not contain an expiration claim. Will re-authenticate.")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception) as e:
            print(f"Error validating existing token: {e}. Will re-authenticate.")
    else:
        print("\nNo KEYCLOAK_ACCESS_TOKEN found in environment. Will perform a new login.")

    if not access_token: # If no valid token was found or validation failed
        token_url = f"{keycloak_url}/realms/{keycloak_realm}/protocol/openid-connect/token"
        print(f"\nAttempting to connect to Keycloak at: {token_url}")
        print(f"Using Keycloak Client ID: {keycloak_client_id}")

        username = input("Enter your Red Hat SSO Username: ")
        password = getpass.getpass("Enter your Red Hat SSO Password: ")

        payload = {
            "grant_type": "password",
            "client_id": keycloak_client_id,
            "username": username,
            "password": password,
            "scope": "openid profile email"
        }
        if keycloak_client_secret:
            payload["client_secret"] = keycloak_client_secret

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        token_data = make_api_call("POST", token_url, data=payload, headers=headers, is_threescale_admin_api=False)
        if token_data:
            access_token = token_data.get('access_token')
            if access_token:
                os.environ["KEYCLOAK_ACCESS_TOKEN"] = access_token
                print("\nKEYCLOAK_ACCESS_TOKEN stored in current environment for reuse.")
                print("\n--- Keycloak Login Successful! ---")
                print(f"Access Token (Bearer): {access_token[:30]}... (truncated)")
                print(f"Expires In (seconds): {token_data.get('expires_in')}")
            else:
                print("Login successful, but no access_token found in response.")
                return None, None
        else:
            print("Failed to obtain access token from Keycloak.")
            return None, None

    # Prompt for SOEID (now with default from whoami)
    default_soeid = get_current_system_username()
    soeid_prompt = f"Enter your SOEID (default: {default_soeid}): " if default_soeid else "Enter your SOEID: "
    soeid = input(soeid_prompt)
    if not soeid and default_soeid:
        soeid = default_soeid
        print(f"Using default SOEID: {soeid}")

    if not soeid:
        print("SOEID is required to proceed. Exiting.")
        return None, None

    return access_token, soeid

def find_account_by_soeid(soeid: str, threescale_admin_api_key: str) -> str:
    """
    Checks if an SOEID exists in 3Scale by finding the account.
    Returns account ID if found, otherwise None.
    """
    print(f"\nChecking if SOEID '{soeid}' exists in 3Scale...")
    endpoint = "accounts/find.xml"
    params = {
        "access_token": threescale_admin_api_key, # Use 3scale Admin API Key here
        "username": soeid
    }
    
    root = make_api_call("GET", endpoint, params=params)

    if root is not None:
        account_id_element = root.find("id")
        if account_id_element is not None:
            account_id = account_id_element.text
            print(f"Account found! Account ID: {account_id}")
            return account_id
        else:
            print("Account not found for the given SOEID.")
            return None
    return None

def list_services(threescale_admin_api_key: str) -> list[dict]:
    """
    Lists all available services (models) from 3Scale.
    Returns a list of dictionaries with service ID and name.
    """
    print("\nListing all available services (models)...")
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
            if service_id is not None and service_name is not None:
                services.append({
                    "id": service_id.text,
                    "name": service_name.text
                })
        print(f"Found {len(services)} services.")
        return services
    return []

def get_account_applications(account_id: str, threescale_admin_api_key: str) -> list[dict]:
    """
    Gets all registered applications for a given account.
    Returns a list of dictionaries with application details.
    """
    print(f"\nGetting applications for Account ID: {account_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params)
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

            if all([app_id, app_name, user_key, plan_id, service_id]):
                applications.append({
                    "id": app_id.text,
                    "name": app_name.text,
                    "user_key": user_key.text,
                    "plan_id": plan_id.text,
                    "service_id": service_id.text
                })
        print(f"Found {len(applications)} applications for account {account_id}.")
        return applications
    return []

def get_application_plans(service_id: str, threescale_admin_api_key: str) -> list[dict]:
    """
    Gets application plans for a specific service.
    Returns a list of dictionaries with plan ID and name.
    """
    print(f"\nGetting application plans for Service ID: {service_id}...")
    endpoint = f"services/{service_id}/application_plans.xml"
    params = {
        "access_token": threescale_admin_api_key
    }

    root = make_api_call("GET", endpoint, params=params)
    plans = []
    if root is not None:
        for plan_element in root.findall("application_plan"):
            plan_id = plan_element.find("id")
            plan_name = plan_element.find("name")
            if plan_id is not None and plan_name is not None:
                plans.append({
                    "id": plan_id.text,
                    "name": plan_name.text
                })
        print(f"Found {len(plans)} application plans for service {service_id}.")
        return plans
    return []

def register_application(account_id: str, plan_id: str, app_name: str, threescale_admin_api_key: str) -> dict:
    """
    Registers a new application for an account, effectively creating an API key.
    Returns the application ID and API key if successful.
    """
    print(f"\nRegistering new application '{app_name}' for Account ID: {account_id} with Plan ID: {plan_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    
    data_payload = {
        "name": app_name,
        "plan_id": plan_id,
        "access_token": threescale_admin_api_key
    }
    
    root = make_api_call("POST", endpoint, data=data_payload)

    if root is not None:
        application_id = root.find("id")
        api_key = root.find("user_key")
        
        if application_id is not None and api_key is not None:
            print(f"Application registered successfully!")
            print(f"Application ID: {application_id.text}")
            print(f"Generated API Key: {api_key.text}")
            return {"app_id": application_id.text, "api_key": api_key.text}
        else:
            print("Failed to get application ID or API key from response.")
            return None
    return None

# --- Main Program Orchestration ---
def main():
    print("--- 3Scale API Automation Script ---")

    # 1. Get Environment Variables
    keycloak_url = get_env_variable("KEYCLOAK_URL")
    keycloak_realm = get_env_variable("KEYCLOAK_REALM")
    keycloak_client_id = get_env_variable("KEYCLOAK_CLIENT_ID")
    keycloak_client_secret = get_env_variable("KEYCLOAK_CLIENT_SECRET", optional=True)
    threescale_admin_api_url = get_env_variable("THREESCALE_ADMIN_API_URL")
    threescale_admin_api_key = get_env_variable("THREESCALE_ADMIN_API_KEY")

    # 2. Perform SSO Login and get SOEID
    keycloak_access_token, soeid = sso_login_and_get_soeid(
        keycloak_url, keycloak_realm, keycloak_client_id, keycloak_client_secret
    )

    if not keycloak_access_token or not soeid:
        print("Authentication or SOEID retrieval failed. Exiting.")
        return

    print(f"\nAuthenticated Keycloak Access Token obtained. SOEID: {soeid}")

    # 3. Check if SOEID exists in 3Scale (Find Account)
    account_id = find_account_by_soeid(soeid, threescale_admin_api_key)

    if not account_id:
        print(f"\nSOEID '{soeid}' does NOT exist in 3Scale.")
        print("Please create your account by logging in to the API management portal: www.3scale.com")
        print("Once created, you can run this script again.")
        return # Exit if account doesn't exist

    print(f"\nSOEID '{soeid}' exists in 3Scale with Account ID: {account_id}.")

    # 4. List all available models (services) and prompt user to select one
    services = list_services(threescale_admin_api_key)

    if not services:
        print("\nNo services (models) found in your 3Scale account. Cannot proceed with API key creation.")
        return

    print("\nAvailable Services:")
    for i, service in enumerate(services):
        print(f"  {i+1}. ID: {service['id']}, Name: {service['name']}")

    selected_service = None
    while selected_service is None:
        try:
            choice = int(input("Enter the number of the service you want to select: "))
            if 1 <= choice <= len(services):
                selected_service = services[choice - 1]
                print(f"\nYou selected Service: ID={selected_service['id']}, Name={selected_service['name']}")
            else:
                print("Invalid choice. Please enter a number within the range.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    # 5. Get application plans for the selected service
    application_plans = get_application_plans(selected_service["id"], threescale_admin_api_key)

    if not application_plans:
        print(f"\nNo application plans found for service '{selected_service['name']}'. Cannot create API key.")
        return

    # For simplicity, we'll target the first application plan found.
    # In a real scenario, you might prompt the user to select a specific plan.
    target_plan = application_plans[0]
    print(f"\nTargeting Application Plan: ID={target_plan['id']}, Name={target_plan['name']}")

    # 6. Check if the plan is already registered for the user, otherwise register it
    existing_applications = get_account_applications(account_id, threescale_admin_api_key)
    api_key_to_use = None

    for app in existing_applications:
        if app.get("service_id") == selected_service["id"] and app.get("plan_id") == target_plan["id"]:
            print(f"\nFound existing registration for Service ID '{selected_service['id']}' and Plan ID '{target_plan['id']}'.")
            api_key_to_use = app["user_key"]
            print(f"Returning existing API Key: {api_key_to_use}")
            break
    
    if not api_key_to_use:
        print("\nPlan is not registered for the user. Registering a new application...")
        # Create a unique app name
        app_name = f"helix-app-{soeid}-{selected_service['id']}-{target_plan['id']}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}" 
        
        new_app_details = register_application(
            account_id=account_id,
            plan_id=target_plan["id"],
            app_name=app_name,
            access_token=threescale_admin_api_key # Use 3scale Admin API Key for this
        )

        if new_app_details:
            api_key_to_use = new_app_details['api_key']
            print(f"\n--- API Key generated successfully (new). ---")
        else:
            print("\n--- ERROR: Failed to register application and create API Key. ---")
            return

    # 7. Set the API key in an environment variable (for current process)
    os.environ["GENERATED_API_KEY"] = api_key_to_use
    print(f"\nFINAL API KEY: {api_key_to_use}")
    print(f"API Key also set in environment variable 'GENERATED_API_KEY': {api_key_to_use}")
    print("\nIf you need to use this API key in a new shell session, please export it manually:")
    print(f"  For Linux/macOS: export GENERATED_API_KEY=\"{api_key_to_use}\"")
    print(f"  For Windows (CMD): set GENERATED_API_KEY=\"{api_key_to_use}\"")
    print(f"  For Windows (PowerShell): $env:GENERATED_API_KEY=\"{api_key_to_use}\"")

    print("\n--- 3Scale API Automation Script Completed ---")

if __name__ == "__main__":
    # Removed redundant import here as it's now at the top
    main()
