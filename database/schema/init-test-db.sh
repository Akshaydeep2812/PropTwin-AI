#!/bin/sh
# Runs once when the MySQL volume is first created. It adds the database used by the automated tests.
set -e
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE DATABASE IF NOT EXISTS proptwin_test CHARACTER SET utf8mb4;
GRANT ALL ON proptwin_test.* TO '$MYSQL_USER'@'%';
SQL
