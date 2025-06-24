import os
import requests
import xml.etree.ElementTree as ET

# --- Helper Functions ---
def get_env_variable(var_name):
    """
    Reads an environment variable and exits if not found.
    """
    value = os.getenv(var_name)
    if not value:
        print(f"Error: Environment variable '{var_name}' not set.")
        print(f"Please set '{var_name}' before running the script.")
        exit(1)
    return value

def make_api_call(method, endpoint, params=None, data=None, headers=None):
    """
    Makes an API call to the 3Scale Admin API.
    Handles common response parsing and error checking.
    """
    base_api_url = get_env_variable("THREESCALE_API_ENDPOINT") # Get base URL from environment variable
    url = f"{base_api_url}{endpoint}"
    print(f"\n--- Making {method} request to: {url} ---")
    # print(f"Parameters: {params}") # Keep parameters private if they contain sensitive info
    # print(f"Data: {data}") # Keep data private if it contains sensitive info

    try:
        if method == "GET":
            response = requests.get(url, params=params, headers=headers)
        elif method == "POST":
            response = requests.post(url, params=params, data=data, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, params=params, headers=headers)
        else:
            print(f"Error: Unsupported HTTP method '{method}'.")
            return None

        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        print(f"Response Status Code: {response.status_code}")
        # print(f"Response Content:\n{response.text}") # Uncomment for debugging full response

        # Parse XML response
        root = ET.fromstring(response.text)
        return root

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {e}")
        print(f"Response Body: {response.text}")
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

def find_account_by_soeid(soeid, access_token):
    """
    Checks if an SOEID exists in 3Scale by finding the account.
    Returns account ID if found, otherwise None.
    """
    print(f"\nChecking if SOEID '{soeid}' exists in 3Scale...")
    endpoint = "accounts/find.xml"
    params = {
        "access_token": access_token,
        "username": soeid  # Assuming SOEID maps to 'username' for account finding
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

def get_account_applications(account_id, access_token):
    """
    Gets all registered applications for a given account.
    Returns a list of dictionaries with application details.
    """
    print(f"\nGetting applications for Account ID: {account_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    params = {
        "access_token": access_token
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

def get_application_plans(service_id, access_token):
    """
    Gets application plans for a specific service.
    Returns a list of dictionaries with plan ID and name.
    """
    print(f"\nGetting application plans for Service ID: {service_id}...")
    endpoint = f"services/{service_id}/application_plans.xml"
    params = {
        "access_token": access_token
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

def register_application(account_id, plan_id, app_name, access_token):
    """
    Registers a new application for an account, effectively creating an API key.
    Returns the application ID and API key if successful.
    """
    print(f"\nRegistering new application '{app_name}' for Account ID: {account_id} with Plan ID: {plan_id}...")
    endpoint = f"accounts/{account_id}/applications.xml"
    
    # Form-urlencoded data
    data_payload = {
        "name": app_name,
        "plan_id": plan_id,
        "access_token": access_token
    }
    
    root = make_api_call("POST", endpoint, data=data_payload)

    if root is not None:
        application_id = root.find("id")
        api_key = root.find("user_key") # Assuming 'user_key' holds the API key for applications
        
        if application_id is not None and api_key is not None:
            print(f"Application registered successfully!")
            print(f"Application ID: {application_id.text}")
            print(f"Generated API Key: {api_key.text}")
            return {"app_id": application_id.text, "api_key": api_key.text}
        else:
            print("Failed to get application ID or API key from response.")
            return None
    return None

# --- Main Program Logic ---
def main():
    print("--- Program 2: Create API Key (with existing key check) ---")

    # 1. Read SOEID, API Access Token, API Endpoint, and Selected Service ID from environment variables
    soeid = get_env_variable("SOEID")
    api_access_token = get_env_variable("API_ACCESS_TOKEN")
    api_endpoint = get_env_variable("THREESCALE_API_ENDPOINT") # Ensure this is set
    selected_service_id = get_env_variable("SELECTED_SERVICE_ID") # From Program 1 output or manual set

    print(f"Using API Endpoint: {api_endpoint}")
    print(f"SOEID: {soeid}")
    print(f"API Access Token: {'*' * len(api_access_token)}") # Mask for security
    print(f"Selected Service ID: {selected_service_id}")

    # Ensure the account exists and get the account_id
    account_id = find_account_by_soeid(soeid, api_access_token)
    if not account_id:
        print(f"Error: Account for SOEID '{soeid}' not found. Cannot proceed with API key creation.")
        exit(1)

    # 2. Get application plans for the selected service
    application_plans = get_application_plans(selected_service_id, api_access_token)

    if not application_plans:
        print(f"\nNo application plans found for service ID '{selected_service_id}'. Cannot create API key.")
        exit(1)

    # For demonstration, we'll assume the first application plan is the one we're interested in.
    # In a real scenario, you might have logic to select a specific plan.
    target_plan = application_plans[0] 
    print(f"\nTargeting Application Plan:")
    print(f"  ID: {target_plan['id']}")
    print(f"  Name: {target_plan['name']}")

    # Check if the plan is already registered for the user
    existing_applications = get_account_applications(account_id, api_access_token)
    existing_api_key = None

    for app in existing_applications:
        # Check if an application for this service_id and plan_id already exists
        if app.get("service_id") == selected_service_id and app.get("plan_id") == target_plan["id"]:
            print(f"\nFound existing registration for Service ID '{selected_service_id}' and Plan ID '{target_plan['id']}'.")
            existing_api_key = app["user_key"]
            print(f"Returning existing API Key: {existing_api_key}")
            break
    
    if existing_api_key:
        api_key_to_use = existing_api_key
        print("\n--- API Key retrieved successfully (existing). ---")
    else:
        # If not registered, proceed with new registration
        print("\nPlan is not registered for the user. Registering a new application...")
        app_name = f"helix-app-{soeid}-{selected_service_id}-{target_plan['id']}-auto" 
        
        new_app_details = register_application(
            account_id=account_id,
            plan_id=target_plan["id"],
            app_name=app_name,
            access_token=api_access_token
        )

        if new_app_details:
            api_key_to_use = new_app_details['api_key']
            print(f"\n--- API Key generated successfully (new). ---")
        else:
            print("\n--- ERROR: Failed to register application and create API Key. ---")
            exit(1)

    # Set the API key in an environment variable (for current process)
    os.environ["GENERATED_API_KEY"] = api_key_to_use
    print(f"\nAPI Key set in environment variable 'GENERATED_API_KEY': {api_key_to_use}")
    print("\nIf you need to use this API key in a new shell session, please export it manually:")
    print(f"  For Linux/macOS: export GENERATED_API_KEY=\"{api_key_to_use}\"")
    print(f"  For Windows (CMD): set GENERATED_API_KEY=\"{api_key_to_use}\"")
    print(f"  For Windows (PowerShell): $env:GENERATED_API_KEY=\"{api_key_to_use}\"")


    print("\n--- Program 2 Ended ---")

if __name__ == "__main__":
    main()
