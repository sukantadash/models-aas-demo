#python3 -m venv venv
#source venv/bin/activate

#Login to ocp

#Step -1 Login to the cluster

oc login -u admin -p zE4iYNKhv6wuZtYv https://api.cluster-hz554.hz554.sandbox500.opentlc.com:6443

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

oc create ns ai-models

oc apply -n ai-models -f setup-s3.yaml


# create  vllm-granite namespace to deploy the model

oc create ns vllm-granite

#update s3-ds.sh to have proper namespaces

oc apply -f s3-ds.yaml


# Step-5 Copy the model to models bucket

## make sure aws cli installed
aws configure

# use api port
aws s3 sync ./granite-3.3-2b-instruct s3://models/granite-3.3-2b-instruct --endpoint-url https://minio-s3-ai-models.apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com



# Step-6 Create model serving runtime (infernce service)

oc apply -f ./vllm-model-inference/granite-instruct-vllm-raw-2.19.yaml -n vllm-granite

#Step-7 Test the model inferencing

curl -X 'POST' \
    'https://vllm-server-vllm-granite.apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com/v1/completions' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer sha256~vX7AwzqninjzFtRUmfi5psuDVO382HLS4-c2pygyK4o' \
    -d '{
    "model": "vllm-server",
    "prompt": "San Francisco is a",
    "max_tokens": 15,
    "temperature": 0
}'

curl -X 'GET' \
  'https://vllm-server-vllm-granite.apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com/v1/models' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer sha256~vX7AwzqninjzFtRUmfi5psuDVO382HLS4-c2pygyK4o'

#curl -L 'https://vllm-server-vllm-granite.apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com/v1/swagger.json' \
#  -H 'Authorization: Bearer sha256~hW_R_Sqr-x4xvVbAMMYewNvt8Hy6NAnjXqUdczPDY1E'


#Step-7 3scale install

# Need storage like NFS or ODF for RWX

#Minimum 16 vCPUs and 64 GiB RAM per node.

#One or more unformatted disks (SSD/NVMe recommended) attached to each worker node for ODF storage.


oc get machinesets -n openshift-machine-api 
oc edit machineset <machineset-name> -n openshift-machine-api #edit replicaset to 2 to add one more worker nodes

#install odf operator

oc apply -k ./components/odf/operator/overlays/stable
oc apply -k ./components/odf/instance/overlays/stable


#install the operators 3scale 


cat <<EOF | oc apply -f -
apiVersion: apps.3scale.net/v1alpha1
kind: APIManager
metadata:
  name: 3scale
  namespace: 3scale  # Must match Operator's namespace if namespaced
spec:
  wildcardDomain: apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com  # Replace with your domain
  tenantName: maas
  system:
    fileStorage:
      persistentVolumeClaim:
        storageClassName: ocs-storagecluster-cephfs  
EOF
# to retrive pwd for admin for api management admin url


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
#install the operators 3scale-apicast