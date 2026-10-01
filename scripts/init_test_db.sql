-- Creates the test database alongside the dev database when the container
-- first starts. docker-entrypoint-initdb.d scripts run as the postgres
-- superuser; the POSTGRES_DB database already exists at this point.
CREATE DATABASE onestop_test WITH OWNER onestop;
