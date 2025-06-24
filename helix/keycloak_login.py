import os
import requests
import getpass
import json

def get_env_variable(var_name: str, optional: bool = False) -> str:
    """
    Retrieves an environment variable.
    Exits if the variable is not set and is not optional.
    """
    value = os.getenv(var_name)
    if value is None and not optional:
        print(f"Error: Environment variable '{var_name}' is not set.")
        print("Please set the following environment variables before running:")
        print("  KEYCLOAK_URL          (e.g., https://your-keycloak-instance.com)")
        print("  KEYCLOAK_REALM        (e.g., your_realm_name)")
        print("  KEYCLOAK_CLIENT_ID    (e.g., your_client_id_for_this_app)")
        print("  KEYCLOAK_CLIENT_SECRET (Optional, if your client is confidential)")
        print("  THREESCALE_ADMIN_API_URL (e.g., https://your-admin-portal.3scale.net)")
        print("  THREESCALE_ADMIN_API_KEY (Your 3scale Admin Portal API Key)")
        exit(1)
    return value

def sso_login():
    """
    Performs a login to Red Hat SSO (Keycloak) using the
    Resource Owner Password Credentials (ROPC) flow,
    then attempts to access a 3scale Admin API to list services
    and optionally create a new developer account.
    """
    print("--- Red Hat SSO Login ---")

    # 1. Get required environment variables
    keycloak_url = get_env_variable("KEYCLOAK_URL")
    keycloak_realm = get_env_variable("KEYCLOAK_REALM")
    keycloak_client_id = get_env_variable("KEYCLOAK_CLIENT_ID")
    keycloak_client_secret = get_env_variable("KEYCLOAK_CLIENT_SECRET", optional=True)
    threescale_admin_api_url = get_env_variable("THREESCALE_ADMIN_API_URL")
    threescale_admin_api_key = get_env_variable("THREESCALE_ADMIN_API_KEY")


    # Construct the Keycloak token endpoint URL
    token_url = f"{keycloak_url}/realms/{keycloak_realm}/protocol/openid-connect/token"

    print(f"\nAttempting to connect to Keycloak at: {token_url}")
    print(f"Using Keycloak Client ID: {keycloak_client_id}")
    if keycloak_client_secret:
        print("Keycloak Client Secret will be used.")
    else:
        print("No Keycloak Client Secret provided (assuming public client or not required).")


    # 2. Ask for Keycloak username and password
    username = input("Enter your Red Hat SSO Username: ")
    password = getpass.getpass("Enter your Red Hat SSO Password: ")

    # 3. Prepare the POST request payload for ROPC flow
    payload = {
        "grant_type": "password",
        "client_id": keycloak_client_id,
        "username": username,
        "password": password,
        "scope": "openid profile email" # Requesting standard OIDC scopes
    }

    # Add client secret to payload if it exists
    if keycloak_client_secret:
        payload["client_secret"] = keycloak_client_secret

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    access_token = None
    try:
        # 4. Make the HTTP POST request to the Keycloak token endpoint
        print("\nSending login request to Keycloak...")
        response = requests.post(token_url, data=payload, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        # 5. Parse the JSON response
        token_data = response.json()
        access_token = token_data.get('access_token')

        # 6. Print the tokens
        print("\n--- Keycloak Login Successful! ---")
        print("Received Tokens:")
        print(f"Access Token (Bearer): {access_token[:30]}... (truncated)")
        print(f"Expires In (seconds): {token_data.get('expires_in')}")
        print(f"Refresh Token: {token_data.get('refresh_token')[:30]}... (truncated)")
        print(f"ID Token: {token_data.get('id_token')[:30]}... (truncated)")

    except requests.exceptions.HTTPError as http_err:
        print(f"\nHTTP Error during Keycloak login: {http_err}")
        try:
            error_details = response.json()
            print("Keycloak Error Details:")
            print(json.dumps(error_details, indent=2))
        except json.JSONDecodeError:
            print(f"Could not decode Keycloak error response: {response.text}")
        return # Exit if Keycloak login fails
    except requests.exceptions.ConnectionError as conn_err:
        print(f"\nConnection Error: Could not connect to Keycloak server. Check URL or network.")
        print(conn_err)
        return # Exit if Keycloak login fails
    except requests.exceptions.Timeout as timeout_err:
        print(f"\nTimeout Error: Keycloak request timed out.")
        print(timeout_err)
        return # Exit if Keycloak login fails
    except requests.exceptions.RequestException as req_err:
        print(f"\nAn unexpected error occurred during Keycloak login: {req_err}")
        return # Exit if Keycloak login fails
    except Exception as e:
        print(f"\nAn unexpected error occurred during Keycloak login: {e}")
        return # Exit if Keycloak login fails

    # --- Access 3scale API to list services (Existing functionality) ---
    print("\n--- Attempting to access 3scale Admin API (List Services) ---")
    threescale_services_url = f"{threescale_admin_api_url}/admin/api/services.json"

    # For listing services, we might or might not need the Keycloak access token
    # depending on how 3scale is configured. If 3scale Admin API uses its own
    # API key, then the Keycloak token is not strictly necessary here,
    # but we keep it for consistency if it were an integrated scenario.
    threescale_list_headers = {
        "Authorization": f"Bearer {access_token}", # May or may not be required by 3scale for this endpoint
        "Accept": "application/json"
    }
    # For listing services, we'll primarily rely on the access_token received from Keycloak.
    # If this fails and 3scale Admin API requires its own API key for listing,
    # the error message will guide the user.

    try:
        print(f"Accessing 3scale Services API at: {threescale_services_url}")
        threescale_response = requests.get(threescale_services_url, headers=threescale_list_headers)
        threescale_response.raise_for_status()

        services_data = threescale_response.json()
        print("\n--- 3scale Services List Successful! ---")
        print("Services found (first 5 entries):")
        if services_data and isinstance(services_data, dict) and 'services' in services_data and isinstance(services_data['services'], list):
            for i, service in enumerate(services_data['services'][:5]):
                print(f"  Service {i+1}: ID={service.get('service', {}).get('id')}, Name={service.get('service', {}).get('name')}")
            if len(services_data['services']) > 5:
                print(f"  ...and {len(services_data['services']) - 5} more services.")
        else:
            print("No services found or unexpected response format.")
            print(json.dumps(services_data, indent=2))
    except requests.exceptions.HTTPError as http_err:
        print(f"\nHTTP Error during 3scale Services List API access: {http_err}")
        try:
            error_details = threescale_response.json()
            print("3scale Error Details:")
            print(json.dumps(error_details, indent=2))
        except json.JSONDecodeError:
            print(f"Could not decode 3scale error response: {threescale_response.text}")
        print("\nNote: Listing services might require a different authentication method or specific permissions.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during 3scale Services List API access: {e}")


    # --- Create 3scale Developer Account (New Functionality - Option 2) ---
    create_account_choice = input("\nDo you want to create a new 3scale Developer Account? (yes/no): ").lower()

    if create_account_choice == 'yes':
        print("\n--- Creating a new 3scale Developer Account ---")
        print("Please provide details for the new 3scale account:")
        account_name = input("Enter Account Name (e.g., My New Dev Company): ")
        account_org_name = input("Enter Organization Name (e.g., NewDevCorp): ")
        account_email = input("Enter Account Email (e.g., dev@example.com): ")
        account_username = input("Enter Account Username (e.g., newdevuser): ")

        threescale_create_account_url = f"{threescale_admin_api_url}/admin/api/accounts.json"

        # The 3scale Admin API requires its own API key, typically passed as 'access_token' parameter.
        # This is distinct from the Keycloak access_token.
        threescale_account_payload = {
            "access_token": threescale_admin_api_key,
            "account[name]": account_name,
            "account[org_name]": account_org_name,
            "account[email]": account_email,
            "account[username]": account_username,
            # Add other optional fields as needed, e.g., "account[state]=active"
        }

        threescale_account_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        try:
            print(f"Sending request to create 3scale account at: {threescale_create_account_url}")
            create_response = requests.post(threescale_create_account_url, data=threescale_account_payload, headers=threescale_account_headers)
            create_response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            new_account_data = create_response.json()
            print("\n--- 3scale Developer Account Created Successfully! ---")
            print("New Account Details:")
            # 3scale API response structure for account creation
            if new_account_data and 'account' in new_account_data:
                account_info = new_account_data['account']
                print(f"  ID: {account_info.get('id')}")
                print(f"  Name: {account_info.get('name')}")
                print(f"  Org Name: {account_info.get('org_name')}")
                print(f"  Email: {account_info.get('email')}")
                print(f"  Username: {account_info.get('username')}")
                print(f"  State: {account_info.get('state')}")
            else:
                print("Unexpected response structure:")
                print(json.dumps(new_account_data, indent=2))

        except requests.exceptions.HTTPError as http_err:
            print(f"\nHTTP Error during 3scale Account Creation: {http_err}")
            try:
                error_details = create_response.json()
                print("3scale Error Details:")
                print(json.dumps(error_details, indent=2))
            except json.JSONDecodeError:
                print(f"Could not decode 3scale error response: {create_response.text}")
            print("\nPossible reasons for 3scale account creation failure:")
            print("1. The THREESCALE_ADMIN_API_KEY is incorrect or lacks 'Account Management API' (Read & Write) permissions.")
            print("2. Required fields (name, org_name, email, username) are missing or invalid.")
            print("3. An account with the same email or username already exists.")
            print("4. The THREESCALE_ADMIN_API_URL or the /accounts.json path is incorrect.")
        except Exception as e:
            print(f"\nAn unexpected error occurred during 3scale Account Creation: {e}")
    else:
        print("\nSkipping 3scale Developer Account creation.")

if __name__ == "__main__":
    sso_login()
