
https://docs.redhat.com/en/documentation/red_hat_single_sign-on/7.4/html/server_installation_and_configuration_guide/operator#external_database


apiVersion: v1
kind: Secret
metadata:
  name: keycloak-db-secret
type: Opaque
stringData:
  username: keycloak
  password: <generated-password>  # Replace this with your generated password


uuidgen | xargs -I{} kubectl create secret generic keycloak-db-secret \
  --from-literal=username=keycloak \
  --from-literal=password={}



apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgresal-db
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgresal-db
  serviceName: postgres-db
  template:
    metadata:
      labels:
        app: postgresql-db
    spec:
      volumes:
        - name: cache-volume
          emptyDir: {}
      containers:
        - name: postgresal-db
          image: docker-cto-dev-local.artifactrepository.citigroup.net/cti-cti-ake-gcs-ilab-173264/rhoai/rhscl/postgresql-10-rhe17:1-173
          env:
            - name: POSTGRESQL_USER
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: username
            - name: POSTGRESQL_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: password
            - name: POSTGRESQL_DATABASE
              value: keycloak
            - name: PGDATA
              value: /data/pgdata
          resources: {}
          volumeMounts:
            - name: cache-volume
              mountPath: /data
          terminationMessagePath: /dev/termination-log
          terminationMessagePolicy: File
          imagePullPolicy: Always
      restartPolicy: Always
      terminationGracePeriodSeconds: 30
      dnsPolicy: ClusterFirst
      securityContext: {}
      schedulerName: default-scheduler
  podManagementPolicy: OrderedReady
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0
  revisionHistoryLimit: 10
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Retain





apiVersion: v1
kind: Service
metadata:
  name: postgres-db
spec:
  selector:
    app: postgresql-db
  ports:
    - port: 5432
      targetPort: 5432
  type: ClusterIP




apiVersion: k8s.keycloak.org/v2alpha1
kind: Keycloak
metadata:
  name: rh-sso
  labels:
    app: rh-sso
spec:
  externalAccess:
    enabled: true
  instances: 1
  db:
    vendor: postgres
    host: postgres-db
    usernameSecret:
      name: keycloak-db-secret
      key: username
    passwordSecret:
      name: keycloak-db-secret
      key: password
  http:
    tlsSecret: example-tls-secret
  hostname:
    hostname: test.keycloak.org
