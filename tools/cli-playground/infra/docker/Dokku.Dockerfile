FROM docker.io/dokku/dokku:0.38.34@sha256:70c09c7f5badff1b0a7077fe899db269255a22aed08571f4da605bfcb50fd8a8
# Pin the official postgres plugin to release 2.7.0.
RUN dokku plugin:install https://github.com/dokku/dokku-postgres.git --committish e5840e2ce85786b3ebedc06ac0c6d0b786732fb8 --skip-install-trigger
