# Models as a Services Deployment Guide: 3scale API Management with Red Hat SSO (MaaS)

This document provides a step-by-step guide for deploying and configuring Models as a Services using 3scale API Management and integrating it with Red Hat Single Sign-On (RH-SSO) on an OpenShift cluster. This setup is crucial for managing APIs and securing user authentication in a Model as a Service (MaaS) environment. Follow the steps sequentially to ensure a successful deployment.

---

## 1. Environment Setup and Cluster Login

Before starting the deployment, ensure your environment is set up and you can access your OpenShift cluster.

### Steps:

1.  **Login to OpenShift Cluster:**
    ```bash
    oc login -u admin [https://api.cluster-hz554.hz554.sandbox500.opentlc.com:6443](https://api.cluster-hz554.hz554.sandbox500.opentlc.com:6443)
    ```

---

## 2. OpenShift AI, Serverless, and Service Mesh Installation

This section covers the installation of OpenShift AI, Serverless, and Service Mesh operators, which are crucial for model deployment and serving.

### Steps:

1.  **Install OpenShift AI Operator and Instance:**
    ```bash
    oc apply -k ./components/openshift-ai/operator/overlays/fast
    # Make sure below pods are running
    oc get pods -n redhat-ods-operator
    oc apply -k ./components/openshift-ai/instance/overlays/fast
    ```
2.  **Install Service Mesh Operator:**
    ```bash
    oc apply -k ./components/openshift-servicemesh/operator/overlays/stable
    ```
3.  **Install Serverless Operator:**
    ```bash
    oc apply -k ./components/openshift-serverless/operator/overlays/stable
    ```
4.  **Configure Trusted Certificates for Model Serving:**
    We'll be using single stack serving in OpenShift AI, so we'll use a trusted certificate instead of a self-signed one to allow the chatbot to access the model inference endpoint.
    ```bash
    oc get secrets -n openshift-ingress | grep cert
    oc extract secret/<CERT_SECRET_FROM_ABOVE> -n openshift-ingress --to=ingress-certs --confirm
    cd ingress-certs
    oc create secret generic knative-serving-cert -n istio-system --from-file=. --dry-run=client -o yaml | oc apply -f -
    cd ..
    oc apply -k ./components/model-server/components-serving
    ```

---

## 3. MinIO and Model Deployment

This section guides you through installing MinIO for model storage and deploying a sample model.

### Steps:

1.  **Install MinIO and Create Namespaces:**
    ```bash
    oc new-project ai-models # Create ai-models namespace to store all models
    oc apply -n ai-models -f setup-s3.yaml
    oc new-project vllm-granite # Create vllm-granite namespace to deploy the model
    # Update s3-ds.sh to have proper namespaces (if necessary)
    oc apply -f s3-ds.yaml
    ```
2.  **Copy the Model to MinIO (S3 Bucket):**
    Ensure `aws cli` is installed and configured.
    ```bash
    aws configure
    # Use minio API port from route, not console. Models in S3 bucket shouldn't have any special character other than '-'.
    aws s3 sync ./models/granite-3.3-2b-instruct s3://models/granite-33-2b-instruct --endpoint-url [https://minio-s3-ai-models.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com](https://minio-s3-ai-models.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com)
    ```
3.  **Create Model Serving Runtime (Inference Service):**
    ```bash
    oc apply -f ./vllm-model-inference/granite-33-2b-instruct.yaml -n vllm-granite
    ```
4.  **Test the Model Inferencing:**
    Test this command in a pod in the project vllm-granite. As these are service url, they are not accessible ourside the project.

    ```bash
    curl -X 'POST' \
        '[http://granite-33-2b-instruct.vllm-granite.svc.cluster.local/v1/completions](http://granite-33-2b-instruct.vllm-granite.svc.cluster.local/v1/completions)' \
        -H 'accept: application/json' \
        -H 'Content-Type: application/json' \
        -d '{
        "model": "granite-33-2b-instruct",
        "prompt": "San Francisco is a",
        "max_tokens": 15,
        "temperature": 0
    }'

    curl -X 'GET' \
      '[http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/v1/models](http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/v1/models)' \
      -H 'accept: application/json'
    #  -H 'Authorization: Bearer '

    # Get the openapi.json file
    curl -O [http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/openapi.json](http://granite-33-2b-instruct-predictor.vllm-granite.svc.cluster.local/openapi.json)
    ```

---

## 4. 3scale API Management Deployment and Configuration

This section covers the installation of the 3scale API Management operator and its configuration for managing your APIs.

### Steps:

1.  **Prepare for 3scale Installation (Storage Requirements):**
    You need storage like NFS or ODF for RWX. Minimum 16 vCPUs and 64 GiB RAM per node are recommended, along with one or more unformatted disks (SSD/NVMe recommended) attached to each worker node for ODF storage.
    ```bash
    oc get nodes
    oc get machinesets -n openshift-machine-api
    # To add more worker nodes, edit replicas to 3 (example):
    # oc edit machineset <machineset-name> -n openshift-machine-api
    # Wait for nodes to be ready:
    oc get nodes
    ```
2.  **Install ODF Operator (Manual Steps Recommended):**
    While programmatic installation is listed, manual installation from the OpenShift console is often more reliable for ODF. Create storage manually from the console by selecting the storage class and all three nodes, leaving other options as default.
    ```bash
    # oc apply -k ./components/odf/operator/overlays/stable # This step might not work, retest
    # Make sure below pods are running
    oc get pods -n openshift-storage
    # Manually create the ODF instance via console.
    # oc apply -f ./components/odf/cluster/instance.yaml # Wait for new storage class (15-20 mins)
    oc get storageclass
    ```
3.  **Install the 3scale Operator:**
    ```bash
    oc apply -k ./components/3scale/operator/overlays/fast
    oc project 3scale
    # Make sure below pods are running
    oc get pods -n 3scale
    ```
4.  **Create 3scale Metrics Secret:**
    ```bash
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
    ```
5.  **Apply 3scale Instance and Metrics Policy:**
    **IMPORTANT:** Before applying, update the `wildcardDomain` in `./components/3scale/cluster/instance.yaml` to match your OpenShift cluster's domain.
    ```bash
    # Example: wildcardDomain: apps.cluster-cbq4n.cbq4n.sandbox906.opentlc.com
    oc apply -f ./components/3scale/cluster/instance.yaml
    oc apply -f ./components/3scale/cluster/llm-metrics-policy.yaml
    ```
6.  **Retrieve 3scale Admin Password:**
    ```bash
    oc get secret system-seed -n 3scale \
    --template={{.data.ADMIN_PASSWORD}} | base64 -d; echo
    ```
7.  **Configure 3scale Admin Portal:**
    * Login to the 3scale administration portal using the retrieved credentials (Route starting with `https://maas-admin-apps....`). Close the initial wizard.
    * **Cleanup Default Backend and Product:**
        * In the **Products** section, click on the default **API** product, then **edit** it.
        * In the **Backends** section, **delete** the default **API Backend**.
        * You can also clean up any other unwanted default Products and Backends.
    * **Create Backend for Granite Model:**
        * In the **Backends** section, create a new backend for Granite. The **Private Base URL** is the service exposed by your model (e.g., `https://granite-33-2b-instruct.vllm-granite.svc.cluster.local`).
        * Repeat for any other models/endpoints you need to expose.
    * **Create Product for Granite Model:**
        * Create a separate **Product** (e.g., `granite-33-2b-instruct`) for each **Backend** you've configured.
    * **Configure Each Product:**
        * For each product, navigate to **Integration -> Settings**. Change **Auth user key** to `Authorization` and **Credentials location** to `As HTTP Basic Authentication`. Save changes.
        * **Link the corresponding Backend** to each Product.
        * Add **Policies** in this order:
            * **CORS Request Handling:** Set `ALLOW_HEADERS` to `Authorization, Content-type, Accept`, `allow_origin` to `*`, and `allow_credentials` to `checked`.
            * Optionally, add **LLM Monitor for OpenAI-Compatible token usage** (refer to its Readme for configuration).
            * Ensure **3scale APIcast** policy is present/enabled.
        * Add **Methods and Mapping Rules** for each API method/path (e.g., POST `/v1/chat/completions`).
    * **Promote Configuration:** From **Integration -> Configuration**, promote the configuration to **staging** then **production**.
    * **Application Plans Configuration:**
        * For each Product, go to **Applications -> Application Plans**.
        * Create a **new Application Plan**. Publish it and leave the **Default plan** to "No plan selected" to allow users to choose services.
        * In **Applications -> Settings -> Usage Rules**, set the **Default Plan** to `Default`.
    * **Developer Portal Setup:**
        * Switch to **Audience** section.
        * In **Developer Portal -> Settings -> Domains and Access**, remove the **Developer Portal Access Code**.
8.  **Update 3scale Developer Portal Content:**
    ```bash
    export ACCESS_TOKEN=`oc get secret system-seed -o json -n 3scale | jq -r '.data.ADMIN_ACCESS_TOKEN' | base64 -d`
    export ADMIN_HOST=`oc get route -n 3scale | grep maas-admin | awk '{print $2}'`
    alias cms='podman run --userns=keep-id:uid=185 -it --rm -v ./3scale/portal:/cms:Z ghcr.io/fwmotion/3scale-cms:latest'
    cms -k --access-token=${ACCESS_TOKEN} ${ACCESS_TOKEN} https://${ADMIN_HOST}/ upload --delete-missing --layout=/l_main_layout.html.liquid
    # Note: There is also a 'download' option if you want to make changes manually on the 3scale CMS portal first.
    ```

---

## 5. Red Hat Single Sign-On (RH-SSO) Installation and Configuration

This section outlines the deployment of the RH-SSO operator and its configuration for integrating with 3scale.

### Steps:

1.  **Install the RH-SSO Operator:**
    The RH-SSO operator also installs the OpenShift Elastic Search operator.
    ```bash
    oc apply -k ./components/redhat-sso/operator/overlays/stable
    # Make sure below pods are running
    oc get pods -n rh-sso
    oc project rh-sso
    ```
2.  **Apply Keycloak Instance and Realm Configuration:**
    ```bash
    oc apply -f ./components/redhat-sso/cluster/02_keycloak.yaml -n rh-sso
    oc apply -f ./components/redhat-sso/cluster/03_realm.yaml -n rh-sso
    ```
3.  **Retrieve RH-SSO Admin Credentials:**
    ```bash
    oc get secret credential-rh-sso -n rh-sso \
    --template={{.data.ADMIN_USERNAME}} | base64 -d; echo
    oc get secret credential-rh-sso -n rh-sso \
    --template={{.data.ADMIN_PASSWORD}} | base64 -d; echo
    ```
4.  **Configure RH-SSO Admin Console:**
    * Login to the Keycloak admin console using the retrieved credentials.
    * **Create 3scale Client:**
        * In the **maas** realm, navigate to `Clients`.
        * Create a new client: `Client ID`: `3scale`, `Client Protocol`: `openid-connect`.
        * Set `Access Type`: `confidential`. Enable `Standard Flow` only. Set `Valid Redirect URLs` to `*`. Save the client and note down the `Secret` from the `Credentials` tab.
    * **Add Mappers:**
        * In the `Mappers` section for the `3scale` client, add `email verified` (builtin) and `org_type` (User Attribute, `User Attribute`: `email`, `Token Claim Name`: `org_name`, `Claim JSON type`: `string`, enable the first 3 switches).
    * **Add Identity Provider (e.g., GitHub):**
        * In the Keycloak admin console, navigate to `Identity Providers`.
        * Select and configure your desired identity provider (e.g., `GitHub`). Ensure `Trust Email` is `ON` and `Sync Mode` is `import`.
5.  **Update 3scale Developer Portal to use RH-SSO:**
    * In the 3scale Admin Portal, go to **Audience -> Developer Portal -> Settings -> SSO Integrations**.
    * Create a new **SSO Integration** of type `Red Hat Single Sign On`.
        * Set `Client`: `3scale`
        * Set `Client secret`: Use the secret noted from Keycloak.
        * Set `Realm`: `https://keycloak-rh-sso.apps.prod.rhoai.rh-aiservices-bu.com/auth/realms/maas` (adjust to your cluster domain).
        * Ensure `Published` is **ticked**.
    * After creation, edit the RH-SSO integration to tick the checkbox **Always approve accounts...**.
    * You can now test the authentication flow from your Developer Portal.

---

## 6. Testing 3scale API

After completing the configurations, you can test the 3scale API.

### Steps:

1.  **Test Model Inferencing via 3scale:**
    Replace `***********` with your 3scale API key or a valid Authorization header.
    ```bash
    curl -X 'POST' \
        '[https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/completions](https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/completions)' \
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
      '[https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/models](https://granite-33-2b-instruct-maas-apicast-production.apps.cluster-7tqcw.7tqcw.sandbox3194.opentlc.com:443/v1/models)' \
      -H 'accept: application/json' \
      -H 'Authorization: Bearer ***********'
    ```