
https://docs.redhat.com/en/documentation/red_hat_single_sign-on/7.4/html/server_installation_and_configuration_guide/operator#external_database


apiVersion: v1
kind: Secret
metadata:
  name: keycloak-db-secret
  namespace: rh-sso
type: Opaque
stringData:
  POSTGRES_DATABASE: keycloak
  POSTGRES_EXTERNAL_ADDRESS: rh-sso-postgresql.rh-sso.svc.cluster.local
  POSTGRES_EXTERNAL_PORT: "5432"
  POSTGRES_HOST: rh-sso-postgresql.rh-sso.svc.cluster.local
  POSTGRES_PASSWORD: <generated-password>  # Replace this with your generated password
  POSTGRES_SUPERUSER: "true"
  POSTGRES_USERNAME: keycloak


uuidgen | xargs -I{} oc create secret generic keycloak-db-secret \
  --from-literal=POSTGRES_USERNAME=keycloak \
  --from-literal=POSTGRES_PASSWORD={} \
  --from-literal=POSTGRES_DATABASE=keycloak \
  --from-literal=POSTGRES_EXTERNAL_ADDRESS=rh-sso-postgresql.rh-sso.svc.cluster.local \
  --from-literal=POSTGRES_EXTERNAL_PORT=5432 \
  --from-literal=POSTGRES_HOST=rh-sso-postgresql.rh-sso.svc.cluster.local \
  --from-literal=POSTGRES_SUPERUSER=true \
  -n rh-sso



apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgresql-db
spec:
  serviceName: rh-sso-postgresql
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
          image: <update the image>
          env:
            - name: POSTGRESQL_USER
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: POSTGRES_USERNAME
            - name: POSTGRESQL_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret
                  key: POSTGRES_PASSWORD
            - name: POSTGRESQL_DATABASE
              valueFrom:
                secretKeyRef:
                  name: keycloak-db-secret            
                  key: POSTGRES_DATABASE
            - name: PGDATA
              value: /data/pgdata
          volumeMounts:
            - name: cache-volume
              mountPath: /data
      volumes:
        - name: cache-volume
          emptyDir: {}



apiVersion: v1
kind: Service
metadata:
  name: rh-sso-postgresql
spec:
  selector:
    app: postgresql-db
  ports:
    - port: 5432
      targetPort: 5432
  type: ClusterIP




apiVersion: keycloak.org/v1alpha1
kind: Keycloak
metadata:
  name: rh-sso
  labels:
    app: rh-sso
spec:
  externalAccess:
    enabled: true
  instances: 1
  externalDatabase:
    enabled: true
