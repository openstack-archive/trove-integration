#!/usr/bin/env bash

# local.sh to install trove
# Install and start Trove (DBaaS) service

# Dependencies:
# - functions

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace

# Import common functions from devstack dir
# Destination path for installation ``DEST``
DEST=${DEST:-/opt/stack}
TOP_DIR=$(cd $(dirname "$0") && pwd)
source $TOP_DIR/stackrc
source $TOP_DIR/localrc
ENABLED_SERVICES+=,trove,rd-api,rd-tmgr
source $TOP_DIR/functions
source $TOP_DIR/lib/database

# Determine Host IP
if [ -z "$HOST_IP" ]; then
    HOST_IFACE=`ip route |awk '/default/ {print $5}'`
    HOST_IP=`/sbin/ifconfig $HOST_IFACE | awk '/inet addr/{gsub(/addr:/,"");print $2}'`
fi

# Determine the Service Host
if [ -z "$SERVICE_HOST" ]; then
    SERVICE_HOST=${HOST_IP}
    # Write out to localrc so it's available downstream (in redstack)
    echo "
SERVICE_HOST=${SERVICE_HOST}" >> $TOP_DIR/localrc
fi

# Public facing bits
SERVICE_PROTOCOL=${SERVICE_PROTOCOL:-http}
NETWORK_GATEWAY=${NETWORK_GATEWAY:-10.0.0.1}
KEYSTONE_AUTH_HOST=${KEYSTONE_AUTH_HOST:-$SERVICE_HOST}
KEYSTONE_AUTH_PROTOCOL=${KEYSTONE_AUTH_PROTOCOL:-$SERVICE_PROTOCOL}
KEYSTONE_AUTH_PORT=${KEYSTONE_AUTH_PORT:-35357}
OS_USER=${OS_USER:-admin}
OS_TENANT=${OS_TENANT:-admin}
DATABASE_HOST=${DATABASE_HOST:-localhost}
MYSQL_HOST=${MYSQL_HOST:-${DATABASE_HOST}}
DATABASE_USER=${DATABASE_USER:-root}
DATABASE_PASSWORD=${DATABASE_PASSWORD:-$MYSQL_PASSWORD}
BASE_SQL_CONN=${BASE_SQL_CONN:-${DATABASE_TYPE}://$DATABASE_USER:$DATABASE_PASSWORD@$DATABASE_HOST}

# Set up default configuration
TROVE_DIR=$DEST/trove/
TROVECLIENT_DIR=$DEST/python-troveclient/
TROVE_PACKAGES_DIR=/var/lib/packages/debian/
TROVE_BUILD_DIR=/tmp/build/
TROVE_INTEGRATION_CONF_DIR=/tmp/trove-integration/
TROVE_ENV_CONF_PATH=$TROVE_INTEGRATION_CONF_DIR/env.rc
TROVE_CONF_DIR=/etc/trove/
TROVE_LOCAL_CONF_DIR=$TROVE_DIR/etc/trove/
TROVE_AUTH_ENDPOINT=$KEYSTONE_AUTH_PROTOCOL://$KEYSTONE_AUTH_HOST:$KEYSTONE_AUTH_PORT/v2.0
TROVE_LOGDIR=${TROVE_LOGDIR:-/var/log/trove}
TROVE_AUTH_CACHE_DIR=${TROVE_AUTH_CACHE_DIR:-/var/cache/trove}

# Set Trove interface related configuration
TROVE_SERVICE_HOST=${TROVE_SERVICE_HOST:-$SERVICE_HOST}
TROVE_SERVICE_PORT=${TROVE_SERVICE_PORT:-8779}
TROVE_SERVICE_PROTOCOL=${TROVE_SERVICE_PROTOCOL:-$SERVICE_PROTOCOL}

# trove service git paths
GIT_BASE=https://github.com
TROVE_REPO=${GIT_BASE}/openstack/trove.git
TROVE_BRANCH=master
TROVECLIENT_REPO=${GIT_BASE}/openstack/python-troveclient.git
TROVECLIENT_BRANCH=master

# Support potential entry-points for console scripts
if [ -d $TROVE_DIR/bin ] ; then
    TROVE_BIN_DIR=$TROVE_DIR/bin
else
    TROVE_BIN_DIR=/usr/local/bin
fi

###############################################################################
# Misc. tools
###############################################################################

# msgout() - prints message with severity and time to stdout.
function msgout() {
    local level=$1
    local str=$2
    local tm=`date +"%Y-%m-%d %H:%M:%S"`
    if [ $level = "DEBUG" ] && [ -z $VERBOSE ]; then
            return 0
    else
        echo "$tm: $PROG [$$]: $1: $str"
    fi

    return 0
}

function trove_mysql_nova() {
    echo mysql nova --execute "$@"
    mysql -u root -p$DATABASE_PASSWORD nova --execute "$@"
}

function trove_manage() {
    cd $TROVE_DIR
    bin/trove-manage --config-file=$TROVE_CONF_DIR/trove.conf $@
}

###############################################################################
# Configure Keystone for Trove related helper functions
###############################################################################

function trove_get_attribute_id() {
    keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN $1-list | grep $2 | get_field $3
}

function trove_add_keystone_user() {
    # Adds a user. Prints the UUID to standard out.
    USER_NAME=$1
    USER_PASS=$2
    USER_EMAIL=$3
    USER_TENANT=$4
    # Create the user "trove"
    USER_UUID=`trove_get_attribute_id user $USER_NAME 1`
    if [ -z "$USER_UUID" ]; then
        USER_UUID=$(keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN user-create \
            --name=$USER_NAME \
            --pass=$USER_PASS \
            --email=$USER_EMAIL \
            --tenant_id $USER_TENANT \
            | grep " id " | get_field 2)
    fi
    echo $USER_UUID
}

function trove_create_keystone_user_role() {
    TENANT_UUID=$1
    USER_UUID=$2
    ROLE_UUID=$3
    keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN user-role-add \
        --tenant_id $TENANT_UUID \
        --user_id $USER_UUID \
        --role_id $ROLE_UUID
}

function trove_create() {
    keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN $1-create \
             --name $2 \
             | grep " id " | get_field 2
}

function trove_configure_keystone() {
    msgout "DEBUG" "Configuring keystone..."
    # Create the "trove" tenant
    # First we should check if these exist
    TROVE_TENANT=`trove_get_attribute_id tenant trove 1`
    if [ -z "$TROVE_TENANT" ]; then
        TROVE_TENANT=$(trove_create tenant trove)
    fi

    # Create the trove role if it doesn't exist.
    # Admin role should already exist
    ADMIN_ROLE=`trove_get_attribute_id role admin 1`
    TROVE_ROLE=`trove_get_attribute_id role trove 1`
    if [ -z "$TROVE_ROLE" ]; then
        TROVE_ROLE=$(trove_create role trove)
    fi

    TROVE_USER=$(trove_add_keystone_user trove TROVE-PASS trove@example.com $TROVE_TENANT)
    trove_create_keystone_user_role $TROVE_TENANT $TROVE_USER $TROVE_ROLE

    RADMIN_USER=$(trove_add_keystone_user radmin radmin radmin@example.com $TROVE_TENANT)
    trove_create_keystone_user_role $TROVE_TENANT $RADMIN_USER $TROVE_ROLE
    trove_create_keystone_user_role $TROVE_TENANT $RADMIN_USER $ADMIN_ROLE

    mkdir -p ${TROVE_INTEGRATION_CONF_DIR}
    touch $TROVE_ENV_CONF_PATH
    iniset $TROVE_ENV_CONF_PATH DEFAULT TROVE_TENANT $TROVE_TENANT
    iniset $TROVE_ENV_CONF_PATH DEFAULT TROVE_USER $TROVE_USER
    iniset $TROVE_ENV_CONF_PATH DEFAULT TROVE_ROLE $TROVE_ROLE

    # Now attempt a login to check it's working
    curl -d '{"auth":{"passwordCredentials":{"username": "trove", "password": "TROVE-PASS"},"tenantName":"trove"}}' \
     -H "Content-type: application/json" $TROVE_AUTH_ENDPOINT/tokens

    # Register trove service.
    TROVE_SERVICE_UUID=$(keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN service-list | grep "trove" | get_field 1)
    if [ -z $TROVE_SERVICE_UUID ]; then
        TROVE_SERVICE_UUID=$(keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN service-create \
            --name=trove \
            --type=database \
            --description="Trove Database as a Service" \
            | grep " id " | get_field 2)
        keystone --endpoint $TROVE_AUTH_ENDPOINT --token $SERVICE_TOKEN endpoint-create \
            --region RegionOne \
            --service_id $TROVE_SERVICE_UUID \
            --publicurl "$TROVE_SERVICE_PROTOCOL://$TROVE_SERVICE_HOST:$TROVE_SERVICE_PORT/v1.0/\$(tenant_id)s" \
            --adminurl "$TROVE_SERVICE_PROTOCOL://$TROVE_SERVICE_HOST:$TROVE_SERVICE_PORT/v1.0/\$(tenant_id)s" \
            --internalurl "$TROVE_SERVICE_PROTOCOL://$TROVE_SERVICE_HOST:$TROVE_SERVICE_PORT/v1.0/\$(tenant_id)s"
    fi
}

###############################################################################
# Setup Trove Config file and related functions
###############################################################################

function fix_rd_configfiles() {
    # Create the trove conf dir and cache dirs if they don't exist
    sudo mkdir -p ${TROVE_CONF_DIR}
    sudo mkdir -p ${TROVE_AUTH_CACHE_DIR}
    sudo chown -R $USER: ${TROVE_CONF_DIR}
    sudo chown -R $USER: ${TROVE_AUTH_CACHE_DIR}

    # Copy conf files over to the trove conf dir
    cd $TROVE_DIR
    cp etc/trove/trove.conf.sample $TROVE_CONF_DIR/trove.conf
    cp etc/trove/api-paste.ini $TROVE_CONF_DIR/api-paste.ini
    cp etc/trove/trove-taskmanager.conf.sample $TROVE_CONF_DIR/trove-taskmanager.conf

    # Fix the tokens in the conf files
    iniset $TROVE_CONF_DIR/trove.conf DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $TROVE_CONF_DIR/trove.conf DEFAULT sql_connection `database_connection_url trove`
    iniset $TROVE_CONF_DIR/api-paste.ini filter:tokenauth admin_token $SERVICE_TOKEN
    iniset $TROVE_CONF_DIR/api-paste.ini filter:tokenauth signing_dir $TROVE_AUTH_CACHE_DIR

    iniset $TROVE_CONF_DIR/trove-taskmanager.conf DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $TROVE_CONF_DIR/trove-taskmanager.conf DEFAULT sql_connection `database_connection_url trove`
    iniset $TROVE_CONF_DIR/trove-taskmanager.conf filter:tokenauth admin_token $SERVICE_TOKEN

    iniset $TROVE_LOCAL_CONF_DIR/trove-guestagent.conf.sample DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $TROVE_LOCAL_CONF_DIR/trove-guestagent.conf.sample DEFAULT sql_connection `database_connection_url trove`
    sed -i "s/localhost/$NETWORK_GATEWAY/g" $TROVE_LOCAL_CONF_DIR/trove-guestagent.conf.sample
}

###############################################################################
# Adding new flavours to nova and related functions
###############################################################################

function add_flavor() {
    local mod="add_flavor"
    msgout "DEBUG" "$mod<-- $FLAVOR_ID ($FLAVOR_NAME), memory=$FLAVOR_MEMORY_MB, root_gb=$FLAVOR_ROOT_GB, VCPUS=$5, EPHEMERAL=$6"
    FLAVOR_NAME=$1
    FLAVOR_ID=$2
    FLAVOR_MEMORY_MB=$3
    FLAVOR_ROOT_GB=$4
    FLAVOR_VCPUS=$5
    FLAVOR_EPHEMERAL=$6

    if [[ -z $(nova --os-username=$OS_USER --os-password=$ADMIN_PASSWORD --os-tenant-name=$OS_TENANT --os-auth-url=$TROVE_AUTH_ENDPOINT flavor-list | grep $FLAVOR_NAME) ]]; then
        nova --os-username=$OS_USER --os-password=$ADMIN_PASSWORD --os-tenant-name=$OS_TENANT --os-auth-url=$TROVE_AUTH_ENDPOINT flavor-create $FLAVOR_NAME $FLAVOR_ID $FLAVOR_MEMORY_MB $FLAVOR_ROOT_GB $FLAVOR_VCPUS --ephemeral $FLAVOR_EPHEMERAL
    fi
    msgout "DEBUG" "$mod:-->"
}

function add_flavors() {
    local mod="add_flavors"
    msgout "DEBUG" "$mod<-- "
    # Incredibly useful for testing resize in a VM.
    set +e
    add_flavor 'tinier' 6 506 10 1 0
    # It can also be useful to have a flavor with 512 megs and a bit of disk space.
    add_flavor 'm1.rd-tiny' 7 512 2 1 0
    # It's also useful to have a flavor that is slightly bigger than tiny but smaller than small...
    add_flavor 'm1.rd-smaller' 8 768 2 1 0
    # Flavors with ephemeral is needed for ephemeral support...
    add_flavor 'eph.rd-tiny' 9 512 2 1 1
    add_flavor 'eph.rd-smaller' 10 768 2 1 2
    set -e
    msgout "DEBUG" "$mod:-->"
}

###############################################################################
# stack.sh entry points
###############################################################################

# cleanup_troveclient() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_troveclient() {
    local mod="cleanup_troveclient"
    # This function intentionally left blank
    msgout "DEBUG" "$mod:<-- "
    msgout "DEBUG" "$mod:--> "
}

# cleanup_trove() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_trove() {
    local mod="cleanup_trove"
    # This function intentionally left blank
    msgout "DEBUG" "$mod:<-- "
    msgout "DEBUG" "$mod:--> "
}

# configure_troveclient() - Set config files, create data dirs, etc
function configure_troveclient() {
    local mod="configure_troveclient"
    msgout "DEBUG" "$mod<-- "
    setup_develop $TROVECLIENT_DIR
    msgout "DEBUG" "$mod:-->"
}

# configure_trove() - Set config files, create data dirs, etc
function configure_trove() {
    local mod="configure_trove"
    msgout "DEBUG" "$mod<-- ($TROVE_DIR)"

    install_package libxslt1-dev python-pexpect
    setup_develop $TROVE_DIR

    # Create the trove build dir if it doesn't exist
    sudo mkdir -p ${TROVE_BUILD_DIR}
    sudo chown -R $USER: ${TROVE_BUILD_DIR}

    msgout "DEBUG" "$mod:-->"
}

# install_troveclient() - Collect source and prepare
function install_troveclient() {
    local mod="install_troveclient"
    msgout "DEBUG" "$mod<-- "
    git_clone $TROVECLIENT_REPO $TROVECLIENT_DIR $TROVECLIENT_BRANCH
    msgout "DEBUG" "$mod:-->"
}

# install_trove() - Collect source and prepare
function install_trove() {
    local mod="install_trove"
    msgout "DEBUG" "$mod<-- "
    git_clone $TROVE_REPO $TROVE_DIR $TROVE_BRANCH
    msgout "DEBUG" "$mod:-->"
}

# init_trove() - Initializes Trove Database as a Service
function init_trove() {
    local mod="init_trove"
    msgout "DEBUG" "$mod<-- "

    msgout "DEBUG" "(Re)Creating trove db..."
    recreate_database trove utf8

    mkdir -p $TROVE_INTEGRATION_CONF_DIR

    msgout "DEBUG" "Creating Keystone users..."
    trove_configure_keystone

    msgout "DEBUG" "Making a temporary trove config file..."
    fix_rd_configfiles

    msgout "DEBUG" "Initializing the Trove Database..."
    trove_manage db_sync

    msgout "DEBUG" "Adding trove specific flavours..."
    add_flavors

    msgout "DEBUG" "Removing old certs from trove cache dir.."
    rm -fr $TROVE_AUTH_CACHE_DIR/*

    msgout "DEBUG" "$mod:-->"
}

# start_trove() - Start running processes, including screen
function start_trove() {
    local mod="start_trove"
    msgout "DEBUG" "$mod<-- "
    screen_it rd-api "cd $TROVE_DIR; bin/trove-api --config-file=$TROVE_CONF_DIR/trove.conf 2>&1 | tee $TROVE_LOGDIR/trove-api.log"
    screen_it rd-tmgr "cd $TROVE_DIR; bin/trove-taskmanager --config-file=$TROVE_CONF_DIR/trove-taskmanager.conf 2>&1 | tee $TROVE_LOGDIR/trove-taskmanager.log"
    msgout "DEBUG" "$mod:-->"
}

function devstack_post_install_hook() {
    install_trove
    install_troveclient
    configure_trove
    configure_troveclient
    init_trove
    start_trove
}

devstack_post_install_hook

# Restore xtrace
$XTRACE
