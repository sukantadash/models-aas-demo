#python3 -m venv venv
#source venv/bin/activate

#Login to ocp

#Step -1 Login to the cluster

oc login -u admin -p  https://api.cluster-hz554.hz554.sandbox500.opentlc.com:6443

#Step -2 Install openshift AI

oc apply -k ./components/openshift-ai/operator/overlays/fast

# make sure below pods are running
oc get pods -n redhat-ods-operator

oc apply -k ./components/openshift-ai/instance/overlays/fast


#Step -3 Install Serverless and service mess operators to enable single model deployments


# install service mesh operator
oc apply -k ./components/openshift-servicemesh/operator/overlays/stable

# install serverless operator

oc apply -k ./components/openshift-serverless/operator/overlays/stable



# We'll be using the single stack serving in OpenShift AI so we'll want to use a trusted certificate instead of a self-signed one. This will allow our chatbot to access the model inference endpoint.


oc get secrets -n openshift-ingress | grep cert


oc extract secret/<CERT_SECRET_FROM_ABOVE> -n openshift-ingress --to=ingress-certs --confirm

cd ingress-certs

oc create secret generic knative-serving-cert -n istio-system --from-file=. --dry-run=client -o yaml | oc apply -f -

cd ..


oc apply -k ./components/model-server/components-serving



# Step-4 install minio

# create  ai-models namespace to store all models

oc new-project ai-models

oc apply -n ai-models -f setup-s3.yaml


# create  vllm-granite namespace to deploy the model

oc new-project vllm-granite

#update s3-ds.sh to have proper namespaces

oc apply -f s3-ds.yaml


# Step-5 Copy the model to models bucket

## make sure aws cli installed
aws configure

# use minio api port  from route not console
aws s3 sync ./models/granite-3.3-2b-instruct s3://models/granite-3.3-2b-instruct --endpoint-url https://minio-s3-ai-models.apps.cluster-wbmfx.wbmfx.sandbox1988.opentlc.com



# Step-6 Create model serving runtime (infernce service)

oc apply -f ./vllm-model-inference/granite-instruct-vllm-raw-2.19.yaml -n vllm-granite

#Step-7 Test the model inferencing

curl -X 'POST' \
    'https://vllm-server-vllm-granite.apps.cluster-wbmfx.wbmfx.sandbox1988.opentlc.com/v1/completions' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer ' \
    -d '{
    "model": "vllm-server",
    "prompt": "San Francisco is a",
    "max_tokens": 15,
    "temperature": 0
}'

curl -X 'GET' \
  'https://vllm-server-vllm-granite.apps.cluster-wbmfx.wbmfx.sandbox1988.opentlc.com/v1/models' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer '

#curl -L 'https://vllm-server-vllm-granite.apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com/v1/swagger.json' \
#  -H 'Authorization: Bearer '


#Step-7 3scale install

# Need storage like NFS or ODF for RWX

#Minimum 16 vCPUs and 64 GiB RAM per node.

#One or more unformatted disks (SSD/NVMe recommended) attached to each worker node for ODF storage.

oc get nodes

oc get machinesets -n openshift-machine-api 
oc edit machineset <machineset-name> -n openshift-machine-api #edit replicas to 3 to add one more worker nodes

#Wait
oc get nodes

#----------- Manual Step Begin ------
#install odf operator. Install manually from console. Below step is not working. Need to retest. 
#Create storage manually from console. select the strorage class, and select all 3 nodes all other options default.

oc apply -k ./components/odf/operator/overlays/stable
# make sure below pods are running
oc get pods -n openshift-storage 

oc apply -f ./components/odf/cluster/instance.yaml

# Wait for new sc it will take 15 to 20 mins

oc get storageclass
#----------- Manual Step End ------


#install the operators 3scale 


oc apply -k ./components/3scale/operator/overlays/fast

oc project 3scale

# make sure below pods are running
oc get pods -n 3scale
# wildcardDomain: apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com # Change this to your wildcard domain in the file ./components/cluster/cluster/instance.yaml
#Change storage class
oc apply -f ./components/3scale/cluster/instance.yaml

cd ./3scale/config

oc create secret generic llm-metrics \
    -n 3scale \
--from-file=./apicast-policy.json \
--from-file=./custom_metrics.lua \
--from-file=./init.lua \
--from-file=./llm.lua \
--from-file=./portal_client.lua \
--from-file=./response.lua \
&& oc label secret llm-metrics apimanager.apps.3scale.net/watched-by=apimanager

cd ../../


for resource in $(oc api-resources --verbs=list --namespaced -o name --sort-by name | grep -v "events"); do \
  oc get $resource -n 3scale --ignore-not-found -o custom-columns=KIND:.kind,NAME:.metadata.name; \
done > output2.txt




oc get secret system-seed -n 3scale \
--template={{.data.ADMIN_PASSWORD}} | base64 -d; echo

#3Scale admin Setup
1. Create a Tenant and perform below steps under the tenant.
2. Create Product 1.1. Create Application Plan
3. Publish the plan
4. Create Backend
5. Create API docs from the api OAS JSON file
6. Link Product to Backend
7. Single Sign-On (SSO) for the developer portal
8. Deploy the developer portal liquid files in the Audience -> content
#Developer Portal :- Users can signup

8. Create Application by linking user, app plan, product -> Developer Portal


#install the operators sso 
#RHSSO operator also installs Openshift Elastic Search operator
oc apply -k ./components/redhat-sso/operator/overlays/stable


# make sure below pods are running
oc get pods -n rh-sso


oc project rh-sso

oc apply -f ./components/redhat-sso/cluster/02_keycloak.yaml -n rh-sso


oc get secret credential-rh-sso -n rh-sso \
--template={{.data.ADMIN_USERNAME}} | base64 -d; echo

oc get secret credential-rh-sso -n rh-sso \
--template={{.data.ADMIN_PASSWORD}} | base64 -d; echo



oc apply -f ./components/redhat-sso/cluster/03_realm.yaml -n rh-sso

#oc apply -f ./components/redhat-sso/cluster/04_user.yaml


export OCP_USER="admin"
export OCP_PASS="MjUzNDYw"
export OCP_URL="https://api.cluster-wbmfx.wbmfx.sandbox1988.opentlc.com:6443"

./components/redhat-sso/cluster/inject_rhsso_ca.sh

