#python3 -m venv venv
#source venv/bin/activate

#Login to ocp

#Step -1 Login to the cluster

oc login -u admin https://api.cluster-hz554.hz554.sandbox500.opentlc.com:6443


#########SKIP##############

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


############SKIP TILL HERE##############

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

# use minio api port  from route not console models in s3 bucket shouldnt have any 
# other special character than '-'
aws s3 sync ./models/granite-3.3-2b-instruct s3://models/granite-33-2b-instruct --endpoint-url https://minio-s3-ai-models.apps.cluster-2j5v9.2j5v9.sandbox3159.opentlc.com


# Step-6 Create model serving runtime (infernce service)
oc apply -f ./vllm-model-inference/granite-33-2b-instruct.yaml -n vllm-granite
oc apply -f ./vllm-model-inference/granite-33-8b-instruct.yaml -n vllm-granite

#Step-6 Test the model inferencing
curl -X 'POST' \
    'http://granite-33-2b-instruct.vllm-granite.svc.cluster.local/v1/completions' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{
    "model": "granite-33-2b-instruct",
    "prompt": "San Francisco is a",
    "max_tokens": 15,
    "temperature": 0
}'

curl -X 'GET' \
  'http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/v1/models' \
  -H 'accept: application/json'
#  -H 'Authorization: Bearer '

#get the openapi.json file
curl -O http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/openapi.json


#Step-8 3scale install

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

#oc apply -k ./components/odf/operator/overlays/stable
# make sure below pods are running
oc get pods -n openshift-storage 

#Manually create the instance
#oc apply -f ./components/odf/cluster/instance.yaml
# Wait for new sc it will take 15 to 20 mins

oc get storageclass
#----------- Manual Step End ------

#install the operators 3scale 
oc apply -k ./components/3scale/operator/overlays/fast
oc project 3scale

# make sure below pods are running
oc get pods -n 3scale

cd ./3scale/config
oc create secret generic llm-metrics \
    -n 3scale \
--from-file=./apicast-policy.json \
--from-file=./custom_metrics.lua \
--from-file=./init.lua \
--from-file=./llm.lua \
--from-file=./portal_client.lua \
--from-file=./response.lua \
&& oc label secret -n 3scale llm-metrics apimanager.apps.3scale.net/watched-by=apimanager
cd ../../


# wildcardDomain: apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com # Change this to your wildcard domain in the file ./components/cluster/cluster/instance.yaml
#Change storage class
oc apply -f ./components/3scale/cluster/instance.yaml
oc apply -f ./components/3scale/cluster/llm-metrics-policy.yaml

# for resource in $(oc api-resources --verbs=list --namespaced -o name --sort-by name | grep -v "events"); do \
#   oc get $resource -n 3scale --ignore-not-found -o custom-columns=KIND:.kind,NAME:.metadata.name; \
# done > output2.txt


oc get secret system-seed -n 3scale \
--template={{.data.ADMIN_PASSWORD}} | base64 -d; echo

#3Scale admin Setup

1. delete the backend API
2. Create product granite-33-2b-instruct
3. create backend granite-33-2b-instruct https://granite-33-2b-instruct.vllm-granite.svc.cluster.local
4. Delete the product API granite-33-2b-instruct

Repeat the below steps for each product
5. Product -> Integration->link the backend
6. Product -> ActiveDocs
7. Product -> the application plan and publish
8. Product -> Integration -> Settings, Polices, Methods and Metrics and Mapping Rules Define ActiveDocs
9. Product -> Integration -> Configuration promote to staging and production

10. Developer portal Setup


As the access to the 3scale Admin REST APIs is protected, we need to get an access-token as well as the host first
```bash
export ACCESS_TOKEN=`oc get secret system-seed -o json -n 3scale | jq -r '.data.ADMIN_ACCESS_TOKEN' | base64 -d`
export ADMIN_HOST=`oc get route -n 3scale | grep maas-admin | awk '{print $2}'`
```
For convenience we set an alias first and then launch the 3scale CMS tool
```bash
alias cms='podman run --userns=keep-id:uid=185 -it --rm -v ./3scale/portal:/cms:Z ghcr.io/fwmotion/3scale-cms:latest'
cms -k --access-token=${ACCESS_TOKEN} ${ACCESS_TOKEN} https://${ADMIN_HOST}/ upload --delete-missing --layout=/l_main_layout.html.liquid

#Step-9 install the operator RH SSO 
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


# RHSSO SSO Setup

#create a ciient, client id : 3scale Client Protocol: openid-connect 

#Add Mapper: Add builtin email verified 
#Add Mapper: org_type as string
#RHSSO config in 3scale developer portal

#Github identity provider integration

#Step-9 Update the 3scale developer portal to use RH SSO
#Update Audience -> Developer Portal -> settings -> SSO Integration -> RH SSO Publish



#Step-10 Test the 3scale API

curl -X 'POST' \
    'https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/completions' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer *************' \
    -d '{
    "model": "granite-33-2b-instruct",
    "prompt": "San Francisco is a",
    "max_tokens": 15,
    "temperature": 0
}'

curl -X 'GET' \
  'https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/models' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer ***********'