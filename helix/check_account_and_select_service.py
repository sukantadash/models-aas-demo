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

def list_services(access_token):
    """
    Lists all available services (models) from 3Scale.
    Returns a list of dictionaries with service ID and name.
    """
    print("\nListing all available services (models)...")
    endpoint = "services.xml"
    params = {
        "access_token": access_token,
        "page": 1,
        "per_page": 500  # Adjust as needed to get all services
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

# --- Main Program Logic ---
def main():
    print("--- Program 1: Check Account and Select Service ---")

    # 1. Read SOEID, API Access Token, and API Endpoint from environment variables
    soeid = get_env_variable("SOEID")
    api_access_token = get_env_variable("API_ACCESS_TOKEN")
    api_endpoint = get_env_variable("THREESCALE_API_ENDPOINT") # Ensure this is set

    print(f"Using API Endpoint: {api_endpoint}")
    print(f"SOEID: {soeid}")
    print(f"API Access Token: {'*' * len(api_access_token)}") # Mask for security

    # 2. Check if SOEID exists in 3Scale (Find Account)
    account_id = find_account_by_soeid(soeid, api_access_token)

    if account_id:
        print(f"\nSOEID '{soeid}' exists in 3Scale.")

        # 3. Get a list of selected services and prompt the user to select one
        services = list_services(api_access_token)

        if services:
            print("\nAvailable Services:")
            for i, service in enumerate(services):
                print(f"  {i+1}. ID: {service['id']}, Name: {service['name']}")

            while True:
                try:
                    choice = int(input("Enter the number of the service you want to select: "))
                    if 1 <= choice <= len(services):
                        selected_service = services[choice - 1]
                        print(f"\nYou selected Service:")
                        print(f"  ID: {selected_service['id']}")
                        print(f"  Name: {selected_service['name']}")
                        print(f"\nNOTE: Please use the following Service ID for the second program (create_api_key.py):")
                        print(f"  SELECTED_SERVICE_ID={selected_service['id']}")
                        # You might also want to save this to a file or another env var for automation
                        break
                    else:
                        print("Invalid choice. Please enter a number within the range.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        else:
            print("\nNo services (models) found in your 3Scale account.")
            print("Please ensure services are configured or try again later.")
    else:
        # If SOEID does not exist
        print(f"\nSOEID '{soeid}' does NOT exist in 3Scale.")
        print("Please create your account by logging in to the API management portal: www.3scale.com")

    print("\n--- Program 1 Ended ---")

if __name__ == "__main__":
    main()