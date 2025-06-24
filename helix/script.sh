#python3 -m venv venv
#source venv/bin/activate

pip install -r requirements.txt


export KEYCLOAK_URL="https://keycloak-rh-sso.apps.cluster-2j5v9.2j5v9.sandbox3159.opentlc.com/auth"
export KEYCLOAK_REALM="maas"
export KEYCLOAK_CLIENT_ID="3scale"
export KEYCLOAK_CLIENT_SECRET=""
export THREESCALE_ADMIN_API_URL="https://maas-admin.apps.cluster-2j5v9.2j5v9.sandbox3159.opentlc.com/admin/api/"
export THREESCALE_ADMIN_API_KEY=""

python threescale_automation.py