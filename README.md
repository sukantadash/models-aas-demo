Please follow the sript.sh for installing Model aas components and configurations



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
  name: postgresql-db
spec:
  serviceName: postgres-db
  replicas: 1
  selector:
    matchLabels:
      app: postgresql-db
  template:
    metadata:
      labels:
        app: postgresql-db
    spec:
      containers:
        - name: postgresql-db
          image: postgres:latest
          volumeMounts:
            - mountPath: /data
              name: cache-volume
          env:
            - name: POSTGRES_USER
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: username
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: password
            - name: POSTGRES_DB
              value: keycloak
            - name: PGDATA
              value: /data/pgdata
      volumes:
        - name: cache-volume
          emptyDir: {}




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
